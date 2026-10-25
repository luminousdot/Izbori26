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
    ("Južne vesti", "https://www.juznevesti.com/feed/"),  # Niš and the south
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
# Diaspora: these come first in the widget, then any other city below that the news mentions.
WORLD_FIRST = ["Berlin", "London", "New York"]
WORLD = WORLD_FIRST + ["Beč", "Cirih", "Pariz", "Frankfurt", "Minhen", "Štutgart", "Brisel", "Amsterdam",
                       "Stokholm", "Oslo", "Toronto", "Čikago", "Moskva", "Ljubljana", "Podgorica"]
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


def city_re(city):
    """Matches the city in any case form: Novi Sad/Novom Sadu, Kragujevac/Kragujevcu, Šabac/Šapcu."""
    stems = []
    for w in lat(city).split():
        w = w[:-2] if w.endswith(("ac", "ak")) else w[:-1] if w[-1] in "aeio" else w
        stems.append(re.escape(w).replace("šab", "ša[bp]"))
    return re.compile(r"\b" + r"\w*\s+".join(stems) + r"\w*")


WORLD_SPECIAL = {"New York": r"\b(?:nju\s*jork|new\s+york)\w*", "Beč": r"\bbeč(?!ej)\w*",  # not Bečej
                 "Cirih": r"\b(?:cirih|zürich|zurich)\w*"}
WORLD_RES = [(c, re.compile(WORLD_SPECIAL[c]) if c in WORLD_SPECIAL else city_re(c)) for c in WORLD]
CITY_RES = [(c, city_re(c)) for c in CITIES] + WORLD_RES + [
    ("Srbija", re.compile(r"\bsrbij\w*")), ("Dijaspora", re.compile(r"\b(?:dijaspor|inostranstv|diaspora|abroad)\w*"))]
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


def pct(text):  # first percentage: "18,2 odsto" -> "18,2%"
    return re.search(r"\d+(?:[.,]\d+)?", PERCENT.search(text).group()).group() + "%"


# "u Bečeju", "у Врању": some place that is not in the lists, so not a figure for all of Serbia
OTHER_PLACE = re.compile(r"\b[uUуУ]\s+[A-ZČĆŠŽĐА-ЯЂЈЉЊЋЏ][a-zčćšžđа-яђјљњћџ]")


def places(l, sent=""):
    """[(place, "31,2%")] for each city in the sentence ("Beograd 35%, Niš 31%"), else [("Srbija", ...)]."""
    hits = sorted((m.start(), c) for c, r in CITY_RES for m in [r.search(l)] if m)
    out = []
    for i, (start, c) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(l)
        seg = l[start:end]
        if not PERCENT.search(seg) and i == 0:  # "izlaznost 33% u Nišu": the figure comes first
            seg = l[:end]
        if PERCENT.search(seg):
            out.append((c, pct(seg)))
    return out or ([] if OTHER_PLACE.search(sent) else [("Srbija", pct(l))])


def summarize(items):
    """{hour: {"grad": [(place, sentence, item, "31,2%", time)], "dijaspora": [...], "nepr": [item]}},
    newest first."""
    hours = {}

    def bucket(t):
        return hours.setdefault(t.replace(minute=0, second=0, microsecond=0),
                                {"grad": [], "dijaspora": [], "nepr": [], "seen": set()})

    now = local(datetime.now(timezone.utc))
    for it in items:
        if not relevant(it):
            continue
        pub = local(it["when"])
        prev_turnout = False
        for sent in re.split(r"(?<=[.!?])\s+", it["title"] + ". " + it["body"]):
            n, l = norm(sent), lat(sent)  # diacritics kept for cities, so "nisu" is not read as Niš
            # a turnout figure: the sentence, or the one before it, talks about turnout
            turnout, prev_turnout = TURNOUT_P.search(n) or prev_turnout, bool(TURNOUT_P.search(n))
            if not PERCENT.search(l) or len(sent) > 300 or not (turnout or DIASPORA_P.search(n)):
                continue
            found = places(l, sent)
            # "do 16 sati" / "do 16h" / "do 16 časova": the figure belongs to 16:00, not to when the
            # article (often a live blog opened in the morning) was first published
            m = re.search(r"\bdo\s+(\d{1,2})(?:[.:]00)?\s*(?:h\b|sat|čas)", l)
            when = pub.replace(hour=int(m.group(1)), minute=0) if m and int(m.group(1)) < 24 else pub
            if when > now:
                when = pub
            h = bucket(when)
            for place, value in found:
                if (place, value) in h["seen"]:  # same figure only once per hour
                    continue
                h["seen"].add((place, value))
                abroad = place == "Dijaspora" or place in WORLD
                h["dijaspora" if abroad else "grad"].append((place, sent, it, value, when))
        if IRREGULAR_P.search(norm(it["title"] + " " + it["snippet"])):
            bucket(pub)["nepr"].append(it)
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


DARK = "--bg:#121212;--fg:#ececec;--muted:#9a9a9a;--line:#2a2a2a;--card:#1b1b1b;--accent:#f87171;--chip:#242424"
# Follows the phone's setting until the header button picks light or dark (remembered in the browser).
CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--line:#e7e5e4;--card:#fff;--accent:#b91c1c;--chip:#f5f5f4}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){%s}}
:root[data-theme=dark]{%s}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px}
#theme{font:inherit;font-size:1.1rem;line-height:1;width:40px;height:40px;border-radius:999px;cursor:pointer;
border:1px solid var(--line);background:var(--chip);color:var(--fg)}
""" % (DARK, DARK) + """*{box-sizing:border-box}
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
.sum details{border-top:1px solid var(--line);padding:6px 0}
.older>summary{color:var(--muted)}.older>details{margin-left:14px}.older>details:first-of-type{margin-top:6px}.sum summary{cursor:pointer;font-weight:600}
.ws{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:8px}
.w{border:1px solid var(--line);border-radius:8px;padding:8px;min-width:0}
.sum h4{margin:0;font-size:.68rem;line-height:1.25;text-transform:uppercase;letter-spacing:.02em;color:var(--muted);
overflow-wrap:anywhere;hyphens:auto}.big.zero{color:var(--muted);font-weight:400}.big.old{opacity:.55}.w:has(.list) .small{-webkit-line-clamp:unset;display:block}
.list{display:block;margin-top:2px}
.big{font-size:1.7rem;font-weight:700;line-height:1.2;margin:4px 0;color:var(--accent)}
.small{font-size:.78rem;line-height:1.35;color:var(--muted);display:-webkit-box;-webkit-line-clamp:5;
-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.sum a{color:var(--fg)}
.sum .wait{color:var(--muted);font-size:.9rem;margin:2px 0 6px}.sum .note{color:var(--muted);font-size:.75rem;margin:6px 0 0}
"""

JS = """
const root=document.documentElement,tb=document.getElementById('theme');
const isDark=()=>(root.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'))==='dark';
const icon=()=>{tb.textContent=isDark()?'\u2600\uFE0E':'\u263E';tb.title=isDark()?'Svetla tema':'Tamna tema';};
icon();tb.onclick=()=>{root.dataset.theme=isDark()?'light':'dark';
 try{localStorage.setItem('theme',root.dataset.theme)}catch(e){};icon();};
document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.chips button').forEach(x=>x.classList.toggle('on',x===b));
 const o=b.dataset.o;document.querySelectorAll('article').forEach(a=>
  a.hidden=!!o&&a.dataset.o!==o);});
"""


def render_summary(items):
    e = html.escape

    def link(it, txt):
        return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (e(it["link"]), txt)

    def hm(it):
        return local(it["when"]).strftime("%H:%M")

    def widget(label, big, small, old=False):
        cls = " zero" if big in ("—", 0) else " old" if old else ""
        return '<div class="w"><h4>%s</h4><div class="big%s">%s</div><div class="small">%s</div></div>' % (
            label, cls, big, small or "Čekamo podatke")

    def turnout(cell):  # big number: the latest figure; below it, every source
        rows, old = cell
        if not rows:
            return "—", ""
        links = " · ".join(link(it, "%s %s" % (val, e(it["outlet"]))) for _, _, it, val, _ in rows)
        when = ("Poslednji podatak u %s" if old else "Ažurirano %s") % rows[0][4].strftime("%H:%M")
        return rows[0][3], when + "<br>" + links, old

    def world(cell):  # big number: the first place (see world_order), named in the text below
        rows, old = cell
        if not rows:
            return "—", ""
        name = {"Dijaspora": "Ukupno"}
        links = "<br>".join(link(it, "%s %s" % (e(name.get(p, p)), val)) for p, _, it, val, _ in rows)
        when = ("Poslednji podatak u %s" if old else "Ažurirano %s") % max(r[4] for r in rows).strftime("%H:%M")
        return rows[0][3], '%s<span class="list">%s</span>' % (when, links), old

    def span(h):
        return "%s–%02d:00 h" % (h.strftime("%H:00"), (h.hour + 1) % 24)

    # only hours with something to show; the newest of them is opened
    hours = [(h, d) for h, d in summarize(items) if d["grad"] or d["dijaspora"] or d["nepr"]]

    # An hour without a new figure shows the last known one, so a widget is never empty.
    metrics = {}
    for city in ("Beograd", "Niš", "Novi Sad", "Srbija"):
        metrics[city] = lambda d, c=city: [r for r in d["grad"] if r[0] == c]
    def world_order(r):  # overall figure, then Berlin, London, New York, then the rest, newest first
        rank = 0 if r[0] == "Dijaspora" else 1 + WORLD_FIRST.index(r[0]) if r[0] in WORLD_FIRST else 9
        return rank, -r[4].timestamp()

    last, cells, nepr_total, abroad = {}, {}, 0, {}
    for h, d in reversed(hours):  # oldest first
        nepr_total += len(d["nepr"])
        for r in reversed(d["dijaspora"]):  # newest figure per place wins
            abroad[r[0]] = r
        cells[h] = {"nepr_total": nepr_total,
                    "world": (sorted(abroad.values(), key=world_order), not d["dijaspora"])}
        for m, rows_of in metrics.items():
            rows = rows_of(d)
            cells[h][m] = (rows, False) if rows else (last.get(m, []), True)
            last[m] = cells[h][m][0]

    now = local(datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    out = []
    if not hours or hours[0][0] != now:
        out.append('<p class="wait">Čekamo nove podatke za %s, još uvek ih nema.%s</p>' % (
            span(now), " Ispod su poslednji podaci." if hours else ""))
    blocks = []
    for n, (h, d) in enumerate(hours):
        c, nepr = cells[h], d["nepr"]
        if nepr:
            nepr_txt = "Ažurirano %s<br>%s%s" % (hm(nepr[0]), link(nepr[0], e(nepr[0]["title"])),
                                                " · +%d još" % (len(nepr) - 1) if len(nepr) > 1 else "")
        else:
            nepr_txt = "Ukupno od %s: %d" % (SINCE.strftime("%H:%M"), c["nepr_total"])
        blocks.append('<details%s><summary>%s</summary><div class="ws">%s%s%s%s</div></details>' % (
            " open" if n == 0 else "", span(h),
            widget("Izlaznost Beograd", *turnout(c["Beograd"])),
            widget("Izlaznost dijaspora", *world(c["world"])),
            widget("Nepravilnosti", len(nepr), nepr_txt),
            "".join(widget("Izlaznost " + label, *turnout(c[city]))
                    for label, city in [("Niš", "Niš"), ("Novi Sad", "Novi Sad"), ("cela Srbija", "Srbija")])))
    out += blocks[:1]  # newest hour stays visible, the older ones fold into "Raniji podaci"
    if len(blocks) > 1:
        out.append('<details class="older"><summary>Raniji podaci</summary>%s</details>' % "".join(blocks[1:]))
    return ('<section class="sum"><h2>Pregled po satima</h2>%s<p class="note">Brojevi iz vesti, '
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
<meta http-equiv="refresh" content="300"><title>Izbori 2026</title><style>%s</style>
<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script></head>
<body><main><header><div class="top"><h1>Izbori 2026</h1>
<button id="theme" type="button" aria-label="Promeni temu"></button></div><p>Ažurirano %s · %d vesti%s</p></header>%s
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
