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

Shows only today's items (Belgrade time). The page is rebuilt from the feeds at most every 2 minutes and reloads itself every 5.
Other countries' elections (e.g. Bulgaria) are filtered out: see `EXCLUDE` in `izbori.py`.
The link is public, but nobody will find it unless you share it.
Files: `api/index.py` and `vercel.json`.

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
