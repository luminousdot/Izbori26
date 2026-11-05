#!/usr/bin/env python3
"""Spin i realnost: what Vučić/SNS claim, next to what is reported on the same topic in the same days
(arrests, criminal complaints, resignations, actions of institutions first), plus what Studentska lista
does and says. Same sources as izbori.py, standard library only.

  python3 stanje.py           fetch once, write stanje.html, open it
  python3 stanje.py --watch   refresh every 5 minutes

Every tag below comes from words in the headline and its first lines, never from guessing who is
"behind" something: the page shows who speaks, who acts and who is mentioned, with the source.
"""
import html, re, sys, time, webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import izbori
from izbori import norm, local, safe, FEEDS

DAYS = 7  # how far back to look
# Read quietly like izbori's live pages; skipped without a note if it has no feed or fails.
EXTRA_FEEDS = [("Raspad sistema", "https://raspadsistema.com/feed/")]

# Sides, as regexes on lowercase Latin text without diacritics (č->c, š->s, ž->z, đ->dj).
SIDES = {
    "vucic": ("Vučić i SNS", r"\bvucic|\bsns\b|\bsns-|naprednja|srpsk\w* naprednj|\bmacut|\bdacic|\bsps\b|"
                            r"\bbrnabic|\bvulin|tehnickom mandatu|odlazec\w* vlad"),
    "sl": ("Studentska lista i studenti", r"studentsk\w* list|studenti pobedjuju|\bsrdanovic|\bstudent(?:i|e|ima)\b|\bstudenata\b"),
    "inst": ("Institucije", r"tuzilast|tuzil(?:ac|ica|ca)|\bvjt\b|\btok\b|polici|\bmup\b|\bsud\b|\bsuda\b|"
                           r"\bsudu\b|sudij|\bbia\b|\brik\b|ustavn\w* sud|zastitni\w* gradjana|agencij\w* za"),
}
# What happens. The first three are "raspad sistema"; the rest describe the new government and statements.
ACTIONS = {
    "hapsenje": ("Hapšenje", r"\buhaps|\bhapsen|\bhapsi|lisen\w* slobode|\bpritvor|\bpriveden|\bprivel|\bprivod"),
    "prijava": ("Krivična prijava", r"krivicn\w* prijav|optuznic|\bistrag|osumnjic|saslusan|saslusanj"),
    "ostavka": ("Ostavka", r"\bostavk|\bsmenjen|\bsmena\b|\bsmenu\b|razresen|povukao se|povukla se"),
    "vlast": ("Nova vlast", r"\bmandatar|imenovan|konstitutiv|nov\w* vlad|sastav vlade|koalicij|izabran\w* za"),
}
SYSTEM = ("hapsenje", "prijava", "ostavka")
SAYS = r"\b(?:izjavi|porucio|porucila|rekao|rekla|saopsti|kaze|tvrdi|optuzio|optuzila|najavio|najavila)\w*"
# Headlines put the subject first: "Vučić najavio...", "Studentska lista predložila...", "Brnabić: ..."
SUBJECT_WORDS = 4

# "Tvrdnja ↔ šta se dešava": a statement by Vučić/SNS next to news on the same topic from the same days.
# Same topic = shared word stems (first 6 letters, so "hapšenja"/"hapšenje" match) or the same kind of event.
# The page does not say who is right; it puts the two side by side.
PAIR_DAYS = 3
STOP = set("""srbij izbor vucic predse sns studen rekao rekla izjav poruci saopst danas godin posle protiv
nakon zbog kojeg kojih kojoj svoje svojim svega izmedj takod jedan jedna jos sada ovaj ovog ovoj nisu
biti bice bilo bila bili treba mogu moze kako kada gde zato samo vise manje velik novog nove novi""".split())

OUT = Path(__file__).resolve().with_name("stanje.html")
SIDE_RE = {k: re.compile(r) for k, (_, r) in SIDES.items()}
ACTION_RE = {k: re.compile(r) for k, (_, r) in ACTIONS.items()}


def classify(it):
    """Adds speaker, subject, mentioned sides and actions to a news item."""
    title, t = it["title"], norm(it["title"] + " " + it["snippet"])
    head = norm(title)
    m = re.match(r"^\s*([^:]{2,60}?):\s", title)  # "Vučić: ..." / "Ana Brnabić: ..."
    speaker = next((k for k, r in SIDE_RE.items() if m and r.search(norm(m.group(1)))), None)
    first = " ".join(head.split()[:SUBJECT_WORDS])
    subject = speaker or next((k for k, r in SIDE_RE.items() if r.search(first)), None)
    it.update(speaker=speaker, subject=subject,
              sides=[k for k, r in SIDE_RE.items() if r.search(t)],
              actions=[k for k, r in ACTION_RE.items() if r.search(t)],
              says=bool(speaker or re.search(SAYS, head)))
    return it


def stems(it):
    return {w[:6] for w in re.findall(r"[a-z]{5,}", norm(it["title"] + " " + it["snippet"])) if w[:6] not in STOP}


def is_event(it):  # something that happened, not a statement: an arrest, a complaint, a resignation, an institution
    return bool(set(it["actions"]) & set(SYSTEM)) or (it["subject"] == "inst" and not it["says"])


def is_claim(it):
    return it["speaker"] == "vucic" or (it["subject"] == "vucic" and it["says"])


def pairs(items, claim):
    """News on the same topic, not themselves Vučić/SNS statements, within PAIR_DAYS of the claim.
    Events (is_event) come before other reports at the same match."""
    mine, acts = stems(claim), set(claim["actions"])
    found = []
    for it in items:
        if it is claim or is_claim(it) or abs(it["when"] - claim["when"]) > timedelta(days=PAIR_DAYS):
            continue
        score = len(mine & stems(it)) + 2 * len(acts & set(it["actions"]))
        if score >= 2:
            found.append((score + is_event(it), it))
    found.sort(key=lambda x: (-x[0], -is_event(x[1]), -x[1]["when"].timestamp()))
    return [it for _, it in found[:3]]


def collect():
    since = datetime.now(timezone.utc) - timedelta(days=DAYS)
    feeds = FEEDS + EXTRA_FEEDS
    items, failed = [], []
    with ThreadPoolExecutor(len(feeds)) as pool:
        for feed, res in zip(feeds, pool.map(lambda f: safe(izbori.fetch, f), feeds)):
            if res is None:
                if feed not in EXTRA_FEEDS:
                    failed.append(feed[0])
            else:
                items += res
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i["when"], reverse=True):
        t = norm(it["title"] + " " + it["snippet"])
        if it["when"] < since or it["link"] in seen or not it["link"].startswith("http"):
            continue
        if any(c in izbori.DROP_CATEGORIES for c in it["cats"]) or izbori.EXCLUDE_PATTERN.search(t):
            continue  # world news
        it = classify(it)
        if it["subject"] or it["sides"] or it["actions"]:
            seen.add(it["link"])
            out.append(it)
    return out, failed


CSS = izbori.CSS + """
.cols{display:grid;grid-template-columns:1fr;gap:12px;margin:12px 0}
@media (min-width:720px){.cols{grid-template-columns:1fr 1fr}main{max-width:1000px}}
.col{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.col h2{margin:0 0 4px;font-size:1.05rem;display:flex;justify-content:space-between;gap:8px}
.col h2 span{color:var(--muted);font-weight:400;font-size:.85rem}
.col ul{list-style:none;margin:0;padding:0}.col li{padding:8px 0;border-top:1px solid var(--line)}
.col li:first-child{border-top:0}.col li a{color:var(--fg);font-weight:600;text-decoration:none}
.col li a:hover,article a:hover{text-decoration:underline}
.tag{display:inline-block;font-size:.72rem;line-height:1.5;padding:0 7px;border-radius:999px;margin:0 4px 0 0;
border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.tag.hapsenje,.tag.prijava,.tag.ostavka{color:var(--accent);border-color:var(--accent)}
.tag.who{color:var(--fg);font-weight:600}
.counts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0}
.counts div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.counts b{display:block;font-size:1.6rem;color:var(--accent);line-height:1.2}
.counts span{font-size:.75rem;color:var(--muted)}
.f{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.f button{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--chip);color:var(--fg);
border-radius:999px;padding:4px 12px;cursor:pointer}.f button.on{background:var(--fg);color:var(--bg)}
.nav{font-size:.9rem}.nav a{color:var(--muted)}
h3.sec{font-size:1.05rem;margin:18px 0 6px}
.pair{display:grid;grid-template-columns:1fr;border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:10px}
@media (min-width:720px){.pair{grid-template-columns:1fr 1.3fr}}
.claim{background:var(--chip);padding:10px 14px}.facts{background:var(--card);padding:10px 14px}
.claim a,.facts a{color:var(--fg);font-weight:600;text-decoration:none}.claim p{margin:4px 0 0;color:var(--muted);font-size:.9rem}
.lbl{font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:700;margin-bottom:2px}
.facts ul{list-style:none;margin:0;padding:0}.facts li{padding:6px 0;border-top:1px solid var(--line)}
.facts li:first-child{border-top:0}.none{color:var(--muted);font-size:.9rem}
.ev{color:var(--accent);font-weight:600}
"""

FILTER_JS = """
document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{
 b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
 const v=b.dataset.v;document.querySelectorAll('#system article').forEach(a=>
  a.hidden=!!v&&!a.dataset.tags.split(' ').includes(v));});
"""


def tags(it, show_subject=False):
    e = html.escape
    out = []
    if it["speaker"]:
        out.append('<span class="tag who">govori: %s</span>' % e(SIDES[it["speaker"]][0]))
    elif show_subject and it["subject"]:
        out.append('<span class="tag who">%s</span>' % e(SIDES[it["subject"]][0]))
    out += ['<span class="tag %s">%s</span>' % (a, e(ACTIONS[a][0])) for a in it["actions"]]
    mentioned = [s for s in it["sides"] if s not in (it["speaker"], it["subject"])]
    if mentioned and set(it["actions"]) & set(SYSTEM):
        out.append('<span class="tag">pominje: %s</span>' % e(", ".join(SIDES[s][0] for s in mentioned)))
    elif it["says"] and not it["speaker"]:
        out.append('<span class="tag">izjava</span>')
    return "".join(out)


def render(items, failed):
    e = html.escape
    now = local(datetime.now(timezone.utc))
    when = lambda it: izbori.fmt_time(it["when"], now.date())
    link = lambda it: '<a href="%s" target="_blank" rel="noopener">%s</a>' % (e(it["link"]), e(it["title"]))

    def column(side):
        mine = [it for it in items if it["subject"] == side]
        lis = "".join('<li><div class="meta"><b>%s</b> · %s</div>%s<div>%s</div></li>' % (
            e(it["outlet"]), when(it), link(it), tags(it)) for it in mine[:12])
        return '<section class="col"><h2>%s<span>%d vesti</span></h2><ul>%s</ul></section>' % (
            SIDES[side][0], len(mine), lis or "<li>Nema vesti.</li>")

    system = [it for it in items if set(it["actions"]) & set(SYSTEM)]

    def card(claim):
        rel = pairs(items, claim)
        facts = "".join('<li><div class="meta"><b>%s</b> · %s%s</div>%s<div>%s</div></li>' % (
            e(it["outlet"]), when(it), ' · <span class="ev">događaj</span>' if is_event(it) else "",
            link(it), tags(it, True)) for it in rel)
        return ('<div class="pair"><div class="claim"><div class="lbl">Spin · šta tvrdi</div>'
                '<div class="meta"><b>%s</b> · %s</div>%s<p>%s</p></div>'
                '<div class="facts"><div class="lbl">Realnost · šta se desilo / izveštava</div><ul>%s</ul></div></div>') % (
            e(claim["outlet"]), when(claim), link(claim), e(claim["snippet"][:160]),
            facts or '<li class="none">Nema drugih vesti na istu temu u ovim danima.</li>')

    claims = [it for it in items if is_claim(it)]
    events = [it for it in items if is_event(it)]
    day = datetime.now(timezone.utc) - timedelta(days=1)
    top = "".join('<div><b>%d</b><span>%s · 24 h<br>%d za %d dana</span></div>' % (
        sum(1 for it in lst if it["when"] >= day), lbl, len(lst), DAYS)
        for lbl, lst in (("Izjave vlasti", claims), ("Događaji", events),
                         ("Bez odgovora", [c for c in claims if not pairs(items, c)])))
    counts = "".join('<div><b>%d</b><span>%s · 24 h<br>%d za %d dana</span></div>' % (
        sum(1 for it in system if a in it["actions"] and it["when"] >= day), ACTIONS[a][0],
        sum(1 for it in system if a in it["actions"]), DAYS) for a in SYSTEM)
    chips = '<button class="on" data-v="">Sve</button>' + "".join(
        '<button data-v="%s">%s</button>' % (k, e(v[0])) for k, v in list(ACTIONS.items())[:3]) + "".join(
        '<button data-v="%s">%s</button>' % (k, "pominje: " + e(v[0])) for k, v in SIDES.items() if k != "inst")
    rows = "".join(
        '<article data-tags="%s"><div class="meta"><b>%s</b> · %s</div>%s<div>%s</div></article>\n' % (
            " ".join(it["actions"] + it["sides"]), e(it["outlet"]), when(it), link(it), tags(it, True))
        for it in system)
    fail = '<p class="fail">%s</p>' % " · ".join(e(n) + ": failed" for n in failed) if failed else ""
    return """<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300"><title>Spin i realnost</title><style>%s</style>
<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script></head>
<body><main><header><div class="top"><h1>Spin i realnost</h1>
<div class="btns"><button id="reload" type="button" aria-label="Osveži" title="Osveži">&#x21BB;</button>
<button id="theme" type="button" aria-label="Promeni temu"></button></div></div>
<p>Ažurirano %s · poslednjih %d dana · <span class="nav"><a href="izbori.html">Izbori 2026 ›</a></span></p></header>%s
<div class="counts">%s</div>%s
<h3 class="sec">Ko šta radi</h3><div class="cols">%s%s</div>
<h3 class="sec">Raspad sistema: hapšenja, prijave, ostavke</h3>
<div class="counts">%s</div><div class="f">%s</div><div id="system">%s</div>
<p class="note" style="color:var(--muted);font-size:.8rem">Uz svaku izjavu Vučića i SNS-a stoje vesti iz istih
dana sa istim rečima ili istom vrstom događaja, prvo događaji (hapšenja, prijave, ostavke, radnje institucija).
Stranica ih stavlja jedno pored drugog, ne presuđuje svaku izjavu: pročitaj obe strane. „Bez odgovora“ su izjave
uz koje nema vesti na istu temu. Izvori su nezavisni mediji. Oznake su automatske, po rečima iz naslova:
ko govori, koje radnje i koje strane se pominju. Ne govore ko „stoji iza“ nečega: to proveri u samoj vesti.
Isti događaj često prenosi više medija, pa brojevi broje vesti, ne događaje.</p>
</main><script>%s%s</script></body></html>""" % (
        CSS, now.strftime("%d.%m.%Y. %H:%M"), DAYS, fail,
        top, "".join(card(c) for c in claims[:30]) or '<p class="none">Nema izjava u poslednjih %d dana.</p>' % DAYS,
        column("vucic"), column("sl"), counts, chips,
        rows or "<p>Nema vesti.</p>", izbori.JS, FILTER_JS)


def run():
    items, failed = collect()
    OUT.write_text(render(items, failed), encoding="utf-8")
    print("%s  %d items, %d feeds failed -> %s" % (time.strftime("%H:%M"), len(items), len(failed), OUT))


def main():
    run()
    webbrowser.open(OUT.as_uri())
    while "--watch" in sys.argv:
        time.sleep(izbori.WATCH_SECONDS)
        try:
            run()
        except Exception as e:
            print("round failed:", e, file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
