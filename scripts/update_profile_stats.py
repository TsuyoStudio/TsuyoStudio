#!/usr/bin/env python3
"""Gera estatísticas SVG dentro do repositório, usando a API oficial do GitHub."""
import collections
import datetime as dt
import html
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

USER = os.getenv("PROFILE_USER", "TsuyoStudio")
PRIVATE_TOKEN = os.getenv("PROFILE_STATS_TOKEN", "").strip()
TOKEN = PRIVATE_TOKEN or os.getenv("GH_TOKEN", "")
OUT = Path("assets/stats")
OUT.mkdir(parents=True, exist_ok=True)

BG = "#151515"
PINK = "#FF0056"
TEXT = "#F4F4F4"
MUTED = "#AAAAAA"
BORDER = "#383838"

def api(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "TsuyoStudio-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)

def txt(x, y, content, size=18, color=TEXT, weight=400):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" font-family="Arial,Helvetica,sans-serif">'
            + html.escape(str(content)) + "</text>")

def panel(width, height, content, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title,quote=True)}">'
            f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="18" '
            f'fill="{BG}" stroke="{BORDER}"/>' + content + '</svg>')

def save(name, content):
    (OUT / name).write_text(content, encoding="utf-8")

profile = api(f"https://api.github.com/users/{USER}")
repos = []
for page in range(1, 11):
    batch = api(f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}")
    repos.extend(r for r in batch if not r.get("fork"))
    if len(batch) < 100:
        break

today = dt.datetime.now(dt.timezone.utc).strftime("%d/%m/%Y")
num_repos = profile.get("public_repos", len(repos))
stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
followers = profile.get("followers", 0)

body = txt(32, 48, "MÉTRICAS / GITHUB", 20, TEXT, 700)
body += txt(954, 48, "DADOS PÚBLICOS", 14, PINK, 700)
body += f'<path d="M30 69H1170" stroke="{BORDER}"/>'
for index, (name, val) in enumerate([
    ("REPOSITÓRIOS", num_repos),
    ("ESTRELAS", stars),
    ("SEGUIDORES", followers),
]):
    x = 33 + index * 387
    body += f'<rect x="{x}" y="93" width="358" height="132" rx="12" fill="#202020" stroke="{BORDER}"/>'
    body += txt(x+22, 130, name, 15, MUTED, 700)
    body += txt(x+21, 197, val, 57, PINK if index == 1 else TEXT, 700)
body += txt(33, 261, f"Atualizado em {today} · somente informações públicas", 14, MUTED)
save("summary.svg", panel(1200, 284, body, "Estatísticas do GitHub de TsuyoStudio"))

counts = collections.Counter()
for repo in repos:
    try:
        counts.update(api(repo["languages_url"]))
    except (urllib.error.URLError, KeyError) as exc:
        print("Language lookup unavailable:", repo.get("name"), str(exc))
languages = counts.most_common(5)

body = txt(32, 47, "LINGUAGENS / REPOSITÓRIOS PÚBLICOS", 19, TEXT, 700)
body += f'<path d="M30 66H1170" stroke="{BORDER}"/>'
if languages:
    total = sum(value for _, value in languages)
    for index, (language, amount) in enumerate(languages):
        y = 115 + index*56
        percent = 100*amount/total if total else 0
        body += txt(35, y, language, 18, TEXT, 700)
        body += txt(1030, y, f"{percent:.1f}%", 16, MUTED)
        body += f'<rect x="310" y="{y-17}" width="695" height="18" rx="5" fill="#292929"/>'
        body += f'<rect x="310" y="{y-17}" width="{max(3,round(695*percent/100))}" height="18" rx="5" fill="{PINK}"/>'
else:
    body += txt(35, 148, "Ainda não há linguagens detectadas nos repositórios públicos.", 19, MUTED)
    body += txt(35, 187, "Quando houver código público, os gráficos serão preenchidos.", 16, MUTED)
body += txt(35, 416, f"Fonte: GitHub API · {today} · projetos privados não incluídos", 13, MUTED)
save("languages.svg", panel(1200, 441, body, "Linguagens públicas de TsuyoStudio"))

weeks = []
total_contributions = None
if TOKEN:
    try:
        query = (
            "query($login:String!){user(login:$login){contributionsCollection{"
            "contributionCalendar{totalContributions weeks{contributionDays"
            "{date contributionCount}}}}}}"
        )
        response = api("https://api.github.com/graphql",
                       {"query": query, "variables": {"login": USER}})
        calendar = response["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        weeks = calendar["weeks"]
        total_contributions = calendar["totalContributions"]
    except (KeyError, TypeError, urllib.error.URLError, ValueError) as exc:
        print("GraphQL contributions not available:", str(exc))

# Este painel adicional mostra commits efetivos, não as contribuições calculadas
# pelo GitHub para o calendário oficial. Não há commits ou dias inventados.
WEEKLY_PATH = OUT / "weekly-activity.json"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

def read_weekly_snapshot():
    try:
        data = json.loads(WEEKLY_PATH.read_text(encoding="utf-8"))
        if sum(data["daily_commits"].values()) != data["total_commits"]:
            raise ValueError("Inconsistent weekly snapshot")
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Weekly snapshot unavailable:", str(exc))
        return None

def optional_live_weekly_snapshot():
    """Recalcula privados somente com token explicito de leitura dos repos."""
    if not PRIVATE_TOKEN:
        return None
    try:
        now_local = dt.datetime.now(dt.timezone.utc).astimezone(LOCAL_TZ)
        monday = now_local.date() - dt.timedelta(days=now_local.weekday())
        sunday = monday + dt.timedelta(days=6)
        start = dt.datetime.combine(monday, dt.time.min, LOCAL_TZ)
        end = start + dt.timedelta(days=7)
        start_iso = start.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = (end - dt.timedelta(seconds=1)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        before_iso = (start - dt.timedelta(seconds=1)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        owned = []
        for page in range(1, 11):
            batch = api(f"https://api.github.com/user/repos?affiliation=owner&per_page=100&page={page}")
            owned.extend(r for r in batch
                         if r.get("owner", {}).get("login", "").casefold() == USER.casefold()
                         and not r.get("fork"))
            if len(batch) < 100:
                break
        if not any(r.get("private") for r in owned):
            raise ValueError("PROFILE_STATS_TOKEN has no private repository access")

        counts = {(monday + dt.timedelta(days=i)).isoformat(): 0 for i in range(7)}
        changed_main = 0
        nonempty = 0
        branches_checked = 0

        for repository in owned:
            repo_id = repository["full_name"]
            repo_api = "https://api.github.com/repos/" + quote(repo_id, safe="/")
            seen = set()
            branch_names = []
            for page in range(1, 11):
                batch = api(f"{repo_api}/branches?per_page=100&page={page}")
                branch_names.extend(b["name"] for b in batch)
                if len(batch) < 100:
                    break
            if not branch_names:
                continue
            nonempty += 1
            branches_checked += len(branch_names)

            for branch in branch_names:
                for page in range(1, 31):
                    url = (f"{repo_api}/commits?sha={quote(branch, safe='')}"
                           f"&author={quote(USER)}&since={quote(start_iso)}"
                           f"&until={quote(end_iso)}&per_page=100&page={page}")
                    batch = api(url)
                    for commit in batch:
                        if (commit.get("author") or {}).get("login", "").casefold() != USER.casefold():
                            continue
                        sha = commit["sha"]
                        if sha in seen:
                            continue
                        seen.add(sha)
                        recorded = dt.datetime.fromisoformat(
                            commit["commit"]["committer"]["date"].replace("Z", "+00:00")
                        ).astimezone(LOCAL_TZ).date().isoformat()
                        if recorded in counts:
                            counts[recorded] += 1
                    if len(batch) < 100:
                        break

            # Comparação de arquivos distintos na branch principal apenas.
            default = repository.get("default_branch") or "main"
            before = api(f"{repo_api}/commits?sha={quote(default, safe='')}"
                         f"&until={quote(before_iso)}&per_page=1")
            if before:
                base_sha = before[0]["sha"]
                diff = api(f"{repo_api}/compare/{base_sha}...{quote(default, safe='')}")
                changed_main += len(diff.get("files") or [])
            else:
                # Repositório criado nesta semana: todos os arquivos atuais são novos.
                tree = api(f"{repo_api}/git/trees/{quote(default, safe='')}?recursive=1")
                changed_main += sum(1 for f in tree.get("tree", []) if f.get("type") == "blob")

        snapshot = {
            "schema_version": 1,
            "profile": USER,
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "verified_on": now_local.date().isoformat(),
            "timezone": "America/Sao_Paulo",
            "daily_commits": counts,
            "total_commits": sum(counts.values()),
            "changed_files_main": changed_main,
            "repos_checked": nonempty,
            "repository_branches_checked": branches_checked,
            "includes_private_repositories": True,
            "source": "GitHub API autenticada",
            "counting_rule": "SHA unico por repo entre branches; autor TsuyoStudio, sem bots",
            "changed_files_rule": "Arquivos distintos na comparacao semanal da branch principal de cada repo",
            "refresh_note": "Gerado com PROFILE_STATS_TOKEN; nao equivale ao calendario oficial do GitHub."
        }
        WEEKLY_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        return snapshot
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError,
            urllib.error.HTTPError) as exc:
        print("Live private activity unavailable; preserving verified snapshot:", str(exc))
        return None

weekly = optional_live_weekly_snapshot() or read_weekly_snapshot()

body = txt(32, 47, "CONTRIBUIÇÕES / ÚLTIMOS 12 MESES", 19, TEXT, 700)
body += f'<path d="M30 65H1170" stroke="{BORDER}"/>'

def contribution_color(value):
    return "#292929" if value == 0 else "#5A1532" if value == 1 else "#981842" if value < 4 else PINK

if weeks:
    active_days = sum(1 for week in weeks for day in week["contributionDays"]
                      if day["contributionCount"] > 0)
    body += txt(33, 100, f"{total_contributions} contribuições no período", 18, PINK, 700)
    body += txt(946, 100, f"{active_days} dias com registro", 14, MUTED, 700)

    # Calendário anual: uma célula por dia, conforme o GitHub.
    for ix, week in enumerate(weeks):
        for day in week["contributionDays"]:
            date_obj = dt.date.fromisoformat(day["date"])
            weekday = (date_obj.weekday() + 1) % 7
            color = contribution_color(day["contributionCount"])
            x = 33 + ix * 21
            y = 136 + weekday * 21
            body += f'<rect x="{x}" y="{y}" width="16" height="16" rx="3" fill="{color}"/>'

    # Um segundo quadro amplia os mesmos dias recentes; não soma
    # contribuições nem inventa atividade de repositórios privados.
    body += f'<path d="M30 302H1170" stroke="{BORDER}"/>'
    body += txt(33, 332, "FOCO / ÚLTIMAS 13 SEMANAS", 17, TEXT, 700)
    for ix, week in enumerate(weeks[-13:]):
        for day in week["contributionDays"]:
            date_obj = dt.date.fromisoformat(day["date"])
            weekday = (date_obj.weekday() + 1) % 7
            color = contribution_color(day["contributionCount"])
            x = 34 + ix * 20
            y = 353 + weekday * 20
            body += f'<rect x="{x}" y="{y}" width="15" height="15" rx="3" fill="{color}"/>'
    body += txt(365, 389, "ATIVIDADE REAL / GITHUB", 17, TEXT, 700)
    body += txt(365, 421, "Visão ampliada dos dias mais recentes.", 15, MUTED)
    body += txt(365, 450, "Mesma fonte e contagem do calendário anual.", 15, MUTED)
    body += txt(365, 477, "O trabalho privado só aparece quando registrado pelo GitHub.", 14, MUTED)
else:
    body += txt(33, 146, "Contribuições anuais indisponíveis nesta atualização.", 19, MUTED)
    body += txt(33, 189, "Os demais indicadores continuam disponíveis.", 16, MUTED)
    body += f'<path d="M30 302H1170" stroke="{BORDER}"/>'
    body += txt(33, 351, "O recorte recente também depende do calendário oficial.", 16, MUTED)

body += txt(33, 513, f"Fonte: calendário GitHub · atualização diária · {today}", 13, MUTED)

# Mantem os 371+91 quadrados anteriores e adiciona microquadrados
# coloridos: um para cada commit verificado da semana (até 168/dia).
body += f'<path d="M30 539H1170" stroke="{BORDER}"/>'
if weekly:
    monday = dt.date.fromisoformat(weekly["week_start"])
    sunday = dt.date.fromisoformat(weekly["week_end"])
    period = f"{monday.day:02d}/{monday.month:02d}–{sunday.day:02d}/{sunday.month:02d}"
    body += txt(33, 567, f"COMMITS REAIS / {period}", 18, TEXT, 700)
    body += txt(869, 567, f'{weekly["total_commits"]} COMMITS', 17, PINK, 700)
    body += txt(1072, 567, f'{weekly["changed_files_main"]} ARQUIVOS', 14, MUTED, 700)
    counts = weekly["daily_commits"]
    max_day = max(counts.values()) if counts else 0
    scale = max(1, (max_day + 167) // 168)
    weekdays = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
    for i in range(7):
        date = monday + dt.timedelta(days=i)
        amount = int(counts.get(date.isoformat(), 0))
        x = 33 + i * 163
        body += f'<rect x="{x}" y="588" width="150" height="225" rx="12" fill="#202020" stroke="{BORDER}"/>'
        body += txt(x+12, 612, f"{weekdays[i]} {date.day:02d}", 13, MUTED, 700)
        body += txt(x+12, 644, amount, 29, TEXT, 700)
        body += txt(x+12, 795, "COMMITS", 11, MUTED, 700)
        color = ("#5A1532" if amount < 5 else "#981842" if amount < 40
                 else "#D32A63" if amount < 100 else PINK)
        filled = min(168, (amount + scale - 1) // scale)
        for cell in range(168):
            cx = x + 12 + (cell % 14) * 9
            cy = 660 + (cell // 14) * 9
            fill = color if cell < filled else "#2B2B2B"
            body += f'<rect x="{cx}" y="{cy}" width="7" height="7" rx="1" fill="{fill}"/>'
    unit = "1 commit" if scale == 1 else f"{scale} commits"
    body += txt(33, 846, f"Cada quadrado colorido = {unit} · dias mais ativos ficam mais rosa", 14, MUTED)
    body += txt(33, 869, f'Fonte: snapshot verificado em {weekly["verified_on"]} · inclui branches privadas, sem duplicar SHA', 12, MUTED)
else:
    body += txt(33, 605, "Os dados semanais autenticados estão indisponíveis.", 18, MUTED)
save("activity.svg", panel(1200, 892, body, "Contribuições GitHub e commits verificados de TsuyoStudio"))

print("Estatísticas geradas:", [p.name for p in OUT.glob("*.svg")])
