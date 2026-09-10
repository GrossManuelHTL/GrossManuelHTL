#!/usr/bin/env python3
"""Render the stat cards used by the profile README.

Talks to the GitHub GraphQL API and writes four SVGs (a light and a dark
variant of a stats card and a language card) into the given output dir.
Stdlib only, so the workflow needs no install step.
"""

import datetime
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
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
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

    calendar = contrib["contributionCalendar"]
    days = [d for week in calendar["weeks"] for d in week["contributionDays"]]
    weekly = [
        sum(d["contributionCount"] for d in week["contributionDays"])
        for week in calendar["weeks"]
    ]

    longest = run = 0
    for day in days:
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)

    busiest = max(days, key=lambda d: d["contributionCount"]) if days else None

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
        "weekly": weekly,
        "week_starts": [
            week["contributionDays"][0]["date"] for week in calendar["weeks"]
        ],
        "active_days": sum(1 for d in days if d["contributionCount"]),
        "longest_streak": longest,
        "busiest_day": busiest["date"] if busiest else "",
        "busiest_count": busiest["contributionCount"] if busiest else 0,
    }


def human(n):
    if n >= 10_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}".replace(",", " ")


def shell(theme, title, note, body, w=None, h=None):
    t = THEMES[theme]
    w = w or W
    h = h or H
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
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
  .grid {{ stroke: {t['border']}; stroke-dasharray: 2 4; }}
  .axis {{ font-size: 9.5px; fill: {t['muted']}; letter-spacing: .5px; }}
  .foot {{ font-size: 11.5px; fill: {t['muted']}; }}
  .footv {{ font-size: 11.5px; font-weight: 600; fill: {t['accent']}; }}
  .sep {{ fill: {t['border']}; }}
  .peak {{ font-family: {MONO}; font-size: 10px; font-weight: 700; fill: {t['accent']}; }}
  .spark {{ stroke-dasharray: 4000; animation: draw 2.2s ease-out both; }}
  @keyframes draw {{ from {{ stroke-dashoffset: 4000; }} to {{ stroke-dashoffset: 0; }} }}
  .in {{ animation: rise .55s cubic-bezier(.2,.7,.3,1) both; }}
  .bar {{ transform-box: fill-box; transform-origin: left center; animation: grow .9s cubic-bezier(.2,.7,.3,1) both; }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(7px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
  @media (prefers-reduced-motion: reduce) {{ .in, .bar, .spark, .fill {{ animation: none; }} }}
</style>
<rect class="card" x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12"/>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="url(#glow)"/>
<rect x="{PAD}" y="26" width="3" height="14" rx="1.5" fill="{t['accent']}"/>
<text class="h" x="{PAD + 12}" y="38">{escape(title)}</text>
<text class="note" x="{w - PAD}" y="37" text-anchor="end">{escape(note)}</text>
<line class="rule" x1="{PAD}" y1="54" x2="{w - PAD}" y2="54"/>
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


AW, AH = 880, 232


def smooth_path(points):
    """Catmull-Rom through the points, emitted as cubic beziers."""
    if len(points) < 2:
        return ""
    d = [f"M{points[0][0]:.2f},{points[0][1]:.2f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i else points[0]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(
            f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}"
        )
    return " ".join(d)


def pretty_date(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%-d %b %Y")
    except ValueError:
        return iso


def activity_card(theme, s):
    t = THEMES[theme]
    weekly = s["weekly"]
    x0, x1 = PAD, AW - PAD
    y0, y1 = 76, 168
    peak = max(weekly) if weekly else 0
    scale = peak or 1
    step = (x1 - x0) / max(len(weekly) - 1, 1)

    points = [
        (x0 + i * step, y1 - (v / scale) * (y1 - y0))
        for i, v in enumerate(weekly)
    ]
    line = smooth_path(points)
    area = f"{line} L{x1:.2f},{y1} L{x0:.2f},{y1} Z" if line else ""

    parts = [
        f"""<style>
  .fill {{ animation: fade 1.4s .45s ease both; }}
  @keyframes fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
</style>
<defs>
  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{t['accent']}" stop-opacity=".38"/>
    <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
  </linearGradient>
</defs>"""
    ]

    # Reference lines at the peak, at half of it and at zero.
    for frac in (1.0, 0.5, 0.0):
        y = y1 - frac * (y1 - y0)
        parts.append(f'<line class="grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"/>')

    if area:
        parts.append(f'<path class="fill" d="{area}" fill="url(#area)"/>')
        parts.append(
            f'<path class="spark" d="{line}" fill="none" stroke="{t["accent"]}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        top = min(points, key=lambda pt: pt[1])
        label_x = min(max(top[0], x0 + 14), x1 - 14)
        parts.append(
            f'<g class="in" style="animation-delay:1.6s">'
            f'<circle cx="{top[0]:.2f}" cy="{top[1]:.2f}" r="3.5" fill="{t["bg"]}" '
            f'stroke="{t["accent"]}" stroke-width="2"/>'
            f'<text class="peak" x="{label_x:.2f}" y="{top[1] - 9:.2f}" '
            f'text-anchor="middle">{peak}</text></g>'
        )

    # One label per month, placed on the week that starts it.
    seen = set()
    for i, iso in enumerate(s["week_starts"]):
        month = iso[:7]
        if month in seen:
            continue
        seen.add(month)
        x = x0 + i * step
        if x > x1 - 18:
            continue
        label = datetime.date.fromisoformat(iso).strftime("%b")
        parts.append(f'<text class="axis" x="{x:.1f}" y="{y1 + 16}">{label}</text>')

    facts = [
        (human(s["active_days"]), "active days"),
        (f'{s["longest_streak"]}', "day longest streak"),
        (f'{s["busiest_count"]}', f'on {pretty_date(s["busiest_day"])}, the busiest day'),
    ]
    spans = []
    for i, (value, label) in enumerate(facts):
        lead = '<tspan class="sep" dx="10">·</tspan> ' if i else ""
        spans.append(f'{lead}<tspan class="footv">{value}</tspan> {escape(label)}')
    parts.append(
        f'<line class="rule" x1="{PAD}" y1="{y1 + 30}" x2="{AW - PAD}" y2="{y1 + 30}"/>'
        f'<text class="foot" x="{PAD}" y="{y1 + 50}">{" ".join(spans)}</text>'
    )

    return shell(
        theme,
        "Contribution Activity",
        "per week, last 12 months",
        "\n".join(parts),
        w=AW,
        h=AH,
    )


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
            (f"activity{suffix}.svg", activity_card(theme, s)),
        ):
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print(f"wrote {path}")

    skip = {"languages", "weekly", "week_starts"}
    print(json.dumps({k: v for k, v in s.items() if k not in skip}, indent=2))


if __name__ == "__main__":
    main()
