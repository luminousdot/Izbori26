# Izbori

Private, super-simple news reader for following the Serbian elections (25 Oct 2026).
For personal use only: shows headline, outlet, time and link. No full-text archiving.

## Usage

Needs only macOS system Python 3 (3.9+), with nothing to install.

```sh
python3 izbori.py           # fetch once, write izbori.html, open it in the browser
python3 izbori.py --watch   # same, every 5 minutes (the open tab reloads itself)
python3 izbori.py --all     # every item, without the election filter
```

To change the election keywords, edit `KEYWORDS` at the top of `izbori.py`.

## On your phone (Vercel)

1. Go to https://vercel.com/new and sign in with GitHub.
2. Import `luminousdot/Izbori26`. Leave every setting as it is and press **Deploy**.
3. Open the `….vercel.app` link on your phone. Add `?all` to the link to see every item.

Shows only news from 25 Oct, 06:00 onwards (`SINCE` in `izbori.py`). The page is rebuilt from the feeds at most every 2 minutes and reloads itself every 5.
Other countries' elections (e.g. Bulgaria) are filtered out: see `EXCLUDE` in `izbori.py`.

Above the news, **Pregled po satima** sums up each hour in six small widgets with a big number: turnout in
Beograd, the diaspora, Niš, Novi Sad and all of Serbia, plus irregularities. The numbers are taken from the articles
(each linked) and never estimated, so the summary is only as complete as the news. The diaspora widget lists Berlin, London and New York
first, then any other world city in the news. To add cities or words, edit `CITIES`, `WORLD`,
`TURNOUT`, `DIASPORA` and `IRREGULAR` in `izbori.py`.
The link is public, but nobody will find it unless you share it.
Files: `api/index.py` and `vercel.json`.

## Sources (RSS)

| Outlet | Feed |
|---|---|
| KRIK | https://www.krik.rs/feed/ |
| CINS | https://www.cins.rs/feed/ |
| BIRN (Balkan Insight, Serbia) | https://balkaninsight.com/category/bi/balkans/serbia/feed/ |
| Radar | https://radar.nova.rs/feed/ |
| N1 | https://n1info.rs/feed/ |
| Nova / Nova S | https://nova.rs/feed/ |
| Insajder | https://insajder.net/feed |
| Danas | https://www.danas.rs/feed/ |
| Mašina | https://www.masina.rs/feed/ |
| Južne vesti (Niš) | https://www.juznevesti.com/feed/ (added 25 Oct, not yet checked) |
| Nedeljnik | https://www.nedeljnik.rs/feed/ (added 25 Oct, not yet checked) |

birn.rs has no feed. No separate feed found for TV Nova / Nova S; nova.rs covers it.
