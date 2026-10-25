#!/usr/bin/env python3
"""Izbori 2026: private, super-simple election news reader. Standard library only.

  python3 izbori.py           fetch once, write izbori.html, open it
  python3 izbori.py --watch   refresh every 5 minutes
  python3 izbori.py --all     no election filter
"""
import html, re, sys, time, unicodedata, urllib.request, webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = [
    ("KRIK", "https://www.krik.rs/feed/"),
    ("CINS", "https://www.cins.rs/feed/"),
    ("BIRN", "https://balkaninsight.com/category/bi/balkans/serbia/feed/"),
    ("Radar", "https://radar.nova.rs/feed/"),
    ("N1", "https://n1info.rs/feed/"),
    ("Nova", "https://nova.rs/feed/"),
    ("Insajder", "https://insajder.net/feed"),
    ("Danas", "https://www.danas.rs/feed/"),
    ("Mašina", "https://www.masina.rs/feed/"),
]

# Edit freely. Matched at the start of a word, ignoring case, Cyrillic/Latin and č/ć/š/ž/đ.
# ALL-CAPS entries (acronyms) must match a whole word.
KEYWORDS = [
    "izbor", "RIK", "biralist", "birališt", "glasa", "glasov", "glasač", "glasanj",
    "izlaznost", "CRTA", "CeSID", "SNS", "Vučić", "student", "lista", "nepravilnost",
    "kupovina glasova", "kontrolor", "opozicij", "kampanj", "mandat", "skupštin",
    "bugarski voz", "election", "vote", "voting", "polling", "ballot",
]
DROP_CATEGORIES = ["svet"]  # nova.rs "Svet" = world news (e.g. Bulgaria's elections)
# Items mentioning these are dropped (other countries' elections). Same matching as KEYWORDS.
EXCLUDE = ["Bugar", "Sofij", "Bulgaria", "Sofia", "Radev"]  # "bugarski voz" (vote fraud) is kept

# Summary box above the news, per hour. Built only from sentences in the articles: nothing is guessed.
CITIES = ["Beograd", "Novi Sad", "Niš", "Kragujevac", "Subotica", "Zrenjanin", "Pančevo", "Čačak",
          "Kraljevo", "Novi Pazar", "Šabac", "Smederevo", "Leskovac", "Valjevo", "Vranje", "Užice",
          "Kruševac", "Sombor", "Jagodina", "Zaječar", "Pirot", "Loznica", "Sremska Mitrovica"]
TURNOUT = ["izlaznost", "izašlo", "glasalo", "turnout"]
DIASPORA = ["dijaspor", "inostranstv", "diaspora", "abroad"]
IRREGULAR = ["nepravilnost", "incident", "kupovin", "bugarski voz", "pritis", "prijav", "napad",
             "irregularit", "fraud"]

# Show only news published after this (25 Oct 2026, 06:00 Belgrade time = UTC+1 after DST ends).
SINCE = datetime(2026, 10, 25, 6, 0, tzinfo=timezone(timedelta(hours=1)))

UA = "IzboriReader/1.0 (personal use)"
OUT = Path(__file__).resolve().with_name("izbori.html")
WATCH_SECONDS = 300

CYR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџш",
               "a b v g d đ e ž z i j k l lj m n nj o p r s t ć u f h c č dž š".split()))


def lat(s):
    """Lowercase, Cyrillic -> Latin."""
    return "".join(CYR.get(ch, ch) for ch in s.lower())


def norm(s):
    """lat(), then č->c, ž->z, đ->dj etc."""
    s = lat(s).replace("đ", "dj")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def words(lst):
    return re.compile("|".join(
        r"\b" + re.escape(norm(k)) + (r"\b" if k.isupper() else "") for k in lst))


PATTERN, EXCLUDE_PATTERN = words(KEYWORDS), words(EXCLUDE)
TURNOUT_P, DIASPORA_P, IRREGULAR_P = words(TURNOUT), words(DIASPORA), words(IRREGULAR)
PERCENT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|odsto|posto|procen\w*)")
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Belgrade")
except Exception:  # no tz database: fall back to the computer's local time
    TZ = None


def text(el, tag):
    v = el.findtext(tag)
    return (v or "").strip()


def plain(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def fetch(feed):
    name, url = feed
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        try:
            when = parsedate_to_datetime(text(it, "pubDate"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except Exception:
            when = datetime(1970, 1, 1, tzinfo=timezone.utc)
        items.append({
            "outlet": name, "title": plain(text(it, "title")), "link": text(it, "link"),
            "snippet": plain(text(it, "description"))[:240], "when": when,
            # full text, only searched for the summary, never shown or saved
            "body": plain(text(it, "description") + " " + text(it, CONTENT))[:5000],
            "cats": [norm(c.text or "").strip() for c in it.findall("category")],
        })
    return items


def relevant(item):
    t = norm(item["title"] + " " + item["snippet"])
    if any(c in DROP_CATEGORIES for c in item["cats"]) or \
            EXCLUDE_PATTERN.search(t.replace("bugarski voz", "")):
        return False
    return bool(PATTERN.search(t))


def collect(show_all):
    items, failed = [], []
    with ThreadPoolExecutor(len(FEEDS)) as pool:
        for feed, res in zip(FEEDS, pool.map(lambda f: safe(fetch, f), FEEDS)):
            if res is None:
                failed.append(feed[0])
            else:
                items += res
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i["when"], reverse=True):
        if it["when"] < SINCE:
            continue
        if it["link"].startswith("http") and it["link"] not in seen and (show_all or relevant(it)):
            seen.add(it["link"])
            out.append(it)
    return out, failed


def summarize(items):
    """{hour: {"grad": [(label, sentence, item)], "dijaspora": [...], "nepr": [item]}}, newest first."""
    hours = {}
    for it in items:
        if not relevant(it):
            continue
        h = hours.setdefault(local(it["when"]).replace(minute=0, second=0, microsecond=0),
                             {"grad": [], "dijaspora": [], "nepr": [], "seen": set()})
        for sent in re.split(r"(?<=[.!?])\s+", it["title"] + ". " + it["body"]):
            n = norm(sent)
            if not PERCENT.search(sent) or len(sent) > 300:
                continue
            # diacritics kept for cities, so "nisu" (are not) is not read as Niš
            city = next((c for c in CITIES if re.search(r"\b" + lat(c), lat(sent))), "Srbija")
            key = (city, tuple(re.findall(r"\d+(?:[.,]\d+)?", sent)))  # same figure only once
            if key in h["seen"]:
                continue
            if DIASPORA_P.search(n):
                h["seen"].add(key)
                h["dijaspora"].append(("Dijaspora", sent, it))
            elif TURNOUT_P.search(n):
                h["seen"].add(key)
                h["grad"].append((city, sent, it))
        if IRREGULAR_P.search(norm(it["title"] + " " + it["snippet"])):
            h["nepr"].append(it)
    return sorted(hours.items(), reverse=True)


def safe(fn, arg):
    try:
        return fn(arg)
    except Exception as e:
        print("  %s: failed (%s)" % (arg[0], e), file=sys.stderr)
        return None


def local(dt):
    return dt.astimezone(TZ) if TZ else dt.astimezone()


def fmt_time(dt, today):
    if dt.year == 1970:
        return "—"
    d = local(dt)
    return d.strftime("%H:%M") if d.date() == today else d.strftime("%d.%m. %H:%M")


CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--line:#e7e5e4;--card:#fff;--accent:#b91c1c;--chip:#f5f5f4}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#9a9a9a;--line:#2a2a2a;
--card:#1b1b1b;--accent:#f87171;--chip:#242424}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
header h1{margin:0;font-size:1.6rem}header p{margin:2px 0 12px;color:var(--muted);font-size:.9rem}
.fail{color:var(--accent);font-size:.85rem;margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chips button{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--chip);
color:var(--fg);border-radius:999px;padding:4px 12px;cursor:pointer}
.chips button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}
.meta{font-size:.8rem;color:var(--muted)}.meta b{color:var(--accent);font-weight:600}
article a{display:block;color:var(--fg);text-decoration:none;font-weight:600;font-size:1.05rem;margin:2px 0}
article a:hover{text-decoration:underline}
article p{margin:0;color:var(--muted);font-size:.9rem;display:-webkit-box;-webkit-line-clamp:2;
-webkit-box-orient:vertical;overflow:hidden}
.sum{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;background:var(--card);
padding:10px 14px;margin-bottom:14px}.sum h2{margin:0 0 4px;font-size:1.05rem}
.sum details{border-top:1px solid var(--line);padding:6px 0}.sum summary{cursor:pointer;font-weight:600}
.sum h4{margin:8px 0 2px;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.sum ul{margin:0;padding-left:18px;font-size:.9rem}.sum li{margin:3px 0}.sum a{color:var(--fg)}
.sum .wait{color:var(--muted);font-size:.9rem;margin:2px 0 6px}.sum .note{color:var(--muted);font-size:.75rem;margin:6px 0 0}
"""

JS = """
document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.chips button').forEach(x=>x.classList.toggle('on',x===b));
 const o=b.dataset.o;document.querySelectorAll('article').forEach(a=>
  a.hidden=!!o&&a.dataset.o!==o);});
"""


def render_summary(items):
    e = html.escape

    def src(it):
        return ' <a href="%s" target="_blank" rel="noopener">%s</a>' % (e(it["link"]), e(it["outlet"]))

    def block(title, lis):  # empty parts are left out
        return "<h4>%s</h4><ul>%s</ul>" % (title, "".join(lis)) if lis else ""

    def span(h):
        return "%s–%02d:00 h" % (h.strftime("%H:00"), (h.hour + 1) % 24)

    # only hours with something to show; the newest of them is opened
    hours = [(h, d) for h, d in summarize(items) if d["grad"] or d["dijaspora"] or d["nepr"]]
    now = local(datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    out = []
    if not hours or hours[0][0] != now:
        out.append('<p class="wait">Čekamo nove podatke za %s, još uvek ih nema.%s</p>' % (
            span(now), " Ispod su poslednji podaci." if hours else ""))
    for n, (h, d) in enumerate(hours):
        lines = {}
        for k in ("grad", "dijaspora"):
            lines[k] = ['<li><b>%s:</b> „%s“ ·%s</li>' % (
                e(lab), PERCENT.sub(lambda m: "<b>%s</b>" % m.group(), e(sent)), src(it))
                for lab, sent, it in d[k]]
        nepr = ['<li>%s ·%s</li>' % (e(it["title"]), src(it)) for it in d["nepr"]]
        out.append('<details%s><summary>%s</summary>%s%s%s</details>' % (
            " open" if n == 0 else "", span(h),
            block("Procenat izlaznosti po gradovima", lines["grad"]),
            block("Procenat izlaznosti u dijaspori", lines["dijaspora"]),
            block("Nepravilnosti (%d)" % len(nepr), nepr)))
    return ('<section class="sum"><h2>Pregled po satima</h2>%s<p class="note">Rečenice iz vesti, '
            'bez procena. Zvanični podaci: RIK, CRTA, CeSID.</p></section>') % (
        "".join(out))


def render(items, failed, show_all):
    e = html.escape
    now = local(datetime.now(timezone.utc))
    outlets = [n for n, _ in FEEDS if any(i["outlet"] == n for i in items)]
    chips = '<button class="on" data-o="">Sve</button>' + "".join(
        '<button data-o="%s">%s</button>' % (e(n), e(n)) for n in outlets)
    rows = "".join(
        '<article data-o="%s"><div class="meta"><b>%s</b> · %s</div>'
        '<a href="%s" target="_blank" rel="noopener">%s</a><p>%s</p></article>\n' % (
            e(i["outlet"]), e(i["outlet"]), fmt_time(i["when"], now.date()),
            e(i["link"]), e(i["title"]), e(i["snippet"])) for i in items)
    fail = '<p class="fail">%s</p>' % " · ".join(e(n) + ": failed" for n in failed) if failed else ""
    return """<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300"><title>Izbori 2026</title><style>%s</style></head>
<body><main><header><h1>Izbori 2026</h1><p>Ažurirano %s · %d vesti%s</p></header>%s
%s<div class="chips">%s</div>%s</main><script>%s</script></body></html>""" % (
        CSS, now.strftime("%d.%m.%Y. %H:%M"), len(items), " · sve vesti" if show_all else "",
        fail, render_summary(items), chips, rows or "<p>Nema vesti.</p>", JS)


def run(show_all):
    items, failed = collect(show_all)
    OUT.write_text(render(items, failed, show_all), encoding="utf-8")
    print("%s  %d items, %d feeds failed -> %s" % (time.strftime("%H:%M"), len(items), len(failed), OUT))


def main():
    show_all, watch = "--all" in sys.argv, "--watch" in sys.argv
    run(show_all)
    webbrowser.open(OUT.as_uri())
    while watch:
        time.sleep(WATCH_SECONDS)
        try:
            run(show_all)
        except Exception as e:  # keep watching even if a round goes wrong
            print("round failed:", e, file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
