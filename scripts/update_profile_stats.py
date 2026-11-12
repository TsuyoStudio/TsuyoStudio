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

USER = os.getenv("PROFILE_USER", "TsuyoStudio")
TOKEN = os.getenv("GH_TOKEN", "")
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

body = txt(32, 47, "CONTRIBUIÇÕES / ÚLTIMOS 12 MESES", 19, TEXT, 700)
body += f'<path d="M30 65H1170" stroke="{BORDER}"/>'
if weeks:
    body += txt(33, 101, f"{total_contributions} contribuições no período", 18, PINK, 700)
    # Grade por semanas, respeitando semanas parciais.
    for ix, week in enumerate(weeks):
        for day in week["contributionDays"]:
            date_obj = dt.date.fromisoformat(day["date"])
            weekday = (date_obj.weekday() + 1) % 7
            value = day["contributionCount"]
            color = "#292929" if value == 0 else "#5A1532" if value == 1 else "#981842" if value < 4 else PINK
            x = 33 + ix*21
            y = 122 + weekday*21
            body += f'<rect x="{x}" y="{y}" width="16" height="16" rx="3" fill="{color}"/>'
else:
    body += txt(33, 146, "Contribuições anuais indisponíveis nesta atualização.", 19, MUTED)
    body += txt(33, 189, "Os demais indicadores continuam disponíveis.", 16, MUTED)
body += txt(33, 310, f"Fonte: GitHub · atualização diária · {today}", 13, MUTED)
save("activity.svg", panel(1200, 333, " ".join([body]), "Atividade GitHub de TsuyoStudio"))
print("Estatísticas geradas:", [p.name for p in OUT.glob("*.svg")])
