# Validation

This file records what was actually tested, on which machine, and what each
result does not prove. Newest section first; older sections are kept so the
numbers quoted in earlier write-ups can still be traced.

## Repository trimmed, and moved to English — 6 November 2026

The optional cloud explanation route (Google Gemini) and the experimental
scikit-learn tracker classifier were removed. Neither was ever run with real
credentials or real training data, so neither had evidence behind it, and both
added a dependency and an outbound path the product does not need. Guard's
"Explain evidence" button now returns the local explanation, which is what the
tested path always did. Sections below that mention Gemini describe code that
is no longer in the repository.

The five Vietnamese guides were rewritten in English and renamed
(`*_VI.md` is gone), and the advisory API dropped its `language` field: the
visitor portal was already English-only, so a Vietnamese Guard explanation was
an inconsistency rather than a feature. The removed field is refused rather
than ignored, so a stale client fails loudly instead of silently losing its
request.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Full Python suite after the removal | **217 passed** | `python -m pytest tests/ -q` |
| Full JavaScript suite after the removal | **50 tests, 0 failed** (9 skipped without `jsdom`) | `node --test tests/*.cjs` |
| `/analyze` makes no outbound call | Asserted, not assumed: the test fails the run if anything POSTs during the request | `tests/test_guard_api.py::test_analyze_explains_locally_and_sends_nothing` |
| `/health` no longer advertises AI configuration | No `ai_*` key in the response | `tests/test_guard_api.py::test_health_reports_no_ai_configuration` |
| The remaining outbound call is still capped | Web Risk lookup returns 429 past the per-minute budget | `tests/test_guard_api.py::test_reputation_budget_is_enforced` |

## Reading a report

What a finding supports, and what it does not. These limits belong with the
numbers, not in a footnote.

- A configured-identifier match supports the presence of that identifier in an observed request. It does not prove the recipient stored it or used it for profiling.
- A repeated deterministic email hash demonstrates linkability in the captured data. Salted hashes, HMACs and encrypted or unsupported encodings may be missed.
- Tracker labels use supported domain-wide EasyPrivacy rules and selected Tracker Radar categories. This is not a full ABP engine. Keyword hints do not become confirmed tracker labels.
- Country is a DNS/GeoIP estimate of an endpoint. Unknown stays unknown. A non-Australian endpoint does not establish an APP 8 breach or a storage location.
- Fingerprint API calls are recorded at session level; legitimate uses exist. The crawler does not establish fingerprinting intent or attribute the call to a specific network request.
- Retest comparisons require matching scope, reference/profile fingerprints, identity profile, capture protocol and successful captures. A changed or failed capture makes disappearance inconclusive.
- Exported reports omit raw request paths, query values, bodies, cookies, identifiers and matched digests. They still contain domains and site history. Raw JSON and DuckDB retain sensitive details and stay local.

## Guard 0.5.1 (pop-unders closed by the browser) — 28 October 2026

Same machine and versions as below.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Full Python suite | **224 passed** | `docs/evidence/final-pytest.txt` |
| Full JavaScript suite (jsdom installed) | **50 passed, 0 skipped** (3 new worker tests: pop-under closed and recorded without its URL; `about:blank` pop-under judged by its next address; clicked, right-clicked, same-site, allowed-site and paused cases left open) | `docs/evidence/final-javascript-tests.txt` |
| Guard in real Chromium (`examples/run_guard_acceptance.py`) | Both phases pass with the same receiver-side counts as 0.5; the Play popup is blocked without a quarantine tab, overlay and direct ad are quarantined | `docs/evidence/guard-v051-browser-acceptance.json`, `docs/evidence/guard-v051-browser/` |
| Real site with pop-under ads (headless Chromium 156, Guard loaded, three clicks per run, three runs) | With Guard 0.5 the advertiser's tab opened on the first click in 5 of 6 runs. With it: run 1, the ad script went around the `window.open` hook and its tab was closed by the new check (`chrome_tab_observed`); runs 2–3, the hook stopped `window.open` and no tab opened. No ad tab stayed open | Run by hand; not in the repository, because the site is third-party |
| False positives (example.com with injected links) | A `target=_blank` link, Ctrl+click and middle-click opened and stayed open; a pop-up opened through a hidden iframe's `window.open` was closed | Run by hand |

## DataExodus Box 0.5 (product release: link check, Safe Browse, Wi-Fi portal) — 27 October 2026

Windows 11, Python 3.11.4, Node.js 24, Playwright 1.64 with its Chromium 156.0.8078.4.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Full Python suite | **220 passed** | `docs/evidence/final-pytest.txt` |
| Full JavaScript suite (jsdom installed) | **47 passed, 0 skipped** | `docs/evidence/final-javascript-tests.txt` |
| Visitor flow in real Chromium (`examples/run_box_acceptance.py`) | **19/19 checks.** Real processes on loopback: portal on 127.0.0.10, sandbox service with headless Chromium, DNS watch with hotspot rules (real upstream lookups), sample links; a second Chromium as the phone. Captive check 302 before joining, 204 after; samples rated low 0, be careful 35, dangerous 60, dangerous 85; a pasted scam text checked; Safe Browse at 1:1 size: tap on the password field, type, Enter submitted the fake bank form inside the sandbox (collector count 1); lookups before joining not recorded; per-device blocking answered 0.0.0.0; Forget this device deleted the device's lookups; cross-site POST and foreign Host refused | `docs/evidence/box-v05-acceptance.json`, screenshots `docs/evidence/box-v05/` |
| Guard 0.5 in real Chromium (`examples/run_guard_acceptance.py`) | Both phases pass with the same receiver-side counts as 0.4 (identifiers 4 → 0, POST collector 2 → 1, ad clicks from the user's page 1 → 0, advertiser click IDs 1 → 0, clean advertiser visit 0 → 1); the sandbox preview now carries the score | `docs/evidence/guard-v05-browser-acceptance.json`, `docs/evidence/guard-v05-browser/` |
| Scoring rules | Every reason maps to one named rule; lookalike brands (incl. digit swaps) caught; brands' own and country sites, and ordinary words (outlook, medicare, steam), not flagged; lab hosts not penalised for bare IPs/plain HTTP | `tests/test_verdict.py` |
| Portal security and privacy | Hotspot clients only; own host names only (DNS rebinding); cross-site and `Origin: null` posts refused; no JavaScript (CSP); everything escaped; checks and Safe Browse sessions private to the device; rate limits; visitors' lookups left out of the owner's dashboard and reports | `tests/test_pi_portal.py`, `tests/test_pi_box.py` |
| DNS watch hotspot rules | Logged only after opt-in, tagged per device (MAC), shorter retention, per-device blocking, captive names answered with the portal and never logged, `auto` upstream from resolv.conf, old logs migrated | `tests/test_pi_dnswatch.py` |
| Pi files | New portal/samples units hardened; only DNS watch and portal may bind privileged ports; firewall's only loopback exceptions are the Guard API and the sample range; hotspot script strict, refuses to cut the Pi's only uplink, WPA2 + AP isolation, DHCP-only dnsmasq; `bash -n` for both scripts; settings helpers exercised in Git Bash with `&`, `|` and `\` in values | `tests/test_pi_files.py` |

Found by the real-browser runs and fixed in this release: the portal's `Referrer-Policy: no-referrer` made Chromium send `Origin: null` on the portal's own forms, so the CSRF check refused "Join" (now `same-origin`); red "danger" buttons had red text (invisible); EasyPrivacy has almost no whole-domain rules for the big trackers, so DNS blocking missed google-analytics.com (added the hand-picked `pi/dns_trackers.txt`). Found in review: the owner's dashboard summed consented visitors' lookups; summaries now leave device-tagged rows out.

**On the Raspberry Pi 5 itself (27 October 2026, Debian 13 trixie, 4 GB):** `pi/install.sh` exited 0 with all self-checks passing; firewall, Guard, dashboard, DNS watch and sample services active; the sandbox account's packets to the dashboard dropped and to the sample range allowed; Chromium with its own sandbox under systemd scored the four samples exactly as on Windows (0 / 35 / 60 / 85) and a real news site 10 (US servers), 3.6–5.3 s per check; a Safe Browse session started in 2.1 s (`docs/evidence/pi-hardware-verification.txt`).

**Research run 1 on the Pi (28 October 2026):** the 50-site study completed (50 sessions, 8.5 minutes, resolver 1.1.1.1 recorded): 34 full captures, 2 partial, 14 failed, mostly bot-protection responses, which were not bypassed. The link checker on the same 50 legitimate sites rated none Dangerous (28 low, 21 careful; 31/18 after the scam-wording refinement found by this run). Details: `docs/evidence/research-run1/README.md`.

**Not verified yet:** the Wi-Fi access point, NetworkManager's DHCP and the portal on 10.42.0.1 (the Pi had no Ethernet uplink yet), and captive-portal pop-ups on real iPhone and Android phones (`docs/HOTSPOT.md` section 3 lists the checks to run). No precision/recall of the score on a labelled set of real phishing links; live Web Risk calls.

## DataExodus Final (Guard 0.4 + Raspberry Pi box) — 23 October 2026

Windows 11, Python 3.11.4, Node.js 24, Playwright Chromium 153.0.8010.12.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Full Python suite | **161 passed**, one Starlette/httpx deprecation warning | `docs/evidence/final-pytest.txt` |
| Full JavaScript suite (jsdom installed) | **46 passed, 0 skipped** | `docs/evidence/final-javascript-tests.txt` |
| Guard 0.4 in real Chromium, baseline vs protected | Both phases pass; receiver-side counts: identifiers 4 → 0, POST collector 2 → 1 (learned rule), same-site POST 1 → 1, ad navigations 3 → 0, ad clicks seen from the user's page 1 → 0, advertiser click IDs 1 → 0; sandbox preview followed the redirect chain, removed click IDs and showed a screenshot | `docs/evidence/guard-v04-browser-acceptance.json`, `docs/evidence/guard-v04-browser/` |
| Stability | 5 consecutive passing runs with the sandbox service started | `docs/evidence/guard-v04-stability.json` |
| Study crawler local lab in real Chromium | Collector receipts 2 before, 0 after; retest comparable; 6 findings not observed in retest | `docs/evidence/local-lab-browser.json` |
| Raspberry Pi services, run locally | DNS watch answered real lookups through 1.1.1.1 and logged them; report labelled owners (Google, Facebook) and GeoIP countries (2 AU, 2 US); dashboard 200; forged Host header 403 | `docs/evidence/pi-services-smoke.txt` |
| Pi deployment files | systemd hardening, loopback-only web services, firewall drop list, installer strictness, requirements coverage (static tests); `bash -n pi/install.sh`; installer substitutions exercised in Git Bash; `connect-pi.ps1` parsed without errors | `tests/test_pi_files.py` |
| Live research agent | Cross-site Origin, cross-site subresource, forged Host and cross-site WebSocket refused; extension, own dashboard and CLI clients allowed | `tests/test_agent.py` |

Found by the real-browser run and fixed: Chrome refuses a case-insensitive SHA-512 `regexFilter` (2 KB compiled-regex limit), which made saving a protected email fail in the earlier Guard 0.3 code. Identity rules now use `urlFilter`.

**Not verified here:** `pi/install.sh` and the systemd services on physical Raspberry Pi hardware (Raspberry Pi OS, nftables, Chromium's sandbox under systemd); live Web Risk calls; any real-world blocking rate, false-positive rate on public sites or user study. The browser runs use a loopback lab; they show the mechanism works, not how often it helps on the open web.
## Earlier snapshots — 22 October 2026

## Guard 0.3 continuation — 23 October 2026

- Full Python suite: **94 passed**, one pre-existing test-client deprecation warning; `docs/evidence/guard-v03-pytest.txt`.
- Full JavaScript suite: **32 passed, no skips**; `docs/evidence/guard-v03-javascript-tests.txt`.
- New checks cover private identifier regex construction and setup, source/destination-scoped follow-up rules, session restoration/reset, rollback and unsupported regex failures, offline quarantine tab targets, tab-bound access, stripped metadata, escaped sandboxed srcdoc and forged-message click gating.
- Lab HTTP checks include unknown collectors and a legitimate same-site POST. Provider adapter mocks accept the new navigation handling label without a safety verdict.
- Manifest references, JavaScript syntax and Python compilation passed; `docs/evidence/guard-v03-smoke.json` records the browser executable is still absent.
- Real browser enforcement, CSP behaviour in Chrome, expanded Playwright acceptance, remote sandbox execution and real provider calls are **not verified**. The offline quarantine does not execute or fetch the destination. Prior suite counts below are retained as historical validation.

Validation was run against the actual extracted/uploaded code and the updated files. Historical claims in the old handoff are not substituted for this evidence.

## Latest Audit + Guard continuation

| Check | Outcome | Evidence |
| --- | --- | --- |
| Current full Python suite | 91 passed; one pre-existing Starlette/httpx warning | `docs/evidence/guard-pytest.txt` |
| Current full JavaScript suite | 18 passed, zero skips; includes jsdom UI tests | `docs/evidence/guard-javascript-tests.txt` |
| New Guard policy and worker behaviour | DNR install/pause/exception rules; caller restrictions; secret-free MAIN policy and evidence projection; observation separated from rule matches | `tests/test_guard_core.cjs`, `test_guard_worker.cjs`, `test_guard_page.cjs` |
| API security | Authentication, body limits, closed input schema, explicit opt-in, provider request construction, invalid-output fallback and hard call caps | `tests/test_guard_api.py`; provider calls mocked |
| Actual loopback API process | Authenticated health/local explanation returned; unauthenticated health returned 401 | `docs/evidence/guard-smoke.json`; zero cloud calls |
| New receiver lab | Actual HTTP service accepts only synthetic raw/hash identity and counts collector/ad arrivals; document control serves | `tests/test_guard_lab.py` |
| Guard report and shared rules | Validated evidence, separate observation labels, source digest and supported-domain export | `tests/test_guard_report.py`, `test_guard_rules.py` |
| UI behaviour | Advisory output rendered as text; reputation requires separate URL-disclosure opt-in | `tests/test_guard_ui.cjs` |
| Browser acceptance | **Not completed**: download returned an invalid/truncated ZIP; Chromium executable absent | `examples.run_guard_acceptance` is supplied for local execution |
| Web Risk with an actual key | **Not performed**: no credential; the adapter was tested with mock responses | No live accuracy, billing or latency claim |

These checks do not establish real-world blocking rates, production readiness, comprehensive malware protection or commercial demand. Network enforcement and page-reported interventions have different evidence strength.

The following table and fixture observations retain the preceding audit-only validation for provenance; its 71/5 suite counts are superseded above.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Full Python test suite | 71 passed; one Starlette/httpx deprecation warning | `docs/evidence/pytest.txt` |
| Extension, crawler hook and audit DOM tests | 5 passed, no skips; jsdom installed for the DOM check | `docs/evidence/javascript-tests.txt` |
| Controlled fixture pipeline | Generated before/after DuckDB, CSV/XLSX, redacted JSON/Markdown/HTML audit | `docs/evidence/demo.txt` and `reports/demo/` |
| Descriptive research report CLI | Completed against controlled before data | `docs/evidence/report.txt` |
| Live agent | HTTP validation, queued processing, exact site scope and millisecond normalization passed in TestClient | `tests/test_agent.py` |
| Local lab HTTP services | Both pages served; synthetic hash accepted; unrelated value rejected; after page omits sender | `tests/test_local_lab.py` |
| Python module compilation | Passed | Local `compileall` execution |
| GitHub Actions YAML | Parsed locally; read-only contents permission | `.github/workflows/ci.yml` |

The warning comes from the installed FastAPI/Starlette test-client stack recommending httpx2. The tests passed with httpx 0.28.1; no application failure was observed from that warning.

## Controlled fixture observations

| Measure | Before | After |
| --- | ---: | ---: |
| Sites / sessions | 2 / 2 | 2 / 2 |
| Requests | 10 | 6 |
| Requests matching the configured synthetic identifier | 4 | 0 |
| Listed tracker requests | 4 | 0 |
| High-priority aggregated findings | 4 | 0 |
| Total aggregated findings | 6 | 0 |

One repeated-hash group spans the two fictional sites. Six findings are not observed in the comparable retest. A CDN request carrying an unrelated hash is a negative control and does not count as a configured-identifier match.

These figures demonstrate software behaviour on generated fixtures. They are not empirical results about any public website.

## Important limits

- Chromium installation was attempted but failed with an invalid/truncated download response. The real Playwright local-lab capture and public 50-site crawl were not executed here.
- The crawler hook test executes the injected JavaScript with API stubs. It verifies that the hook script runs; it is not a substitute for a real Chromium integration test.
- jsdom exercised report selection/filtering/evidence rendering. Visual layout in an actual browser and manual extension installation remain acceptance checks.
- InfluxDB/Grafana were not started or verified. Installing the Python Influx client does not establish monitoring-stack operation.
- The supplied ZIP contained no original raw crawl directory, DuckDB databases, reference blocklists or GeoIP file. The old 10-site counts and ML 99.3% claim cannot be independently reproduced from this upload.
- The frozen website list differs from the sectors/sites described in some legacy material. The list is preserved; the difference is documented.
- GitHub reports the plugin installed/enabled, but repository tools and an authenticated CLI were unavailable. No remote repository was read or changed, and CI has not run on GitHub.

## Reproduce locally

```bash
python -m pip install -r requirements.txt -c requirements-tested.txt
python -m pytest tests/ -q
python -m analysis.demo
node --test tests/test_extension.cjs tests/test_crawler_hooks.cjs
```

The constraints record tested direct package versions, not a complete cross-platform transitive lockfile. `docs/evidence/environment.json` records the actual Python/OS/direct package versions.

The optional report DOM test uses jsdom and requires the fixture report to be generated first. Real browser acceptance:

```bash
python -m playwright install chromium
python -m examples.run_local_lab --out reports/local-lab-run1
```

Keep the original collector receipts and capture errors. For a commercial pilot, add independent label validation and external-user evaluation; passing this suite does not establish market demand or production readiness.
