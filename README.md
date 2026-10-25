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

## Sources (RSS, all checked working on 2026-10-25)

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

birn.rs has no feed. No separate feed found for TV Nova / Nova S; nova.rs covers it.
