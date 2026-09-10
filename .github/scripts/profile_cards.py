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
    createdAt
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
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
        "levels": ("#0a5c4f", "#0e9c85", "#14c9aa", "#00e0b8"),
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
        "levels": ("#a8ecdf", "#5cd4bd", "#17b49a", "#009e86"),
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

    longest = run = 0
    for day in days:
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)

    busiest = max(days, key=lambda d: d["contributionCount"]) if days else None

    grid = [
        (w, day["weekday"], day["contributionCount"])
        for w, week in enumerate(calendar["weeks"])
        for day in week["contributionDays"]
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
        "created_at": user["createdAt"],
        "grid": grid,
        "week_count": len(calendar["weeks"]),
        "peak_day": max((c for _, _, c in grid), default=0),
        "active_days": sum(1 for d in days if d["contributionCount"]),
        "longest_streak": longest,
        "busiest_day": busiest["date"] if busiest else "",
        "busiest_count": busiest["contributionCount"] if busiest else 0,
    }


def human(n):
    if n >= 10_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}".replace(",", " ")


def shell(theme, title, note, body, w=None, h=None, chrome=True, frame=True):
    t = THEMES[theme]
    w = w or W
    h = h or H
    label = title or "profile banner"
    plate = (
        f'<rect class="card" x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12"/>'
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="url(#glow)"/>'
        if frame
        else f'<rect width="{w}" height="{h}" fill="{t["bg"]}"/>'
    )
    heading = (
        f'<rect x="{PAD}" y="26" width="3" height="14" rx="1.5" fill="{t["accent"]}"/>'
        f'<text class="h" x="{PAD + 12}" y="38">{escape(title)}</text>'
        f'<text class="note" x="{w - PAD}" y="37" text-anchor="end">{escape(note)}</text>'
        f'<line class="rule" x1="{PAD}" y1="54" x2="{w - PAD}" y2="54"/>'
        if chrome
        else ""
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">
<title>{escape(label)}</title>
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
{plate}
{heading}
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


HEADER_W, HEADER_H = 880, 122
FOOTER_W, FOOTER_H = 880, 60
PROFILE_W, PROFILE_H = 880, 186

# The bio. Edit these two columns and push; the workflow redraws the card.
PROFILE_LEFT = [
    ("Based in", "Marchtrenk, Upper Austria"),
    ("Time zone", "CET / CEST, UTC+1"),
    ("On GitHub since", None),  # filled in from the account creation date
]
PROFILE_RIGHT = [
    ("School", "HTBLA Leonding"),
    ("Focus", "Backend, cloud and containers, computer vision"),
    ("Offline", "Usually on a tennis court"),
]


def header_card(theme, s):
    t = THEMES[theme]
    dots = ("#ff5f57", "#febc2e", "#28c840")
    circles = "".join(
        f'<circle cx="{30 + i * 18}" cy="26" r="5.5" fill="{c}" opacity=".9"/>'
        for i, c in enumerate(dots)
    )
    body = f"""<style>
  .tt {{ font-family: {MONO}; font-size: 15px; }}
  .prompt {{ fill: {t['accent']}; font-weight: 700; }}
  .cmd {{ fill: {t['text']}; }}
  .who {{ fill: {t['text']}; font-weight: 700; font-size: 19px; }}
  .wtitle {{ font-family: {MONO}; font-size: 11px; fill: {t['muted']}; }}
</style>
<g>{circles}</g>
<text class="wtitle" x="{HEADER_W / 2}" y="30" text-anchor="middle">{escape(s['login'].lower())} — zsh</text>
<line class="rule" x1="0" y1="45" x2="{HEADER_W}" y2="45"/>
<text class="tt" x="30" y="78"><tspan class="prompt">~$</tspan> <tspan class="cmd">whoami</tspan></text>
<text class="tt who" x="30" y="105">{escape(s['name'])}</text>"""
    return shell(theme, "", "", body, w=HEADER_W, h=HEADER_H, chrome=False)


def profile_card(theme, s):
    since = ""
    try:
        since = datetime.date.fromisoformat(s["created_at"][:10]).strftime("%B %Y")
    except ValueError:
        pass

    rows = []
    col_w = (PROFILE_W - 2 * PAD) / 2
    for c, column in enumerate((PROFILE_LEFT, PROFILE_RIGHT)):
        for r, (label, value) in enumerate(column):
            x = PAD + c * col_w
            y = 58 + r * 46
            rows.append(
                f'<g class="in" style="animation-delay:{0.07 * (r * 2 + c) + 0.1:.2f}s">'
                f'<text class="lab" x="{x:.0f}" y="{y}">{escape(label.upper())}</text>'
                f'<text class="val" x="{x:.0f}" y="{y + 20}">{escape(value or since)}</text>'
                f"</g>"
            )
    body = (
        f"<style>.val {{ font-size: 14px; fill: {THEMES[theme]['text']}; }}</style>"
        + "".join(rows)
    )
    return shell(theme, "About me", "", body, w=PROFILE_W, h=PROFILE_H, chrome=False)


def mix(a, b, t):
    """Blend two #rrggbb colours; t=0 is a, t=1 is b."""
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


BUG_W, BUG_H = 880, 36
BUG_CYCLE = 14.0     # seconds for one full pass, including the wait offscreen
BUG_STEP = 0.42      # seconds per leg swing
GROUND = 23          # y of the rule the beetle walks on

# Fractions of the cycle: enter, stop to groom, carry on, wait offscreen.
BUG_MARKS = (0.03, 0.38, 0.50, 0.93)
BUG_FROM, BUG_MID, BUG_TO = -34, 424, 918


def bug_frames(pose):
    """Keyframe stops for one leg group, sampled at every leg swing.

    pose(t, walking) returns the angle in degrees at time t, so the walking
    legs and the one that lifts during the pause can share this generator.
    """
    stop_a, stop_b = BUG_MARKS[1] * BUG_CYCLE, BUG_MARKS[2] * BUG_CYCLE
    steps = int(BUG_CYCLE / BUG_STEP) + 1
    out, seen = [], set()
    for i in range(steps + 1):
        t = min(i * BUG_STEP, BUG_CYCLE)
        pct = round(100 * t / BUG_CYCLE, 2)
        if pct in seen:
            continue
        seen.add(pct)
        out.append(f"{pct:g}%{{transform:rotate({pose(t, not stop_a <= t < stop_b):.1f}deg)}}")
    return "".join(out)


def bug_card(theme):
    """A beetle walking the rule under the banner. A bug in the README."""
    t = THEMES[theme]
    body_dark = mix(t["accent"], "#000000", 0.45 if theme == "dark" else 0.25)
    limb = mix(t["muted"], t["text"], 0.35)

    # Tripod gait: three legs swing forward while the other three push back.
    def swing(phase):
        def pose(time, walking):
            if not walking:
                return 0.0
            return 13.0 if int(time / BUG_STEP) % 2 == phase else -13.0
        return pose

    def groom(time, walking):
        """The front right leg, which sweeps the antenna during the stop."""
        if walking:
            return swing(1)(time, True)
        rel = (time - BUG_MARKS[1] * BUG_CYCLE) / BUG_STEP
        return -46.0 if int(rel) % 2 else -30.0

    legs = []
    joints = ((-4.6, "back"), (0.4, "mid"), (5.2, "front"))
    for side in (-1, 1):                      # -1 is the far side, drawn first
        for i, (jx, kind) in enumerate(joints):
            # Feet land on the rule, so the beetle stands on the line rather
            # than straddling it.
            reach = {"back": (-4.6, 5.7), "mid": (-0.8, 5.9), "front": (4.8, 5.6)}[kind]
            group = "a" if (i + (side < 0)) % 2 else "b"
            if side > 0 and kind == "front":
                group = "g"
            legs.append(
                f'<g transform="translate({jx:.1f},-5.4)">'
                f'<g class="leg {group}">'
                f'<path d="M0,0 L{reach[0] * 0.5:.1f},{reach[1] * 0.55:.1f} '
                f'L{reach[0]:.1f},{reach[1]:.1f}" fill="none" stroke="{limb}" '
                f'stroke-width="{1.5 if side > 0 else 1.1:.1f}" stroke-linecap="round" '
                f'stroke-linejoin="round" opacity="{1 if side > 0 else .55:g}"/>'
                f"</g></g>"
            )

    beetle = f"""<g class="bob">
{chr(10).join(legs)}
<ellipse cx="-0.4" cy="-8.6" rx="8.2" ry="5.3" fill="url(#shell)"/>
<path d="M-8.4,-8.2 A8.2,5.3 0 0 0 6.4,-6.2" fill="none" stroke="{body_dark}" stroke-width="1" stroke-opacity=".7"/>
<path d="M-7.2,-10.4 A8.2,5.3 0 0 1 0.8,-13.7" fill="none" stroke="#ffffff" stroke-width="1.2" stroke-opacity=".38" stroke-linecap="round"/>
<ellipse cx="6.4" cy="-10" rx="3.8" ry="3.6" fill="{body_dark}"/>
<circle cx="10.2" cy="-10.8" r="2.5" fill="{body_dark}"/>
<g class="feel">
  <path d="M11.5,-12.3 q2.6,-1 3.6,-2.9" fill="none" stroke="{limb}" stroke-width="1.1" stroke-linecap="round"/>
  <path d="M11.8,-9.8 q3,-0.3 4.2,-1.7" fill="none" stroke="{limb}" stroke-width="1.1" stroke-linecap="round"/>
</g>
</g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{BUG_W}" height="{BUG_H}" viewBox="0 0 {BUG_W} {BUG_H}" role="img" aria-label="a beetle walking along a divider">
<title>a beetle walking along a divider</title>
<defs>
  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{t['accent']}" stop-opacity="0"/>
    <stop offset="50%" stop-color="{t['accent']}" stop-opacity=".7"/>
    <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
  </linearGradient>
  <radialGradient id="shell" cx="34%" cy="26%" r="78%">
    <stop offset="0%" stop-color="{mix(t['accent'], '#ffffff', .35)}"/>
    <stop offset="62%" stop-color="{t['accent']}"/>
    <stop offset="100%" stop-color="{body_dark}"/>
  </radialGradient>
</defs>
<style>
  .walk {{ animation: walk {BUG_CYCLE:g}s linear infinite; }}
  @keyframes walk {{
    0%,{BUG_MARKS[0] * 100:g}% {{ transform: translateX({BUG_FROM}px); }}
    {BUG_MARKS[1] * 100:g}%,{BUG_MARKS[2] * 100:g}% {{ transform: translateX({BUG_MID}px); }}
    {BUG_MARKS[3] * 100:g}%,100% {{ transform: translateX({BUG_TO}px); }}
  }}
  .bob {{ animation: bob {BUG_STEP * 2:g}s ease-in-out infinite; }}
  @keyframes bob {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-.7px); }} }}
  .feel {{ animation: feel 1.1s ease-in-out infinite; transform-origin: 12px -11px; }}
  @keyframes feel {{ 0%,100% {{ transform: rotate(-5deg); }} 50% {{ transform: rotate(6deg); }} }}
  .leg {{ animation-duration: {BUG_CYCLE:g}s; animation-timing-function: ease-in-out; animation-iteration-count: infinite; }}
  .a {{ animation-name: gaitA; }}
  .b {{ animation-name: gaitB; }}
  .g {{ animation-name: gaitG; }}
  @keyframes gaitA {{ {bug_frames(swing(0))} }}
  @keyframes gaitB {{ {bug_frames(swing(1))} }}
  @keyframes gaitG {{ {bug_frames(groom)} }}
  @media (prefers-reduced-motion: reduce) {{
    .walk, .bob, .feel, .leg {{ animation: none; }}
    .walk {{ transform: translateX({BUG_MID}px); }}
  }}
</style>
<rect x="0" y="{GROUND - 1}" width="{BUG_W}" height="2" fill="url(#rule)"/>
<g transform="translate(0,{GROUND})">
  <g class="walk">
{beetle}
  </g>
</g>
</svg>
"""

def footer_card(theme, s):
    t = THEMES[theme]
    body = f"""<defs>
  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{t['accent']}" stop-opacity="0"/>
    <stop offset="50%" stop-color="{t['accent']}" stop-opacity=".8"/>
    <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect x="0" y="18" width="{FOOTER_W}" height="2" fill="url(#rule)"/>
<text class="foot" x="{FOOTER_W / 2}" y="46" text-anchor="middle">
  Every image on this page is regenerated nightly by a workflow in this repo.
</text>"""
    return shell(theme, "", "", body, w=FOOTER_W, h=FOOTER_H, chrome=False, frame=False)


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
            (f"header{suffix}.svg", header_card(theme, s)),
            (f"footer{suffix}.svg", footer_card(theme, s)),
            (f"bug{suffix}.svg", bug_card(theme)),
            (f"profile{suffix}.svg", profile_card(theme, s)),
        ):
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print(f"wrote {path}")

    skip = {"languages", "grid"}
    print(json.dumps({k: v for k, v in s.items() if k not in skip}, indent=2))


if __name__ == "__main__":
    main()
