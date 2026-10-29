# DataExodus Final: what was merged, from where, and what was fixed

## Guard 0.5.1, 28 October 2026: pop-unders closed by the browser

Found by testing a real comic-reading site whose ad network opens a pop-under on the first click. Guard's popup guard wraps `window.open` in the page, and the ad script went around it, so the advertiser's tab still opened.

| Area | Change |
| --- | --- |
| `guard/background.js` | Listens to `chrome.webNavigation.onCreatedNavigationTarget`, which Chrome fires for every tab a page opens, whatever the method (`window.open` from any frame, a scripted `target=_blank` link, a form). A tab is closed when it leaves the page's site and no link the user clicked, or right-clicked for "Open link in new tab", leads there (`GuardCore.unsolicitedPopup`). Pop-unders that open `about:blank` first are judged by the address they then load. Recorded as `popup` with `evidence_quality: chrome_tab_observed` (Chrome saw it, not a page report), domain only. New permission: `webNavigation`. |
| `guard/content.js` | Sends the link a user clicks, middle-clicks or right-clicks (and a form they submit) to the worker as `link_intent`, kept in memory for 3 s (60 s for right-click) and never stored. A blocked popup no longer opens a quarantine tab, which on a pop-under site was itself a tab nobody asked for; a clicked hidden overlay still does. |
| `analysis/guard_report.py` | Accepts `chrome_tab_observed` popup events and counts them apart from page-reported interventions. |
| Acceptance | The lab's Play popup is expected to be blocked without a quarantine tab; overlay and direct ad still quarantined. |

## 0.5, 27 October 2026: DataExodus Box, the product release

The product is now the Raspberry Pi box that a visitor tries with their own phone. The research toolkit stays in the repository and in the tests, but it is optional (`install.sh --study`).

| Area | Change |
| --- | --- |
| Link check (`protection/verdict.py`, `protection/sandbox.py`) | A 0–100 score with a named reason for every point: URLhaus host, clipboard write, program download, password or card form posting to another site, lookalike brand (including digit swaps), punycode, bare IP, plain-HTTP password, card form, notification prompt, dialogs, scam wording, cross-site redirects, trackers, third parties, servers outside Australia, ad click, click IDs, device prompts, fingerprinting reads, pop-ups. The page's actions are reported by wrappers installed before any page script runs; forms and text are read after load in every frame. Ordinary browser user agent, to avoid the simplest cloaking. |
| Safe Browse (`/sandbox/browse`) | A live sandbox page (360×640, mobile) driven by tap, scroll, back, type and key actions; the client receives JPEG screenshots only. `target=_blank` links are followed after a tap, pop-unders only counted; sessions close after 2 idle minutes and 10 minutes at most; `SANDBOX_BROWSE_SESSIONS` limits them. |
| Wi-Fi access point (`pi/hotspot.sh`) | NetworkManager WPA2 access point with AP isolation on 10.42.0.1/24. NM's dnsmasq does DHCP only; the DNS watch answers DNS. Refuses to run when wlan0 is the only uplink; `--off` undoes it; prints a join QR code in the terminal. |
| Captive portal (`pi/portal.py`, `pi/devices.py`) | Welcome page with consent, Check a link (paste a link or a whole scam message), Safe Browse through an `<input type=image>` form (no JavaScript at all), My device (opt-in DNS view, per-device tracker blocking, Forget this device), How it works. Hotspot clients and the portal's own host names only; cross-site and `Origin: null` posts refused; results and sessions private to the device; rate limits. |
| DNS watch | Hotspot devices logged only after opt-in, tagged by MAC, kept 24 h; per-device blocking; connectivity-check names answered with the portal and never logged; `auto` upstream from `/etc/resolv.conf`; `pi/dns_trackers.txt` (hand-picked ad/analytics hosts, because EasyPrivacy blocks the big trackers by path, which DNS never sees). |
| Sample links (`examples/sample_links.py`) | Four fictional sites on 127.0.0.49–58:8030 (news, ad click, fake bank, fake CAPTCHA) so the checker can be shown offline without real scams. The firewall allows exactly this range and port. |
| Dashboard | Wi-Fi status and a printable card with the join and portal QR codes (`/card`). |
| Guard 0.5 | The quarantine page shows the score and reasons; a dangerous result offers no one-click clean link. |
| Acceptance | `examples/run_box_acceptance.py`: the visitor flow in real Chromium on one computer (19 checks). |

Bugs found by the real-browser runs: `Referrer-Policy: no-referrer` made Chromium send `Origin: null` on the portal's own forms, so the CSRF check refused them; danger buttons had red text on red; DNS blocking missed google-analytics.com with EasyPrivacy alone. Found in review: the owner's dashboard summed consented visitors' lookups although the portal promises "visible only on this device"; summaries now leave device-tagged rows out.

## 23 October 2026: the merge

One codebase replaces four parallel copies:

| Source | What it contributed |
| --- | --- |
| `DataExodus_Project_2.zip` (+ `DataExodus_Guard_1.zip`, `GUARD_QUICKSTART_VI.md`) | The base tree: study crawler, processing, audit/retest, live agent, submission documents, and its Guard 0.3 (learned session rules, offline quarantine page, rule rollback, tab-scoped quarantine records, gesture-gated popups) |
| `DataExodus_Guard` (Guard 0.3, browser-verified) | Real-browser fixes, ad-click recognition and redirect, sandbox preview service, "open anyway" for one tab, registrable-site third-party test, acceptance harness technique |
| `DataExodus` (first build) | `setup_data.py` that works on Windows (Tracker Radar streamed from the tarball), URLhaus mirror, MaxMind Account ID login |
| `DataExodus_GhostShield` (Antigravity build, fixed) | The X-Ray idea (rebuilt from scratch in the isolated world) and its local-only agent protection, now applied to `pipeline/agent.py` |
| New | Raspberry Pi 5 box (`pi/`): isolated sandbox host, DNS watch, scheduled study, dashboard, firewall, installer, Windows tunnel script |

## Bugs found by running it in a real browser (Chromium 153)

Neither Guard 0.3 had both of these right; unit tests with mocked Chrome APIs passed for both.

1. **Saving settings with a protected email failed.** The SHA-512 identity rule was a case-insensitive `regexFilter`; Chrome rejects it ("exceeded the 2KB memory limit when compiled"), `isRegexSupported` refuses it and the whole save is rolled back. Identity rules are now `urlFilter` substrings (an escaped regex only for an email containing `*`, `|` or `^`). Covered by the browser acceptance run and `tests/test_guard_core.cjs`.
2. **`GuardCore` was missing in one content-script world.** Listing `core.js` in both the MAIN and isolated entries makes Chrome inject it once per frame, in whichever entry comes first. `core-main.js` is a byte-identical copy; `tests/test_guard_manifest.py` enforces it.

## Guard 0.4.0 design decisions

- **Learned rules, not permanent auto-blocks.** After a POST body carries the identifier to another site, a session rule blocks that *source → destination* pair only (Project_2's design). A permanent domain-wide block (the other 0.3) could silently break a payment provider on every site.
- **One quarantine page for every held navigation.** Listed-domain navigation, ad clicks, identifier-carrying navigation, scripted popups and transparent overlays all end on `quarantine.html`. Chrome's redirect carries the URL in the fragment (never sent over the network); the page hands it to the worker and replaces the fragment. Identifier-carrying navigations are redirected without their URL.
- **The page cannot claim a reason.** `quarantine.html` is web-accessible, so any site can open it with any fragment. The worker re-derives the reason from current policy (or, for identifier navigations, from a matching Chrome rule event) and marks anything else `opened_directly`, unverified.
- **The sandbox only ever receives the URL Guard holds for that tab.** The quarantine page sends a record id, never a URL; "open clean / direct / original" are chosen from the same record.
- **X-Ray** runs in the isolated world, draws in a closed shadow root and reports counts only.

## Raspberry Pi 5 box

- `dataexodus-guard`: `protection.api` + sandbox on 127.0.0.1:8010, Raspberry Pi OS Chromium with its own process sandbox (`DATAEXODUS_CHROMIUM_SANDBOX=1`), reached from the laptop by SSH tunnel (`pi/connect-pi.ps1`).
- `dataexodus-firewall`: nftables output rule for the service account's uid: internet yes; RFC 1918, loopback (except its own API port), link-local, CGNAT, ULA and multicast dropped. Defends the SSRF guard against DNS rebinding.
- `dataexodus-dnswatch`: UDP+TCP forwarder; only allowed client networks are answered (no open resolver); SQLite log pruned after 7 days; block mode from EasyPrivacy whole-domain rules, URLhaus and a custom list, hot-reloaded.
- `dataexodus-study.timer`: weekly crawl → process → report → audit compared with the previous good run; lock against overlap; keeps 8 runs.
- `dataexodus-box`: read-only dashboard, Host-header check against DNS rebinding, raw captures never served, reports served with a sandbox CSP.
- `pi/install.sh`: idempotent; keeps settings, token and data; syntax-checks the nftables file before enabling it; self-checks the service, the dashboard and the firewall (expects a timeout to the router).

## Also fixed

- `pipeline/agent.py` (live research agent): any website could open `ws://localhost:8000/live` and receive live browsing events; no Host check (DNS rebinding). Now: Host allowlist, Origin and `Sec-Fetch-Site` checks, WebSocket origin check (`tests/test_agent.py`).
- `pipeline/classify.py`: `Classifier.label()` labels a name without a network lookup (the DNS report already has the answered addresses).
- `crawler/crawl.py`: `CHROMIUM_PATH` for the OS browser on the Pi.

## Verification

- 161 Python tests, 46 JavaScript tests (jsdom DOM tests included), 0 skipped.
- Real Chromium 153 acceptance, baseline and protected phases, receiver-side counts: `docs/evidence/guard-v04-browser-acceptance.json`.
- Local smoke run of the Pi services on Windows: DNS watch on a high port with real upstream lookups, DNS report with owners and GeoIP countries, dashboard 200, forged Host 403.
- `bash -n pi/install.sh`; installer substitutions exercised in Git Bash; `connect-pi.ps1` parsed with the PowerShell parser.
- **Not done here:** running the installer and services on a physical Raspberry Pi; live Gemini / Web Risk calls.
