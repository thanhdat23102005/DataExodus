# DataExodus Box

**A Raspberry Pi 5 privacy box that a visitor can try with their own phone.** The visitor joins the box's Wi-Fi and the welcome page opens by itself (captive portal). From there:

| Feature | What it does |
| --- | --- |
| **Check a link** | Paste a link, or a whole scam text or email. The Pi opens it in an isolated, throwaway Chromium and shows a 0–100 score with every reason (credential form posting to another site, forced download, clipboard write, notification request, lookalike brand, URLhaus listing, trackers, servers outside Australia…), the redirect chain, a screenshot and a clean link without click IDs. The phone never loads the page. |
| **Safe Browse** | Use the suspicious page on the Pi by tapping its picture: scroll, type, go back. The page runs on the Pi; the phone only receives JPEG images. |
| **My device** (opt-in) | Which companies the phone's apps contact and where their servers are. One switch blocks trackers for that phone only; *Forget this device* deletes everything. |
| **Guard 0.5** (Chrome/Edge, `guard/`) | On the laptop: identifier URLs blocked before they leave, learned rules after a POST, ad clicks held in quarantine and scored by the Pi's sandbox, clean links, X-Ray view. |
| **Sample links** | Four fictional sites served by the Pi (news article, ad click, fake bank sign-in, fake CAPTCHA), so the checker can be demonstrated without internet and without visiting real scams. |

```
 visitor's phone ──Wi-Fi "DataExodus-Box"──> Raspberry Pi 5 ──Ethernet / USB tethering──> internet
   captive portal http://10.42.0.1             sandbox Chromium: link check + Safe Browse
   (check a link · Safe Browse · My device)    nftables: the sandbox cannot reach the LAN or any phone
                                               DNS watch: per-device consent and blocking
 laptop (Chrome/Edge + Guard) ──SSH tunnel──>  127.0.0.1:8010 sandbox API · 127.0.0.1:8020 dashboard + QR card
```

| Start here | |
| --- | --- |
| Set up the Pi | [docs/RASPBERRY_PI_VI.md](docs/RASPBERRY_PI_VI.md), then the Wi-Fi: [docs/HOTSPOT_VI.md](docs/HOTSPOT_VI.md) (`sudo bash pi/install.sh --hotspot`) |
| What the assessor does | [docs/TRY_IT.md](docs/TRY_IT.md); the Pi prints a card with both QR codes at `http://127.0.0.1:8020/card` |
| Guard on the laptop | [docs/GUARD_QUICKSTART_VI.md](docs/GUARD_QUICKSTART_VI.md) |
| The whole visitor flow on one Windows PC, no Pi | `python -m examples.run_box_acceptance --out reports/box-run` |

The thesis from the research stays: *hashing is not anonymisation*, and data leaving Australia is shown, with its limits (APP 8).

**Verified (28 October 2026):** 224 Python and 50 JavaScript tests pass. A real Chromium run of the visitor flow passed 19/19 checks on loopback addresses: captive check, the four samples rated low / be careful / dangerous / dangerous, a pasted scam text, Safe Browse tapping a field, typing and submitting the fake bank form inside the sandbox, opt-in DNS logging, per-device blocking, Forget this device, refusal of cross-site posts and foreign Host headers (`docs/evidence/box-v05-acceptance.json`, screenshots in `docs/evidence/box-v05/`). Guard 0.5.1 passed its own real-browser acceptance, and closed the pop-under ads of a real site that went around its in-page popup hook (`CHANGES_FINAL.md`). On a real Raspberry Pi 5 (Debian 13, 4 GB) the installer, services, firewall, sandbox scoring (same scores as on Windows, 3.6–5.3 s per link) and Safe Browse were verified (`docs/evidence/pi-hardware-verification.txt`). **Not yet verified:** the Wi-Fi access point and captive-portal pop-ups on real iPhone/Android phones (needs an Ethernet or USB-tethering uplink); live Gemini / Web Risk calls.

---

# Research component: the 50-website study

The research stays part of the project, run on the Pi: RQ1 measures the trackers, third parties and server countries of the frozen 50-site list (`dataexodus-study`); RQ2 runs the product's link checker over the same legitimate sites to count false alarms (`python -m analysis.score_sites`); a controlled lab shows that a hashed email remains an identifier. Protocol, commands and reporting: [docs/RESEARCH_VI.md](docs/RESEARCH_VI.md). Everything below documents the underlying research and audit toolkit. On the Pi the weekly timer is enabled with `sudo bash pi/install.sh --study`; a single run is `sudo systemctl start dataexodus-study`.

The research collector extension remains at `extension/`; do not run it and Guard at the same time. Guard evidence exports become reports with `python -m analysis.guard_report --events path/to/export.json`; audit domain rules can be exported for Guard with `python -m protection.export_rules`. No AI output changes enforcement.

A local website privacy audit prototype: identify supported tracker destinations, match configured test identifiers in raw or hashed form, explain the evidence, and compare a retest after a website change.

The academic study and the product prototype share the same rule-based classifier. The proposed first users are small web agencies and website developers. Customer demand has not yet been validated.

## Start with the working controlled demo

Run these commands from the extracted project directory. Python 3.10+ is required.

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS / WSL
source .venv/bin/activate
```

Then:

```bash
python -m pip install -r requirements.txt -c requirements-tested.txt
python -m pytest tests/ -q
python -m analysis.demo
```

Open `reports/demo/audit.html` in your browser. This standalone report also works without an internet connection. It uses **generated fixtures**, not public website traffic. No browser installation is required for this first demo.

Expected results:

| Measure | Before | After |
| --- | ---: | ---: |
| Fictional sites | 2 | 2 |
| Requests | 10 | 6 |
| Requests matching configured identifiers | 4 | 0 |
| Tracker requests | 4 | 0 |
| High-priority findings | 4 | 0 |

Six aggregated findings (including two medium-priority tracker findings) are not observed in the retest. “Not observed” describes that capture, not a permanent fix.

## Then verify a real local browser capture

```bash
python -m playwright install chromium
python -m examples.run_local_lab --out reports/local-lab-run1
```

On Linux, Playwright may also need OS libraries; follow the dependency message from its installer. On Windows use the activated environment above.

The lab starts two loopback-only test sites and a loopback collector, loads them with the actual Playwright crawler, removes the identifier-sending integration for the second phase, and creates a comparison report. `collector_receipts.json` records receipt at the local collector. The identifier is synthetic. These captures belong to the controlled lab, not the 50-site study.

The output directory must be fresh so previous evidence stays intact. The lab uses ports 8765–8767; pass `--port 8865` if those are occupied. Plain HTTP is intentional inside this loopback lab and will appear as an HTTP finding.

To inspect the local page yourself instead:

```bash
python -m examples.demo_lab --phase before
```

Open the two local URLs printed by the command and inspect the browser Network panel. Stop it with Ctrl+C. Run again with `--phase after` to inspect the changed version.

**Verified 23 October 2026:** this lab was run with Playwright Chromium on Windows: the collector received the synthetic hash from both sites before the change and nothing after it, and the audit classified the retest as comparable (docs/evidence/local-lab-browser.json). Run it on your own machine as well and keep that run's receipts as your evidence.

## Capture a website you are authorised to test

```bash
python setup_data.py
python -m crawler.crawl --url https://your-authorised-site.example --output data/capture-before
```

`setup_data.py` downloads EasyPrivacy and Tracker Radar and requires network access. For destination estimates, put your own licensed `GeoLite2-Country.mmdb` in `data/blocklists/`. Existing local copies can be reused. Do not put a license key into a shared report.

Copy `data/identities.example.yaml` to `data/identities.local.yaml`, and configure a dedicated test identity locally if needed. An empty identity file is allowed, but it cannot establish the absence of identity leakage. Merely configuring an email does not cause the website to know or transmit it; the tested journey must actually use the identity on a site you control or are authorised to test. The crawler does not enter forms or log in.

```bash
python -m pipeline.process --raw data/capture-before --db data/capture-before.duckdb
python -m analysis.audit --db data/capture-before.duckdb --out reports/before
```

Change the responsible tag, plugin or SDK on your own staging website, repeat the same capture protocol into a new raw directory, then:

```bash
python -m pipeline.process --raw data/capture-after --db data/capture-after.duckdb
python -m analysis.audit --db data/capture-after.duckdb --baseline reports/before/audit.json --out reports/after
```

Both databases are rebuilt transactionally from their specified raw directories. Re-running processing does not double counts. CSV/XLSX exports are automatic; `--skip-export` disables them. Keep raw files as the evidence source.

## Run the academic study

```bash
python -m crawler.crawl --sector government --output data/study-pilot
python -m crawler.crawl --output data/study-run1
python -m pipeline.process --raw data/study-run1 --db data/study-run1.duckdb
python -m analysis.report --db data/study-run1.duckdb --out reports/study-run1
```

The frozen list actually contains government, health, education, news_media and ecommerce. Some health entries are international websites. Describe the sample as the selected website list rather than claiming every site is an Australian organisation. Do not change the frozen sample without recording a protocol amendment.

Reports contain descriptive tables and an audit. Statistical hypothesis tests, policy comparisons and the final study findings still need to be completed and justified using the actual evidence.

## Live mode

```bash
uvicorn pipeline.agent:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. In Chrome/Edge, open the extensions page, enable Developer mode and load the `extension/` folder. The extension combines request phases by requestId and sends batches to the local agent. Pause clears unsent in-memory records. An already-sent request cannot be recalled. A short flush timer is best-effort; the alarm fallback is 30 seconds. In-memory events can be lost when the extension service worker stops.

Live API ingestion was tested. Installing this extension in a real browser and exercising InfluxDB/Grafana are separate acceptance checks, still pending. `monitoring/setup_monitoring.sh` is legacy optional tooling; its download versions and dashboard provisioning have not been verified in this snapshot.

The current agent is for a local demonstration. Authentication, encrypted storage, retention/deletion controls and deployment hardening are product work still to do before serving external customers.

## Evidence interpretation

- A configured-identifier match supports the presence of that identifier in an observed request. It does not prove the recipient stored it or used it for profiling.
- A repeated deterministic email hash demonstrates linkability in the captured data. Salted hashes, HMACs and encrypted or unsupported encodings may be missed.
- Tracker labels use supported domain-wide EasyPrivacy rules and selected Tracker Radar categories. This is not a full ABP engine. Keyword hints do not become confirmed tracker labels.
- Country is a DNS/GeoIP estimate of an endpoint. Unknown stays unknown. A non-Australian endpoint does not establish an APP 8 breach or a storage location.
- Fingerprint API calls are recorded at session level; legitimate uses exist. The crawler does not establish fingerprinting intent or attribute the call to a specific network request.
- Retest comparisons require matching scope, reference/profile fingerprints, identity profile, capture protocol and successful captures. A changed or failed capture makes disappearance inconclusive.
- Exported reports omit raw request paths, query values, bodies, cookies, identifiers and matched digests. They still contain domains and site history. Raw JSON and DuckDB retain sensitive details and stay local.

## Tests and supporting files

```bash
python -m pytest tests/ -q     # 232 tests
node --test tests/*.cjs        # 50 tests
```

Both commands are what CI runs, so they reproduce the figures quoted above. The UI DOM tests need jsdom (`npm install jsdom`); nothing else does. `requirements-tested.txt` pins the dependency versions that were actually tested, which is not the same as a complete platform-independent lockfile.

- `docs/VALIDATION.md`: what was tested, in which environment, and what each result does not prove.
- `docs/FINAL_PROJECT_GUIDE.md`: demo walkthrough, validation metrics and assessment evidence.
- `docs/evidence/`: the recorded runs behind every number in this README.
- `docs/DEVELOPMENT_PLAN_VI.md`: product direction and staged work.
- `submission/`: the approved charter, plan and proposal.
- `archive/unverified_legacy_outputs/`: earlier outputs kept for provenance. Their numbers are not current results.

Coursework for TAFE NSW Higher Education. The code here is mine. The reference data is not: EasyPrivacy, URLhaus, DuckDuckGo Tracker Radar and MaxMind GeoLite2 each carry their own licence and attribution terms, and anyone reusing this project needs to read those first.
