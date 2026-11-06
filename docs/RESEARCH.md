# The 50-website study

The project has two halves that share one classifier and one argument —
*hashing is not anonymisation*, read through APP 8:

1. **The product:** DataExodus Box. Anyone can try it with their own phone over
   the Pi's Wi-Fi. See [HOTSPOT.md](HOTSPOT.md).
2. **The study:** measure 50 websites from a list frozen in week 1
   (`data/sites.yaml`) — five sectors, ten sites each: government, health,
   education, news media, ecommerce.

## Research questions

| | Question | Tool | Results land in |
| --- | --- | --- | --- |
| RQ1 | How many third parties and trackers does each of the 50 homepages contact? Which companies are behind them? Which countries are their servers in? Does it differ by sector? | the study crawler (`dataexodus-study`) | `/var/lib/dataexodus/runs/<UTC timestamp>/report/report.md`, `audit/audit.html` |
| RQ2 | Where does the product's own scorer put these 50 legitimate sites, and how often does it cry **"Dangerous"** on one? | `analysis/score_sites.py` | `summary.md`, `scores.csv` |
| Experiment | A hashed email is still an identifier, and still links across sites (controlled lab, synthetic identity) | `examples/run_local_lab.py` | `docs/evidence/local-lab-browser.json` |

## Measurement protocol

Record this verbatim with the results — a number without its protocol is not a
measurement.

- **Device:** Raspberry Pi 5, 4 GB, Debian 13 (Raspberry Pi OS), the OS's own
  headless Chromium driven by Playwright, running as the `dataexodus` account
  behind its own firewall rules.
- **DNS:** 1.1.1.1 and 1.0.0.1 (Cloudflare), set for every network in
  `/etc/NetworkManager/conf.d/90-dataexodus-dns.conf`. **Why it is pinned:** a
  home router's DNS answered `10.10.10.1` for tracker domains, which silently
  removed them from the data. Every run records the resolver it used in
  `status.json`, and the dashboard shows it in the *DNS used* column.
- **Per site:** open the homepage, wait for `DOMContentLoaded`, stay 8 seconds,
  time out at 30. No cookie banner clicked, no login, no forms filled. A fresh
  browser per site, keeping the headless browser's own user agent — it does not
  pretend to be a person. A site that blocks automated browsers is recorded as a
  failure.
- **Reference data:** EasyPrivacy, DuckDuckGo Tracker Radar, GeoLite2-Country.
  These files are held fixed between runs, or the runs are not comparable.
- **Also recorded:** date and time, which network (home Wi-Fi or 4G), and
  location, for example Sydney. Location and carrier change which CDN edge
  answers, and therefore which country the servers appear to be in.

## Running it

**RQ1 — crawl the 50 sites** (15–20 minutes), in a shell on the Pi:

```bash
sudo systemctl start dataexodus-study                    # one run, now
sudo tail -f /var/lib/dataexodus/runs/*/crawl.log        # progress; Ctrl+C to leave
ls /var/lib/dataexodus/runs/*/raw | wc -l                # or: sites finished so far (max 50)
cat /var/lib/dataexodus/runs/*/status.json               # ok: true when it is done
```

Results appear on the dashboard (`http://127.0.0.1:8020`, through the tunnel).
From the second run onwards it compares itself against the previous one. Use at
least **two or three runs on different days** before drawing anything from the
numbers. To have the Pi run it every Sunday:

```bash
sudo systemctl enable --now dataexodus-study.timer
```

Only enable the timer while the Pi is on a wired or home network — each run
pulls a few hundred megabytes, which is expensive over a phone's tethered
connection.

**RQ2 — score the 50 sites** (about 5 minutes):

```bash
cd /opt/dataexodus
export DATAEXODUS_GUARD_TOKEN="$(grep '^DATAEXODUS_GUARD_TOKEN=' /etc/dataexodus/dataexodus.env | cut -d= -f2-)"
.venv/bin/python -m analysis.score_sites --out ~/site-scores-$(date +%Y%m%d)
```

**Copy the results back** (PowerShell on the laptop; replace `<run>` with the
directory name, for example `20261027T1404Z`):

```powershell
scp -r admin@192.168.0.83:/var/lib/dataexodus/runs/<run>/report admin@192.168.0.83:/var/lib/dataexodus/runs/<run>/audit C:\DataExodus\reports\pi-study-<run>\
scp -r admin@192.168.0.83:~/site-scores-* C:\DataExodus\reports\
```

Leave the raw data (`raw/`, `study.duckdb`) on the Pi. It holds every URL that
was recorded, and the reports do not need it.

## Reporting the results

- **Method:** the protocol above, the 50-site list, and the crawl success rate
  (in `status.json` and `crawl.log`).
- **RQ1:** per sector — share of requests going to trackers, number of third
  parties, the companies behind the most of them, share of servers outside
  Australia, use of fingerprinting APIs. These are descriptive tables, **not**
  statistical tests.
- **RQ2:** how many sites landed in Low / Be careful / Dangerous, how many were
  false alarms, and which rules pushed scores up most. Say plainly what "Be
  careful" means on a legitimate site: it tracks heavily, not that it is
  malicious.
- **The link back to the product:** the trackers and companies that show up most
  in RQ1 are exactly what *Block known trackers* refuses on the DataExodus
  Wi-Fi (`pi/dns_trackers.txt`).

## Run 1 (pilot, 28 October 2026)

Full numbers: `docs/evidence/research-run1/README.md`.

- **Coverage (RQ1):** 34 sites captured in full, 2 partially, 14 failed. Most
  failures were bot protection serving a block page to an automated browser
  (ATO, Home Affairs, news.com.au, Woolworths, several universities). **No
  attempt was made to get around it.** RQ1's conclusions therefore apply to the
  sites that were captured, and the coverage is reported as it is. That is
  itself a methodological finding worth writing up.
- **RQ1:** 5,166 requests recorded — 3,542 to third parties, 776 to listed
  trackers.
  - Highest share of tracker requests: health (17%) and education (17%).
  - Google Analytics / Tag Manager present on 28 sites.
  - Microsoft Clarity (session recording) on 7 sites, two of them government.
  - TikTok analytics on 5 sites, including healthdirect.gov.au and Medibank.
- **RQ2:** 49 of 50 sites scored. **No legitimate site was rated "Dangerous".**
  28 Low risk, 21 Be careful — mostly for trackers and offshore servers. 48 of
  49 had third-party servers outside Australia.
- **What the study changed in the product:** the "scam wording" rule misfired on
  9 sites, because common phrases like "gift card" (6 retail and insurance
  sites) and "act now" (Home Affairs) tripped it. The rule now needs one strong
  phrase or two weak ones. Rescored: 31 Low, 18 Be careful, 0 Dangerous. This
  has to be stated honestly — the rule was tuned on these same 50 sites, so the
  rescore is not an independent test of it.

## Limits

- Homepages only, one anonymous visit, no cookie consent clicked. Inner pages
  and signed-in users may look different.
- The crawler fills no forms, so it cannot observe a user's email being sent
  from these 50 sites. The "a hash is not anonymity" claim rests on the
  controlled lab experiment instead.
- Country is a GeoIP estimate of a server address. It does not say where data is
  stored, so on its own it does not establish an APP 8 breach.
- Tracker labels come from public lists. A domain not on a list is counted as
  unknown, not as clean.
- RQ2 measures false alarms on legitimate sites only. Measuring whether the
  scorer **catches** real phishing needs a labelled set of phishing links, and
  that has not been done.
