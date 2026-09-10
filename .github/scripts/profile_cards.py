#!/usr/bin/env python3
"""Render the stat cards used by the profile README.

Talks to the GitHub GraphQL API and writes four SVGs (a light and a dark
variant of a stats card and a language card) into the given output dir.
Stdlib only, so the workflow needs no install step.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

# Languages that inflate the numbers without saying anything about the person.
IGNORED_LANGUAGES = {"HTML", "CSS", "SCSS", "Batchfile", "Makefile", "Dockerfile"}

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "panel": "#11171f",
        "border": "#1f2a35",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "accent": "#00e0b8",
        "track": "#1f2a35",
        "glow": "0.16",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "border": "#d8dee4",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#00a98c",
        "track": "#e6eaef",
        "glow": "0.09",
    },
}

W, H = 450, 200
PAD = 22
SANS = "'Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono','Fira Code',ui-monospace,SFMono-Regular,Consolas,monospace"


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.load(res)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def summarize(user):
    contrib = user["contributionsCollection"]
    repos = user["repositories"]["nodes"]

    # Weight every repository equally instead of by byte count, so one large
    # generated project does not swallow the whole chart.
    sizes, colors = Counter(), {}
    for repo in repos:
        edges = [
            e for e in repo["languages"]["edges"]
            if e["node"]["name"] not in IGNORED_LANGUAGES
        ]
        repo_total = sum(e["size"] for e in edges)
        if not repo_total:
            continue
        for edge in edges:
            name = edge["node"]["name"]
            sizes[name] += edge["size"] / repo_total
            colors[name] = edge["node"]["color"] or "#8b949e"

    total = sum(sizes.values()) or 1
    top = sizes.most_common(6)
    languages = [
        {"name": n, "share": 100 * s / total, "color": colors[n]} for n, s in top
    ]

    return {
        "name": user["name"] or user["login"],
        "login": user["login"],
        "contributions": contrib["contributionCalendar"]["totalContributions"],
        "commits": contrib["totalCommitContributions"]
        + contrib["restrictedContributionsCount"],
        "repositories": user["repositories"]["totalCount"],
        "pull_requests": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "languages": languages,
        "language_count": len(sizes),
    }


def human(n):
    if n >= 10_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}".replace(",", " ")


def shell(theme, title, note, body):
    t = THEMES[theme]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<defs>
  <radialGradient id="glow" cx="100%" cy="0%" r="85%">
    <stop offset="0%" stop-color="{t['accent']}" stop-opacity="{t['glow']}"/>
    <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>
  .card {{ fill: {t['bg']}; stroke: {t['border']}; }}
  text {{ font-family: {SANS}; }}
  .h {{ font-size: 15px; font-weight: 600; fill: {t['text']}; }}
  .note {{ font-size: 10.5px; fill: {t['muted']}; letter-spacing: .8px; text-transform: uppercase; }}
  .num {{ font-family: {MONO}; font-size: 21px; font-weight: 700; fill: {t['accent']}; }}
  .lab {{ font-size: 10px; fill: {t['muted']}; letter-spacing: .9px; text-transform: uppercase; }}
  .lang {{ font-size: 12.5px; fill: {t['text']}; }}
  .pct {{ font-family: {MONO}; font-size: 11.5px; fill: {t['muted']}; }}
  .rule {{ stroke: {t['border']}; }}
  .in {{ animation: rise .55s cubic-bezier(.2,.7,.3,1) both; }}
  .bar {{ transform-box: fill-box; transform-origin: left center; animation: grow .9s cubic-bezier(.2,.7,.3,1) both; }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(7px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
  @media (prefers-reduced-motion: reduce) {{ .in, .bar {{ animation: none; }} }}
</style>
<rect class="card" x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12"/>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="url(#glow)"/>
<rect x="{PAD}" y="26" width="3" height="14" rx="1.5" fill="{t['accent']}"/>
<text class="h" x="{PAD + 12}" y="38">{escape(title)}</text>
<text class="note" x="{W - PAD}" y="37" text-anchor="end">{escape(note)}</text>
<line class="rule" x1="{PAD}" y1="54" x2="{W - PAD}" y2="54"/>
{body}
</svg>
"""


def stats_card(theme, s):
    cells = [
        ("Contributions", s["contributions"]),
        ("Commits", s["commits"]),
        ("Repositories", s["repositories"]),
        ("Pull requests", s["pull_requests"]),
        ("Issues", s["issues"]),
        ("Languages", s["language_count"]),
    ]
    col_w = (W - 2 * PAD) / 3
    parts = []
    for i, (label, value) in enumerate(cells):
        x = PAD + (i % 3) * col_w
        y = 102 if i < 3 else 160
        parts.append(
            f'<g class="in" style="animation-delay:{0.06 * i + 0.1:.2f}s">'
            f'<text class="num" x="{x:.1f}" y="{y}">{human(value)}</text>'
            f'<text class="lab" x="{x:.1f}" y="{y + 17}">{label.upper()}</text>'
            f"</g>"
        )
    return shell(theme, "GitHub Stats", "last 12 months", "\n".join(parts))


def language_card(theme, s):
    t = THEMES[theme]
    langs = s["languages"]
    parts = [f'<rect x="{PAD}" y="72" width="{W - 2 * PAD}" height="11" rx="5.5" fill="{t["track"]}"/>']

    if langs:
        total = sum(l["share"] for l in langs) or 1
        parts.append('<g clip-path="inset(0 round 5.5px)" transform="translate(0,0)">')
        parts.append(f'<g class="bar" style="animation-delay:.1s">')
        x = float(PAD)
        avail = W - 2 * PAD
        for lang in langs:
            w = avail * lang["share"] / total
            parts.append(
                f'<rect x="{x:.2f}" y="72" width="{max(w, 0.6):.2f}" height="11" fill="{lang["color"]}"/>'
            )
            x += w
        parts.append("</g></g>")

    col_w = (W - 2 * PAD) / 2
    for i, lang in enumerate(langs):
        x = PAD + (i % 2) * col_w
        y = 118 + (i // 2) * 26
        parts.append(
            f'<g class="in" style="animation-delay:{0.06 * i + 0.25:.2f}s">'
            f'<circle cx="{x + 5:.1f}" cy="{y - 4}" r="5" fill="{lang["color"]}"/>'
            f'<text class="lang" x="{x + 17:.1f}" y="{y}">{escape(lang["name"])}</text>'
            f'<text class="pct" x="{x + col_w - 12:.1f}" y="{y}" text-anchor="end">{lang["share"]:.1f}%</text>'
            f"</g>"
        )

    if not langs:
        parts.append(
            f'<text class="lang" x="{PAD}" y="120">No language data available.</text>'
        )

    return shell(theme, "Most Used Languages", "weighted by repo", "\n".join(parts))


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    login = os.environ.get("GH_USER") or "GrossManuelHTL"
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN is required")

    s = summarize(fetch(login, token))
    os.makedirs(out_dir, exist_ok=True)

    for theme in THEMES:
        suffix = "-dark" if theme == "dark" else ""
        for name, svg in (
            (f"stats{suffix}.svg", stats_card(theme, s)),
            (f"langs{suffix}.svg", language_card(theme, s)),
        ):
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print(f"wrote {path}")

    print(json.dumps({k: v for k, v in s.items() if k != "languages"}, indent=2))


if __name__ == "__main__":
    main()
