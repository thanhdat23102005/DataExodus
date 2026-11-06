# DataExodus Box

A Raspberry Pi 5 privacy box that someone can try with their own phone. They
join the box's Wi-Fi, the welcome page opens by itself (captive portal), and
from there they can check a suspicious link without their phone ever loading it.

```
 visitor's phone ──Wi-Fi "DataExodus-Box"──> Raspberry Pi 5 ──Ethernet / USB tethering──> internet
   captive portal http://10.42.0.1             sandbox Chromium: link check + Safe Browse
   (check a link · Safe Browse · My device)    nftables: the sandbox cannot reach the LAN or any phone
                                               DNS watch: per-device consent and blocking
 laptop (Chrome/Edge + Guard) ──SSH tunnel──>  127.0.0.1:8010 sandbox API · 127.0.0.1:8020 dashboard + QR card
```

| Feature | What it does |
| --- | --- |
| **Check a link** | Paste a link, or a whole scam text or email. The Pi opens it in an isolated, throwaway Chromium and shows a 0–100 score with every reason (credential form posting to another site, forced download, clipboard write, notification request, lookalike brand, URLhaus listing, trackers, servers outside Australia…), the redirect chain, a screenshot and a clean link without click IDs. The phone never loads the page. |
| **Safe Browse** | Use the suspicious page on the Pi by tapping its picture: scroll, type, go back. The page runs on the Pi; the phone only receives JPEG images. |
| **My device** (opt-in) | Which companies the phone's apps contact and where their servers are. One switch blocks trackers for that phone only; *Forget this device* deletes everything. |
| **Guard 0.5** (Chrome/Edge, `guard/`) | On the laptop: identifier URLs blocked before they leave, learned rules after a POST, ad clicks held in quarantine and scored by the Pi's sandbox, clean links, X-Ray view. |
| **Sample links** | Four fictional sites served by the Pi (news article, ad click, fake bank sign-in, fake CAPTCHA), so the checker can be demonstrated without internet and without visiting real scams. |

---

## Install

Python 3.10 or newer. Run these from the project folder.

```bash
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1          # Windows PowerShell
```

```bash
source .venv/bin/activate           # Linux / macOS / WSL
```

```bash
python -m pip install -r requirements.txt -c requirements-tested.txt
python -m playwright install chromium
```

`requirements-tested.txt` pins the versions I actually tested against. It is a
constraint file, not a full lockfile.

For reference data (EasyPrivacy, DuckDuckGo Tracker Radar, URLhaus):

```bash
python setup_data.py
```

That one needs network access. For server-country estimates, put your own
licensed `GeoLite2-Country.mmdb` in `data/blocklists/`. Never put a MaxMind
licence key in a report or a commit.

## Run

### The whole visitor flow on one PC, no Pi

```bash
python -m examples.run_box_acceptance --out reports/box-run
```

This starts the portal and the sample sites on loopback addresses and walks the
flow end to end — check a link, the four sample verdicts, Safe Browse, opt-in
DNS logging, per-device blocking. It writes a JSON result and screenshots. Use
it to see the product working before touching the hardware.

### On the Raspberry Pi

Full steps, including the Wi-Fi access point: **[docs/RASPBERRY_PI_VI.md](docs/RASPBERRY_PI_VI.md)**,
then **[docs/HOTSPOT_VI.md](docs/HOTSPOT_VI.md)**.

```bash
cd ~/DataExodus
sudo bash pi/install.sh --hotspot     # add --study for the weekly research timer
```

The Pi prints a card with both QR codes at `http://127.0.0.1:8020/card`. What a
visitor does with their phone: **[docs/TRY_IT.md](docs/TRY_IT.md)**. Demo-day
checklist and what to do when the Wi-Fi misbehaves:
**[docs/TAFE_DEMO_VI.md](docs/TAFE_DEMO_VI.md)**.

### Guard in Chrome or Edge

Load `guard/` unpacked, then point it at the sandbox service — on this computer
or on the Pi through an SSH tunnel (`pi\connect-pi.ps1`). Full steps:
**[docs/GUARD_QUICKSTART_VI.md](docs/GUARD_QUICKSTART_VI.md)**.

The older research collector extension is still in `extension/`. Do not run it
and Guard at the same time; their measurements get mixed together.

### The live research agent

```bash
uvicorn pipeline.agent:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for its dashboard, then load `extension/`
unpacked in Chrome or Edge. The extension batches request events to the local
agent, which classifies them as they arrive. It binds to loopback only and
refuses cross-site callers. This is a local demonstration: there is no
authentication, encryption at rest or retention policy, so it is not something
to point at anyone else's browsing.

### The controlled demo, with no browser at all

```bash
python -m analysis.demo
```

Opens as `reports/demo/audit.html`. It runs on generated fixtures, not real
website traffic, and works offline. Expected: 10 requests before and 6 after,
4 identifier matches before and 0 after, 4 high-priority findings before and 0
after. "Not observed" describes that capture, not a permanent fix.

### A real local browser capture

```bash
python -m examples.run_local_lab --out reports/local-lab-run1
```

Two loopback test sites and a loopback collector, loaded by the real Playwright
crawler. The identifier-sending integration is removed for the second phase and
the two captures are compared. `collector_receipts.json` records what actually
arrived at the collector. The identifier is synthetic. The output directory must
be new, so earlier evidence stays intact; the lab uses ports 8765–8767, and
`--port 8865` moves it.

## Tests

```bash
python -m pytest tests/ -q     # 216 tests
node --test tests/*.cjs        # 50 tests; 9 of them need "npm install jsdom"
```

These are the two commands CI runs.

## The research component

The 50-website study runs on the Pi: RQ1 measures trackers, third parties and
server countries across a frozen site list; RQ2 runs the product's own link
checker over the same legitimate sites to count false alarms. Protocol and
commands: **[docs/RESEARCH_VI.md](docs/RESEARCH_VI.md)**.

Capturing a site you are authorised to test, and the before/after retest:

```bash
python -m crawler.crawl --url https://your-authorised-site.example --output data/capture-before
python -m pipeline.process --raw data/capture-before --db data/capture-before.duckdb
python -m analysis.audit --db data/capture-before.duckdb --out reports/before
```

Change the responsible tag or SDK on your own staging site, capture again into a
new raw directory, then pass `--baseline reports/before/audit.json` to the
second audit. Databases are rebuilt from their raw directory, so re-running does
not double-count. Keep the raw files — they are the evidence.

The crawler does not fill forms, log in, or dismiss cookie banners, and it does
not pretend to be a human user. A site that blocks it is recorded as a failure,
not worked around.

## What is verified, and what is not

**Verified:** 216 Python and 50 JavaScript tests pass. A real Chromium run of
the visitor flow passed 19/19 checks on loopback addresses
(`docs/evidence/box-v05-acceptance.json`, screenshots in
`docs/evidence/box-v05/`). Guard 0.5.1 passed its own real-browser acceptance
and closed the pop-under ads of a real site that went around its in-page popup
hook. On a real Raspberry Pi 5 (Debian 13, 4 GB) the installer, services,
firewall, sandbox scoring (same scores as on Windows, 3.6–5.3 s per link) and
Safe Browse all worked (`docs/evidence/pi-hardware-verification.txt`).

**Not verified:** the Wi-Fi access point and captive-portal pop-ups on real
iPhone and Android phones — that needs an Ethernet or USB-tethering uplink. No
precision/recall figure for the score against a labelled set of real phishing
links. No live Web Risk calls.

Every number above, what it was measured on, and what it does not prove:
**[docs/VALIDATION.md](docs/VALIDATION.md)**. The recorded runs behind them are
in `docs/evidence/`.

A low score is never presented as "safe". The sandbox sees one anonymous visit,
and a page that detects it can behave differently.

## Licence and attribution

Coursework for TAFE NSW Higher Education. The code here is mine. The reference
data is not: EasyPrivacy, URLhaus, DuckDuckGo Tracker Radar and MaxMind
GeoLite2 each carry their own licence and attribution terms, and anyone reusing
this project needs to read those first.
