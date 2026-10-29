#!/usr/bin/env python3
"""
Builds two self-hosted SVG cards for the profile README:

  assets/activity.svg  - weekly contribution "load" panel for the last 12 months
  assets/receipt.svg   - a printed "Build Log" receipt: recent commits, languages,
                         totals and a barcode encoded from 365 days of contributions

Stdlib only. Needs GITHUB_TOKEN (the Actions token is enough) and GH_USER.
Run with --mock to render with fake data (no network).
"""
import json, os, sys, random, datetime as dt, urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "omsatodiya")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("OUT_DIR", "assets")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

# Tokyo Night palette
BG, PANEL, GRID = "#1a1b27", "#1f2335", "#292e42"
BLUE, CYAN, PURPLE, TEXT, MUTED = "#7aa2f7", "#7dcfff", "#bb9af7", "#c0caf5", "#565f89"


# ----------------------------------------------------------------- data
def api(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None)
    req.add_header("Authorization", f"bearer {TOKEN}")
    req.add_header("User-Agent", "profile-cards")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes { name stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } } }
    }
  }
}"""


def fetch():
    u = api("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": USER}})["data"]["user"]
    cc = u["contributionsCollection"]
    days = [(d["date"], d["contributionCount"]) for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    repos = u["repositories"]["nodes"]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    commits = []
    for r in repos[:8]:  # most recently pushed public repos
        try:
            for c in api(f"https://api.github.com/repos/{USER}/{r['name']}/commits?author={USER}&per_page=3"):
                commits.append((c["commit"]["author"]["date"], r["name"], c["sha"][:7],
                                c["commit"]["message"].splitlines()[0]))
        except Exception:
            pass  # empty repo etc.
    commits.sort(reverse=True)
    return dict(days=days, total=cc["contributionCalendar"]["totalContributions"],
                commits_year=cc["totalCommitContributions"], repos=u["repositories"]["totalCount"],
                stars=sum(r["stargazerCount"] for r in repos), langs=langs, recent=commits[:6])


def mock():
    random.seed(7)
    end = dt.date(2026, 10, 30)
    days = []
    for i in range(364, -1, -1):
        d = end - dt.timedelta(days=i)
        m = d.month + (d.year - 2025) * 12
        base = {10: 2, 11: 3, 12: 10, 13: 14, 14: 10, 15: 9, 16: 12, 17: 22, 18: 36, 19: 30, 20: 0, 21: 0, 22: 12}.get(m, 3)
        days.append((d.isoformat(), max(0, int(random.gauss(base, base * 0.8))) if random.random() > 0.25 else 0))
    now = dt.datetime(2026, 10, 30, 8, 0, tzinfo=dt.timezone.utc)
    recent = [((now - dt.timedelta(hours=h)).isoformat(), r, s, m) for h, r, s, m in [
        (3, "tenantopsbench", "9f2c1ab", "grade tickets by final db state"),
        (20, "tenantopsbench", "41d0e7c", "add billing trap: double refund"),
        (49, "omsatodiya", "c3a9f10", "self-hosted profile cards"),
        (75, "Distributed-RAG", "7be21d4", "rerank before prompt assembly"),
        (130, "AI-Manthan", "0d4e8aa", "rls policy for tenant_members"),
        (300, "Finbridge---HTT3", "e81f3c2", "dedupe sync jobs on reconnect"),
    ]]
    return dict(days=days, total=sum(c for _, c in days), commits_year=510, repos=13, stars=2,
                langs={"TypeScript": 520000, "Python": 310000, "JavaScript": 90000, "CSS": 40000,
                       "C++": 25000, "HTML": 12000, "Shell": 3000}, recent=recent)


# ----------------------------------------------------------------- helpers
def fmt(n): return f"{n:,}"


def ago(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = (dt.datetime.now(dt.timezone.utc) - t).total_seconds() if not MOCK else (dt.datetime(2026, 10, 30, 8, tzinfo=dt.timezone.utc) - t).total_seconds()
    for unit, sec in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= sec:
            return f"{int(s // sec)}{unit}"
    return "now"


def cut(s, n): return s if len(s) <= n else s[: n - 1] + "…"


def streaks(days):
    counts = [c for _, c in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur = 0
    i = len(counts) - 1
    if counts and counts[-1] == 0:
        i -= 1  # today may not have a commit yet
    while i >= 0 and counts[i]:
        cur += 1; i -= 1
    return cur, longest


def smooth(pts, floor=None):
    """Catmull-Rom -> cubic bezier path through pts."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        if floor is not None:  # never dip below the zero line
            c1 = (c1[0], min(c1[1], floor)); c2 = (c2[0], min(c2[1], floor))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


# ----------------------------------------------------------------- activity panel
def activity_svg(D):
    days = D["days"]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    vals = [sum(c for _, c in w) for w in weeks]
    W, H = 900, 300
    L, R, T, B = 56, 24, 92, 44
    cw, ch = W - L - R, H - T - B
    top = max(vals) or 1
    step = 10 ** max(len(str(top)) - 1, 0)
    ymax = ((top // step) + 1) * step
    x = lambda i: L + cw * i / (len(vals) - 1)
    y = lambda v: T + ch - ch * v / ymax
    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = smooth(pts, T + ch)
    area = line + f" L{pts[-1][0]:.1f},{T + ch} L{pts[0][0]:.1f},{T + ch} Z"
    pk = max(range(len(vals)), key=vals.__getitem__)
    pk_date = dt.date.fromisoformat(weeks[pk][0][0])
    avg = sum(vals) / len(vals)
    cur, longest = streaks(days)

    grid = ""
    for k in range(5):
        v = ymax * k / 4
        gy = y(v)
        grid += f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" class="g"/>' \
                f'<text x="{L - 10}" y="{gy + 4:.1f}" class="ax" text-anchor="end">{int(v)}</text>'
    months, last = "", None
    for i, w in enumerate(weeks):
        d = dt.date.fromisoformat(w[0][0])
        if d.month != last and 0 < i < len(weeks) - 2:
            months += f'<text x="{x(i):.1f}" y="{H - 18}" class="ax" text-anchor="middle">{d.strftime("%b").lower()}</text>'
        last = d.month

    stats = [("contributions", fmt(D["total"])), ("avg / week", f"{avg:.0f}"),
             ("peak week", f"{vals[pk]} · {pk_date.strftime('%b %d').lower()}"),
             ("streak now / best", f"{cur}d / {longest}d")]
    stat_svg = ""
    for i, (k, v) in enumerate(stats):
        sx = L + i * (cw / 4)
        stat_svg += f'<text x="{sx:.1f}" y="70" class="sv">{escape(v)}</text>' \
                    f'<text x="{sx:.1f}" y="46" class="sk">{k}</text>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
 text{{font-family:{MONO}}}
 .g{{stroke:{GRID};stroke-width:1}} .ax{{fill:{MUTED};font-size:11px}}
 .sk{{fill:{MUTED};font-size:11px;letter-spacing:.06em;text-transform:uppercase}}
 .sv{{fill:{TEXT};font-size:20px;font-weight:600}}
 .ln{{fill:none;stroke:url(#lg);stroke-width:2.5;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.4s cubic-bezier(.6,.1,.3,1) .2s forwards}}
 .ar{{opacity:0;animation:fade 1.2s ease 1.6s forwards}}
 .pk{{opacity:0;animation:fade .4s ease 2.4s forwards}}
 .pulse{{transform-origin:{pts[pk][0]:.1f}px {pts[pk][1]:.1f}px;animation:pulse 2s ease-out 2.6s infinite}}
 @keyframes draw{{to{{stroke-dashoffset:0}}}} @keyframes fade{{to{{opacity:1}}}}
 @keyframes pulse{{0%{{transform:scale(1);opacity:.7}}100%{{transform:scale(3.2);opacity:0}}}}
</style>
<defs>
 <linearGradient id="lg" x1="0" x2="1"><stop offset="0" stop-color="{PURPLE}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>
 <linearGradient id="af" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BLUE}" stop-opacity=".35"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></linearGradient>
</defs>
<rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
<text x="{L}" y="24" class="ax">● <tspan fill="{BLUE}">{USER}</tspan> / contribution load — weekly, last 12 months</text>
{stat_svg}
{grid}{months}
<path d="{area}" fill="url(#af)" class="ar"/>
<path d="{line}" class="ln" pathLength="1"/>
<g class="pk"><circle cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="5" fill="{CYAN}" class="pulse"/>
<circle cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="4" fill="{CYAN}"/></g>
</svg>'''


# ----------------------------------------------------------------- receipt
def receipt_svg(D):
    W, PAD = 420, 28
    INK, FADED, PAPER = "#24283b", "#6b6f85", "#ece8dc"
    rows, y = [], 34

    def t(txt, x: float = PAD, anchor="start", cls="r"):
        rows.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{escape(str(txt))}</text>')

    def rule(dash=True):
        nonlocal y
        dsh = 'stroke-dasharray="3 3"' if dash else ""
        rows.append(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" stroke="{INK}" stroke-width="1" {dsh}/>')
        y += 22

    now = dt.datetime.now(IST) if not MOCK else dt.datetime(2026, 10, 30, 13, 30, tzinfo=IST)
    t("BUILD LOG", W / 2, "middle", "h"); y += 20
    t(f"{USER} · SVNIT Surat · backend & AI", W / 2, "middle", "s"); y += 18
    t(f"RECEIPT #{now:%y%j}-{D['total']:05d}", PAD, cls="s")
    t(now.strftime("%d %b %Y %H:%M IST").upper(), W - PAD, "end", "s"); y += 16
    rule()

    t("RECENTLY SHIPPED", cls="b"); y += 20
    for iso, repo, _, msg in D["recent"]:
        t(cut(repo, 16), cls="r")
        t(cut(msg, 25), 158, cls="s")
        t(ago(iso), W - PAD, "end", "s"); y += 18
    if not D["recent"]:
        t("nothing public this week — building in private", cls="s"); y += 18
    y += 4; rule()

    t("LANGUAGES (public repos)", cls="b"); y += 20
    tot = sum(D["langs"].values()) or 1
    for name, size in sorted(D["langs"].items(), key=lambda kv: -kv[1])[:5]:
        pct = f"{100 * size / tot:.1f}%"
        t(name, cls="r"); t(pct, W - PAD, "end", "r")
        x1, x2 = PAD + len(name) * 7.3 + 8, W - PAD - len(pct) * 7.3 - 8
        rows.append(f'<line x1="{x1:.0f}" y1="{y - 4}" x2="{x2:.0f}" y2="{y - 4}" stroke="{FADED}" stroke-dasharray="1 4" stroke-linecap="round"/>')
        y += 18
    y += 4; rule()

    cur, longest = streaks(D["days"])
    busiest = max(D["days"], key=lambda d: d[1])
    for k, v in [("contributions, 12 mo", fmt(D["total"])), ("commits this year", fmt(D["commits_year"])),
                 ("public repos", D["repos"]), ("stars earned", D["stars"]),
                 ("current streak", f"{cur} days"), ("longest streak, 12 mo", f"{longest} days"),
                 ("busiest day", f"{dt.date.fromisoformat(busiest[0]):%d %b} · {busiest[1]}")]:
        t(k.upper(), cls="s"); t(v, W - PAD, "end", "r"); y += 18
    y += 4; rule(dash=False)
    t("TOTAL SHIPPED", cls="h2"); t(f"{fmt(D['total'])} ✓", W - PAD, "end", "h2"); y += 26

    # barcode: one bar per day for 365 days; width/darkness from that day's count
    bar_top, bar_h = y, 54
    counts = [c for _, c in D["days"]][-365:]
    mx = max(counts) or 1
    span = W - 2 * PAD
    unit = span / len(counts)
    for i, c in enumerate(counts):
        if c == 0:
            continue
        lvl = min(4, 1 + int(4 * c / (mx + 1)))
        rows.append(f'<rect x="{PAD + i * unit:.2f}" y="{bar_top}" width="{unit * (0.35 + 0.16 * lvl):.2f}" height="{bar_h}" fill="{INK}" opacity="{0.45 + 0.14 * lvl:.2f}"/>')
    y += bar_h + 16
    first = dt.date.fromisoformat(D["days"][-len(counts)][0])
    t(f"{first:%d %b %y}".upper(), cls="xs"); t("1 bar = 1 day of commits", W / 2, "middle", "xs")
    t("TODAY", W - PAD, "end", "xs"); y += 28
    t("THANK YOU FOR REVIEWING MY CODE", W / 2, "middle", "s"); y += 16
    t("auto-printed every 12h by github actions", W / 2, "middle", "xs"); y += 22

    Hp = y  # paper height
    # torn bottom edge
    teeth = "".join(f"L{i - 6},{Hp + 7} L{i - 12},{Hp} " for i in range(W, 0, -12))
    paper = f'<path d="M0,0 L{W},0 L{W},{Hp} {teeth.strip()} L0,{Hp} Z" fill="{PAPER}"/>'
    # faint thermal-paper print lines
    paper += f'<rect width="{W}" height="{Hp}" fill="url(#thermal)"/>'

    SLOT = 30
    total_h = SLOT + Hp + 12
    sw = W + 40
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{sw}" height="{total_h}" viewBox="0 0 {sw} {total_h}">
<style>
 text{{font-family:{MONO};fill:{INK}}}
 .h{{font-size:22px;font-weight:700;letter-spacing:.32em}}
 .h2{{font-size:15px;font-weight:700;letter-spacing:.08em}}
 .b{{font-size:12px;font-weight:700;letter-spacing:.12em}}
 .r{{font-size:12px}} .s{{font-size:11px;fill:{FADED}}} .xs{{font-size:9.5px;fill:{FADED};letter-spacing:.06em}}
 .paper{{animation:print 3.2s steps(28,end) .3s both}}
 @keyframes print{{from{{transform:translateY(-{Hp}px)}}to{{transform:translateY(0)}}}}
</style>
<defs>
 <pattern id="thermal" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity=".018"/></pattern>
 <clipPath id="out"><rect x="0" y="{SLOT - 6}" width="{sw}" height="{total_h}"/></clipPath>
 <linearGradient id="slot" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a2f45"/><stop offset="1" stop-color="{BG}"/></linearGradient>
</defs>
<g clip-path="url(#out)"><g class="paper"><g transform="translate(20,{SLOT - 6})">{paper}{"".join(rows)}</g></g></g>
<rect x="0" y="0" width="{sw}" height="{SLOT}" rx="10" fill="url(#slot)"/>
<rect x="14" y="{SLOT - 10}" width="{sw - 28}" height="5" rx="2.5" fill="#0d0f17"/>
<circle cx="{sw - 26}" cy="11" r="3.5" fill="#9ece6a"><animate attributeName="opacity" values="1;.25;1" dur="1.1s" repeatCount="indefinite"/></circle>
<text x="20" y="15" style="fill:{MUTED};font-size:9.5px;letter-spacing:.2em">THERMAL · {USER.upper()}</text>
</svg>'''


MOCK = "--mock" in sys.argv

if __name__ == "__main__":
    data = mock() if MOCK else fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("activity", activity_svg(data)), ("receipt", receipt_svg(data))):
        with open(f"{OUT}/{name}.svg", "w", encoding="utf-8") as f:
            f.write(svg)
    print("wrote", f"{OUT}/activity.svg", f"{OUT}/receipt.svg")