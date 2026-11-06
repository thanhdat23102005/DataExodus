# Guard: the browser extension

Guard 0.5 blocks identifier collection in Chrome or Edge, holds ad clicks in
quarantine, and hands suspicious links to the Pi's sandbox for a 0–100 score
with a reason for every point. A "Dangerous" result does not get a one-tap
clean-link button.

**Verified in real Chromium 156:** the extension was loaded unpacked and driven
through the lab in two phases, baseline and protected. Every number comes from
the **receiving** side of the lab, not from a simulated block. Results:
`docs/evidence/guard-v05-browser-acceptance.json` (0.4 before it:
`guard-v04-browser-acceptance.json`). Web Risk has only been tested with mock
responses, never with a real key. Change history and test counts:
[VALIDATION.md](VALIDATION.md). For the Pi half, see
[RASPBERRY_PI.md](RASPBERRY_PI.md).

## What Guard does, and where it stops

| Signal or action | What 0.5 does | Limit |
| --- | --- | --- |
| The protected email, or its SHA-1/256/512 hex, in a URL going to a third party | A Chrome rule (DNR) blocks it **before it is sent**, including to a domain never seen before | Only the representations it supports |
| An identifier in a **POST body** to another site | Observed as the request leaves the browser. Guard writes a session rule for that *source site → destination* pair, so the next one is blocked | The first POST does get out; DNR cannot read bodies |
| A domain on the block list | Subresources blocked; a top-level navigation goes to **Quarantine** | The starter list is small; an audit export can be imported |
| **An ad click** (Google/Bing/Amazon/Taboola/Outbrain/Criteo/Xandr…) | Chrome redirects the click to Quarantine **before** the ad network hears about it | Edge does not let an extension redirect navigations to bing.com |
| A scripted popup or pop-under | **Since 0.5.1:** Chrome reports every tab a page opens, whatever method it used. A tab to another site that you did not click, or right-click, a link to is closed immediately with a small notice. No Quarantine tab | The tab can flash up before it closes, and the ad network may already have received the first request. A "Sign in with…" window opened from a button can be closed by mistake |
| A transparent overlay — an invisible link covering content | The interaction is blocked, then a Quarantine tab opens, but only on a real click | A page can disable the hook; a report that comes from the page is marked unverified |
| An ordinary link, or a same-site POST | Still works — the negative control in the lab | Test real OAuth and payment flows yourself |
| A scripted "Sign in with…" window to another site | **Can be blocked by mistake** by the popup layer | Add that site to *Allow sites* and record it as a false positive |

**The Quarantine page does not load the destination.** It shows the origin and a
count of URL components inside an `iframe sandbox=""`, under a CSP that blocks
every connection. From there:

- **Preview in isolated sandbox** — the DataExodus service opens the link in a
  throwaway headless Chromium: no cookies, no logins, no storage, no downloads,
  and it refuses internal addresses. You get the **0–100 score with every
  reason**, the redirect chain, the trackers, a screenshot and a clean link. The
  service can run on the laptop or, preferably, on the **Raspberry Pi**.
- **Open clean destination** — the advertiser's page with no click IDs
  (`gclid`, `fbclid`, `utm_*`…).
- **Open advertiser page directly** — when the ad link carries its destination
  (`adurl=`), skip the ad network entirely.
- **Open original link anyway** — the original link, for this tab only and once.

The full URL lives in `chrome.storage.session`: memory only, readable only by
the extension's own pages, gone when the tab closes. It never appears in
evidence or an export, and it goes nowhere unless you press Preview. A
navigation that carries your identifier is **not** kept — the URL is the thing
containing the identifier — so there is no Preview button for that case.

**X-Ray:** *X-Ray this page* in the popup outlines third-party tracking pixels,
hidden frames and transparent overlay links in place, with a summary table. It
is a heuristic view: it says what a page **contains**, not what it has **sent**.

## 1. Install (Windows)

PowerShell, in the project folder:

```powershell
cd C:\DataExodus
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -c requirements-tested.txt
python -m pip install dnslib        # for the Raspberry Pi / DNS watch side
python -m playwright install chromium
python setup_data.py                # EasyPrivacy, Tracker Radar, URLhaus; add --geoip-key/--geoip-account for GeoLite2
```

If you downloaded the reference data before, copy the old `data\blocklists`
folder across instead of downloading it again. If PowerShell refuses to run
`Activate.ps1`, call `.venv\Scripts\python.exe` directly.

## 2. Load Guard into Chrome or Edge

1. Open `chrome://extensions` (or `edge://extensions`) and turn on **Developer
   mode**.
2. **Remove or disable any earlier build**, and the research collector extension
   in `extension/`. Running more than one at a time mixes up the measurements.
3. **Load unpacked** and pick `C:\DataExodus\guard`.
4. Pin DataExodus Guard to the toolbar and open **Settings**.
5. Set **Protected email** to `student.demo@example.com` — a test identity, not
   a real address. Enable **Pre-block…**, **After a local identity
   observation…** and **Route ad clicks…**, then **Save and apply rules**.

## 3. The DataExodus service (sandbox, explanations, URL check)

**Option A, on the Raspberry Pi** (recommended). See
[RASPBERRY_PI.md](RASPBERRY_PI.md), run `pi\connect-pi.ps1 -CopyToken`, and
paste the token into Settings.

**Option B, on the laptop.** Always run it from the project folder, or you get
`No module named 'protection'`:

```powershell
cd C:\DataExodus
$env:DATAEXODUS_GUARD_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:DATAEXODUS_GUARD_TOKEN | Set-Clipboard
python -m uvicorn protection.api:app --host 127.0.0.1 --port 8010 --no-access-log
```

Paste the token into **Local service token** in Settings and save. It only
guards the API on this machine. Keep it out of git.

## 4. The lab

```powershell
cd C:\DataExodus
python -m examples.guard_lab
```

Open `http://127.0.0.1:8875`. Six loopback servers, one role each: the website
(.1), a listed collector (.2), an ad server with an `/aclk` redirector (.3), an
unlisted collector (.4), a collector that takes POSTs (.5), and the advertiser's
page (.6). Nothing malicious anywhere in it.

To **preview the lab's ad** in the sandbox, run the service on the laptop
(option B) with the lab-only variable:

```powershell
cd C:\DataExodus
$env:SANDBOX_ALLOW_HOSTS = "127.0.0.3,127.0.0.6"   # LAB ONLY
python -m uvicorn protection.api:app --host 127.0.0.1 --port 8010 --no-access-log
```

**Pass A (baseline):** in Settings turn **Enable network protection** off, save,
reload the lab, work through cards 01–09, then press *Refresh receiver
evidence*.

**Pass B (protected):** Ctrl+C the lab and restart it, so receipts go back to
zero. Turn protection on along with **Enable local lab rules**, save, reload,
and repeat exactly the same sequence. On card 06, send once, open the popup and
wait for *Scoped collection rules* to reach 1, then send again.

| Action | Baseline | Protected (measured in real Chromium) |
| --- | --- | --- |
| 01 email / hash / body to listed collector .2 | 3 received | 0 |
| 05 email in a URL to unlisted collector .4 | 1 | 0 |
| 06 POST twice to .5 | 2 | 1 — the first gets out, the learned rule stops the second |
| 07 same-site POST | 1 | 1, still working |
| 02 Play, 03 overlay, 08 direct ad link | 3 ad navigations | 0; one Quarantine tab each |
| 04 same-site document | opens | opens |
| 09 sponsored ad | the redirector logs the click; the advertiser receives `gclid` | the redirector **never sees your browser**; the sandbox follows the chain; the clean page opens with **no click ID** |

Try **X-Ray this page** on the lab too: the ad server's 1×1 pixel and card 03's
overlay link get outlined.

Keep `/receipts`, the popup's JSON export and the screenshots. Do not conclude
"the data was prevented" from a warning alone — the receiver's side is what
settles it.

## 5. Automated tests

```powershell
python -m pytest tests/ -q
node --test (Get-ChildItem tests\*.cjs).FullName                         # needs Node.js; the DOM tests need jsdom
python -m examples.run_guard_acceptance --out reports/guard-browser-run2 --headed
```

The acceptance script starts the service on `127.0.0.1:8010` itself (with
`SANDBOX_ALLOW_HOSTS` for the lab) if that port is free. If the tunnel to the Pi
is open, the port is taken: the script then skips the preview and takes the
*Open advertiser page directly* path instead. Each run needs a fresh output
directory.

## 6. Checking one URL, and blocking by hand

Set `WEBRISK_API_KEY` on the service. In Settings, enter a URL, confirm that you
agree to send it to Google, then press **Check URL**. On a `listed` result you
can **Block destination domain**. `not_listed` does **not** mean safe. Safe
Browsing is for non-commercial use only; commercial use needs Web Risk.

## 7. Sharing lists with the audit, and reporting evidence

```powershell
python -m protection.export_rules --out reports/guard-domains.json            # Settings -> Import a reviewed audit domain export
python -m analysis.guard_report --events "C:\path\DataExodus_Guard_Evidence.json" --out reports/guard-audit
```

The report keeps three categories apart: *Chrome rule matches* (network blocks
and navigations sent to Quarantine), unverified *page reports*, and
*observations*. Do not add them together into a "block rate".

## 8. Measuring what each layer contributes

| Build | What it measures |
| --- | --- |
| A: domain rules only | Requests actually prevented, false positives, functionality broken |
| B: A + identifier rules + learned rules | Identifiers reaching an **unlisted** collector; the second POST |
| C: B + Quarantine and sandbox | Ad clicks the ad network never recorded; click IDs that never reached the advertiser |

## 9. Limits

- Guard protects inside a browser extension's reach. It does not remove malware
  already running on the operating system.
- DNR cannot read bodies: the first POST gets out, and the learned rule only
  covers later ones.
- The MAIN-world popup hook can be disabled by a page, and a report coming from
  a page can be forged — which is why one never creates a blocking rule.
- The sandbox says what a page did in **one** anonymous visit. It is not a
  verdict on safety or malware.
- Guard matches the test email raw or as SHA-1/256/512. It does not match MD5,
  phone numbers or cookies the way the research pipeline does.
- No trial with users outside the project, and no claim of complete protection.
