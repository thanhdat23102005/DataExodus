# Final project evidence and demonstration

## Product demonstration: DataExodus Box (recommended for the A4 demo)

**Product question.** Can a self-contained Raspberry Pi 5 box let a non-expert check a suspicious link, use the page safely, and see where their own phone's data goes, without the page ever running on their device and without recording anything they did not agree to?

**Set-up before the session.** Pi installed with `sudo bash pi/install.sh --hotspot` and connected to the internet by Ethernet or USB tethering; the card printed from `http://127.0.0.1:8020/card`; the checklist in `docs/HOTSPOT_VI.md` section 3 run once with your own phone; laptop with Guard and the SSH tunnel.

| Time | The assessor does | You explain |
| --- | --- | --- |
| 0:00–0:45 | Scans the card's QR code; the welcome page opens by itself | A captive portal: the Pi's DNS answers the phone's connectivity check. Nothing is recorded without the tick box; 24-hour retention; each device sees only its own data. |
| 0:45–2:30 | *Check a link*: the fake bank, then the fake CAPTCHA sample | A throwaway Chromium on the Pi, firewalled from the LAN and from every phone. The score is a sum of named rules shown with the result; there is no hidden model. |
| 2:30–3:30 | Pastes a real scam text or link they have received | The phone never loads it. The redirect chain, screenshot and trackers come from the Pi. |
| 3:30–4:45 | *Safe Browse* on the fake bank: taps the password field, types, Enter | The page runs on the Pi; the phone only gets pictures. What was typed reached "another site" inside the sandbox. |
| 4:45–6:00 | *My device*: opens a few apps, switches on tracker blocking | Which companies the apps contact and where their servers are (APP 8 angle: an estimate, not proof of storage). Hashing is not anonymisation: identifiers survive hashing, so blocking at the network is a real control. |
| 6:00–7:00 | On the laptop: Guard holds an ad click; *Preview in isolated sandbox* | The same sandbox and score, used from the browser extension. |
| 7:00 | *Forget this device*, then forgets the network | Deletion is immediate and verifiable. |

| Test | Expected evidence |
| --- | --- |
| Four sample links | low (0), be careful (≈35), dangerous (≈60), dangerous (≈85), each with its reasons (`docs/evidence/box-v05-acceptance.json`) |
| Pasted message containing a link | The link is extracted and checked; text without a link is rejected |
| Safe Browse | Tap coordinates map 1:1 to the sandbox page; the fake bank form submits inside the sandbox |
| Consent | No DNS rows for a device before opting in; rows tagged per device; Forget deletes them |
| Per-device blocking | Listed tracker names answered 0.0.0.0 for that device only |
| Portal security | Non-hotspot clients, foreign Host headers, cross-site and `Origin: null` posts refused; no JavaScript served |
| Firewall (on the Pi) | `sudo -u dataexodus curl -m 3 http://<a phone's 10.42.0.x address>` times out; a public site loads |
| Captive pop-up (on the Pi) | Android "Sign in to network" / iPhone pop-up appears on joining; passes after joining |

**Questions to prepare for (product).**

- *How accurate is the score?* It is a transparent heuristic, tested on fictional samples that exercise each rule. It has not been measured against a labelled set of real phishing links; that is the next evaluation step (for example a sample of PhishTank/OpenPhish URLs against a sample of popular sites, reporting precision and recall).
- *What if the scam page detects the sandbox?* Cloaking is possible: the score comes from one anonymous visit. The sandbox uses an ordinary user agent to avoid the simplest checks; a low score is never presented as "safe".
- *Why not just use Google Safe Browsing?* Reputation lists only know URLs someone has already reported. The sandbox looks at behaviour on the spot (a password form posting elsewhere, a clipboard write), works for brand-new links, and shows the user why. Web Risk can be added as one more signal (`/reputation`, opt-in).
- *Is it safe for the assessor's phone?* The page never runs on the phone. Visitors are isolated from each other (AP isolation), the sandbox account cannot reach any device on the network, and the portal sends no JavaScript.
- *What do you record about visitors?* Only with consent: DNS names for 24 hours, keyed by the device's (usually random) Wi-Fi MAC, visible only to that device, deleted on request. The Pi routes traffic like any router but does not log or decrypt it.
- *Can it be sold?* It is a tested prototype. Next steps would be usability tests with non-experts, the accuracy evaluation above, HTTPS for the portal, and a hardware cost/benefit comparison with existing DNS filters (Pi-hole, NextDNS).

**Suggested product report structure.** 1. Problem and users (scam links, invisible data flows, APP 8). 2. Requirements, including privacy and safety requirements. 3. Architecture (Pi services, portal, sandbox, DNS watch, Guard) and threat model. 4. Implementation of scoring, Safe Browse and consent. 5. Security and privacy by design (isolation layers, consent, retention, no JavaScript, CSRF/DNS-rebinding defences). 6. Evaluation: automated tests, the real-browser acceptance run, the on-Pi checks, and the limits. 7. Future work and commercial validation.

---

# Research component and audit evidence

The research is kept as the project's second part, run on the Raspberry Pi: RQ1, the 50-website measurement (trackers, third parties, server countries, by sector); RQ2, the product's link checker applied to the same legitimate sites to count false alarms; and the controlled lab experiment for *hashing is not anonymisation*. The protocol (including the neutral 1.1.1.1 resolver, recorded in every run's `status.json`), commands and reporting guidance are in `docs/RESEARCH_VI.md`. The rest of this guide covers the original study and the audit/retest workflow in more detail. It is not a completed final report.

## A defensible project question

Can a local, explainable audit workflow help a website developer identify transmission of configured test identifiers, choose a change, and verify whether the finding recurs under the same capture conditions?

The existing 50-site descriptive study remains a separate part of the original academic scope. Confirm how the two parts fit the actual A4 rubric and document any scope amendment. The new audit workflow adds an applied outcome without inventing study results.

## Suggested five-minute demonstration

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:40 | One finding and the user problem | A developer needs a specific request to investigate and a way to verify a change. |
| 0:40–1:40 | Before capture | Identify a configured synthetic email hash, destination, surface, source rule and evidence ID. |
| 1:40–2:30 | Repeated hash across two controlled sites | Matching a known deterministic hash supports linkability; profiling intent and downstream use remain unverified. |
| 2:30–3:30 | The website change and after capture | Explain the actual integration change in the local lab or staging site; show the retest and its matching protocol. |
| 3:30–4:20 | Redacted evidence JSON and test logs | Show reproducibility, a negative control and protection against duplicate processing. |
| 4:20–5:00 | Limits and next users | State the capture coverage, explain unknown geography and describe an agency pilot as proposed work. |

Use the fixture demo to explain the UI. Use the local browser lab or an authorised staging capture as browser/network evidence after executing it on your machine. Keep the labels visible. Never relabel fixture counts as public-site measurements.

## Extended demonstration: Guard and the Raspberry Pi box (about 10 minutes)

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–1:30 | Guard lab, protection paused: send the test email, its hash and a POST body; click the sponsored result | The receiver panel counts what arrived; the ad redirector logged the click and the advertiser got a `gclid`. |
| 1:30–3:30 | Same actions with Guard on | Identifier URLs stopped before sending, even to an unlisted collector; the first POST arrives and the learned rule stops the second; same-site submit and documentation still work. |
| 3:30–5:00 | The sponsored click held in quarantine, **Preview in isolated sandbox** (Pi), **Open clean destination** | The redirect chain, trackers and screenshot came from the Pi ("Opened on: dataexodus"); the advertiser page opened without a click ID. |
| 5:00–6:00 | X-Ray on the lab page | Pixel, hidden frame and invisible link are outlined; this is a view of the markup, not proof of sending. |
| 6:00–7:30 | Pi dashboard: DNS watch for your own phone | Which companies the phone's apps contacted, and where the answering servers are; lookups are not data transfers; DoH bypasses it. |
| 7:30–9:00 | Pi dashboard: weekly study runs and the week-over-week audit | Same protocol each week; changed reference lists make a comparison inconclusive rather than "improved". |
| 9:00–10:00 | `sudo -u dataexodus curl -m 3 http://<router>` timing out; `ss -tulpn` | Defence in depth: the sandbox account cannot reach the LAN even if the application's address check is bypassed. |

Keep `docs/evidence/guard-v04-browser-acceptance.json` (automated real-browser run) next to your own screenshots and the Pi verification commands from `docs/RASPBERRY_PI_VI.md`.

## Evidence checklist

- Record Python, Playwright and Chromium versions, OS, time, dwell interval, capture protocol and site list.
- Retain raw JSON, content hashes and reference-list snapshots; keep sensitive captures local.
- Save the actual test output. A passing unit test is different from a successful real browser capture.
- For the local lab, keep collector receipts as separate proof that the local collector received the test hash.
- Keep an expected-vs-observed table with positive controls (supported raw/hash/encoded variants) and negative controls (unrelated email, unrelated hash, too-long hex strings, first-party resources).
- For the study, record failed/partial navigations and report sector coverage before comparing rates.
- Check a documented sample of labels manually using request details and the reference record; report any disagreements.
- Retain baseline and retest with matching identities, rules, protocol and site scope. Capture disappearance remains evidence for that run only.

## Suggested evaluation table

| Test | Expected evidence |
| --- | --- |
| Known SHA-256 email hash in URL | Correct algorithm, surface and configured-identifier match |
| Percent-encoded known email in body | Raw match after decoding, without exporting the email value |
| Same matched hash on two controlled sites | One linkability group listing both sites |
| Unrelated hash on CDN request | No configured-identifier finding |
| Site and static subdomain under abc.net.au | First-party classification |
| Missing GeoIP database | Country/offshore unknown, explicit coverage note |
| Reprocessing the same raw directory | Identical request/session counts |
| Malformed batch after a valid run | Transaction rollback preserves the earlier derived dataset |
| Retest with failed navigation or changed identity/rules | Disappearance classified as inconclusive |
| Tag removed in an otherwise equivalent retest | Target finding not observed in that retest |
| Guard: identifier in a URL to an unlisted collector | Collector receives nothing (receiver-side count 0) |
| Guard: POST body sent twice to a collector | Exactly one receipt; a session rule scoped to that source/destination pair |
| Guard: sponsored-result click | Ad redirector logs no click from the user's page; advertiser receives no click ID |
| Guard: same-site POST, documentation link | Still function (negative controls) |
| Guard: a script-opened "Sign in with…" window to another site | Blocked unless the site is in Allow sites: a known false positive of the popup check; record it |
| Pi: sandbox account requests the router | Times out (nftables drop), while a public site loads |
| Pi: DNS client outside the allowed networks | REFUSED and not logged |

## Questions to prepare for

**How is this useful beyond a graph?** The audit identifies a destination and payload surface, explains the match, suggests what a developer should inspect, and retains a before/after comparison.

**How do you know the email hash belongs to this test identity?** The detector computes supported deterministic hashes from the locally configured test identity, then matches the complete hex value. It does not infer a person's identity from any random hash.

**Does an empty identity file invalidate the whole study?** Tracker and destination measurements may still run, but the identity-leakage component has no configured-identifier coverage. A public anonymous page visit might never transmit an email even with an identity configured. The controlled experiment tests the matching mechanism separately.

**Is a foreign endpoint a privacy breach?** No legal verdict follows from that observation. It is an endpoint-location estimate and a reason to investigate the data flow and context. The application no longer uses an invented legal adequacy whitelist.

**Is every third party a tracker?** No. The classifier stores party relationship separately from supported tracker reference matches; a CDN negative control demonstrates the difference.

**Did you prove fingerprinting?** The crawler logs selected API calls at session level. Those APIs have legitimate uses; the observation does not prove intent or a particular receiving request.

**What about the 99.3% ML result in the old charter?** The supplied snapshot lacks the raw training/evaluation evidence for that figure. It is not presented as a reproduced result. Learning blocklist-derived labels is different from independent tracker-detection accuracy.

**Why a Raspberry Pi, not just the laptop?** The quarantined link is opened on a different machine, by an account the Pi's firewall keeps off the home network, so a malicious landing page never runs next to the student's browser profile. The Pi also runs continuously, which makes the weekly study and the DNS watch possible.

**Can a page in the sandbox escape?** The preview browser has no cookies, logins or storage, Chromium's own process sandbox stays on, the service runs unprivileged under systemd hardening, and nftables drops LAN traffic for its account. This reduces risk; it is not a malware detonation VM, and the report should say so.

**Can you sell it now?** It is a tested local prototype with a proposed user group. External-user usability, independent detection evaluation, data controls, licensing and willingness to pay remain to be established.

## Final report structure

1. Problem, intended user and research question.
2. Scope, ethics, data handling and measurement protocol.
3. Shared architecture and design decisions.
4. Implementation of matching, evidence generation and retest comparison.
5. Controlled experiment and negative controls.
6. Actual 50-site results when collected, with capture coverage and justified analysis.
7. Evaluation with measured precision/recall where ground truth exists, usability and reproducibility.
8. Limitations, development priorities and a proposed commercial validation plan.

Reference the original assessment rubric for required sections and word counts. The original Charter/Plan documents remain historical artifacts; reconcile their completion claims with current evidence before submission.
