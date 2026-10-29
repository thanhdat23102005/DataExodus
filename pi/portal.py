"""DataExodus Box captive portal: the page a phone sees when it joins the Pi's Wi-Fi.

A visitor (for example an assessor with their own phone) joins the DataExodus
Wi-Fi (pi/hotspot.sh). The DNS watch answers the phone's connectivity check with
this portal, so the phone opens the welcome page by itself. From there:

  Check a link    paste a link or a whole scam text; the Pi opens it in the
                  isolated sandbox (protection/sandbox.py) and shows a 0-100
                  score with the reasons, the redirect chain, a screenshot and
                  the companies the page contacts. The phone never loads it.
  Safe Browse     drive the suspicious page on the Pi by tapping its picture.
  My device       optional, opt-in: which companies the phone's apps contact
                  and where their servers are, with per-device tracker blocking
                  and "Forget this device".

Security: answers only clients on the hotspot network and only its own host
names (DNS rebinding), refuses cross-site form posts, sends no JavaScript (CSP
default-src 'none'), escapes every value it did not write, and talks to the
sandbox service only on the Pi's loopback with the Guard token.

  python -m pi.portal        (PORTAL_IP, PORTAL_PORT, PORTAL_NET from the settings file)
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

from pi import dns_report
from pi.devices import Devices
from pi.dnswatch import CAPTIVE_NAMES
from protection.api import checked_url
from protection.verdict import LEVELS, NOTE, RULES

app = FastAPI(title="DataExodus Box portal", docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(__file__).resolve().parents[1]
CSS = (Path(__file__).with_name("portal.css")).read_text(encoding="utf-8")
e = lambda value: html.escape(str(value), quote=True)  # noqa: E731
B64 = re.compile(r"^[A-Za-z0-9+/=]+$")
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.I)
BARE_DOMAIN = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/\S*)?$")
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Connectivity-check answers that tell an operating system "no sign-in needed".
PROBE_REPLIES = {
    "/hotspot-detect.html": ("<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>", "text/html"),
    "/library/test/success.html": ("<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>", "text/html"),
    "/connecttest.txt": ("Microsoft Connect Test", "text/plain"),
    "/ncsi.txt": ("Microsoft NCSI", "text/plain"),
    "/success.txt": ("success\n", "text/plain"),
    "/canonical.html": ('<meta http-equiv="refresh" content="0;url=https://support.mozilla.org/kb/captive-portal"/>',
                        "text/html"),
    "/check_network_status.txt": ("NetworkManager is online\n", "text/plain"),
    "/nm": ("NetworkManager is online\n", "text/plain"),
}


# ------------------------------------------------------------------ settings

def portal_ip() -> str:
    return os.getenv("PORTAL_IP", "10.42.0.1")


def portal_port() -> int:
    return int(os.getenv("PORTAL_PORT", "80"))


def portal_name() -> str:
    return os.getenv("PORTAL_HOSTNAME", "dataexodus.home.arpa").lower()


def portal_net():
    return ipaddress.ip_network(os.getenv("PORTAL_NET", "10.42.0.0/24"), strict=False)


def origin(host: str | None = None) -> str:
    port = portal_port()
    return f"http://{host or portal_ip()}" + ("" if port == 80 else f":{port}")


def state_dir() -> Path:
    return Path(os.getenv("DATAEXODUS_STATE", ROOT / "data"))


def dns_db() -> Path:
    return Path(os.getenv("DNSWATCH_DB", state_dir() / "dnswatch.sqlite"))


def retention_hours() -> int:
    return int(os.getenv("PORTAL_RETENTION_HOURS", "24"))


_devices: dict[str, Devices] = {}


def devices() -> Devices:
    path = os.getenv("PORTAL_DEVICES", str(state_dir() / "portal" / "devices.json"))
    if path not in _devices:
        _devices[path] = Devices(path)
    return _devices[path]


def guard(method: str, path: str, **kwargs):
    base = os.getenv("PORTAL_GUARD_API", "http://127.0.0.1:8010")
    headers = {"Authorization": "Bearer " + os.getenv("DATAEXODUS_GUARD_TOKEN", "")}
    return requests.request(method, base + path, headers=headers, timeout=kwargs.pop("timeout", 75), **kwargs)


# ------------------------------------------------------------- jobs, limits

class Job:
    def __init__(self, owner: str, url: str):
        self.id = secrets.token_urlsafe(18)
        self.owner, self.url = owner, url
        self.created = time.time()
        self.result: dict | None = None
        self.error: str | None = None


JOBS: OrderedDict[str, Job] = OrderedDict()
SESSIONS: dict[str, dict] = {}  # Safe Browse: session id -> {"owner", "state"}
RATE: dict[str, deque] = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="portal-check")


def allow(kind: str, owner: str, limit: int, window: int = 600) -> bool:
    with LOCK:
        stamps = RATE.setdefault(f"{kind}:{owner}", deque())
        now = time.time()
        while stamps and stamps[0] < now - window:
            stamps.popleft()
        if len(stamps) >= limit:
            return False
        stamps.append(now)
        return True


def run_job(job: Job):
    try:
        response = guard("POST", "/sandbox/preview", json={"url": job.url})
        if response.status_code != 200:
            job.error = f"The sandbox service answered {response.status_code}."
        else:
            job.result = response.json()
    except (requests.RequestException, ValueError):
        job.error = "The sandbox service is not reachable on the Pi (is dataexodus-guard running?)."


def start_job(owner: str, url: str) -> Job:
    job = Job(owner, url)
    with LOCK:
        JOBS[job.id] = job
        while len(JOBS) > 60 or (JOBS and next(iter(JOBS.values())).created < time.time() - 3600):
            JOBS.popitem(last=False)
    POOL.submit(run_job, job)
    return job


def extract_url(text: str) -> str | None:
    """A link from whatever was pasted: a URL, a bare domain, or a whole text message."""
    text = (text or "").strip()[:4096]
    found = URL_IN_TEXT.search(text)
    if found:
        url = found.group(0).rstrip(").,;:!?'\"")
    elif BARE_DOMAIN.match(text):
        url = "https://" + text
    else:
        return None
    try:
        return checked_url(url)
    except ValueError:
        return None


# ---------------------------------------------------------------- middleware

def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def on_hotspot(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in portal_net()
    except ValueError:
        return False


@app.middleware("http")
async def hotspot_only(request: Request, call_next):
    ip = client_ip(request)
    if not on_hotspot(ip):
        return PlainTextResponse("This page is only for devices on the DataExodus Wi-Fi.", status_code=403)
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower().rstrip(".")
    if host in CAPTIVE_NAMES:
        # A connectivity check (the DNS watch sent it here): pass once the
        # visitor has made a choice on the welcome page, else show that page.
        if devices().get(ip):
            body, mime = PROBE_REPLIES.get(request.url.path, ("", ""))
            return Response(body, media_type=mime) if body else Response(status_code=204)
        return RedirectResponse(origin() + "/", status_code=302)
    if host not in {portal_ip(), portal_name()}:
        # Any other name is a DNS-rebinding attempt by a web page.
        return PlainTextResponse("Unknown host", status_code=403)
    if request.method == "POST":
        sent_from = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        if (sent_from and sent_from not in {origin(), origin(portal_name())}) or \
                (fetch_site and fetch_site not in ("same-origin", "none")):
            return PlainTextResponse("Cross-site request refused", status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = ("default-src 'none'; style-src 'self'; img-src data:; "
                                                   "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Not "no-referrer": with it, browsers send "Origin: null" on the portal's
    # own form posts. "same-origin" still sends nothing to other sites.
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers.setdefault("Cache-Control", "no-store")
    return response


async def form(request: Request) -> dict[str, str]:
    body = (await request.body())[:16384].decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def see_other(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


# ------------------------------------------------------------------- layout

def layout(title: str, body: str, refresh: int | None = None) -> HTMLResponse:
    meta = f"<meta http-equiv=refresh content='{int(refresh)}'>" if refresh else ""
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"{meta}<title>{e(title)} · DataExodus Box</title><link rel=stylesheet href='/portal.css'></head><body>"
        "<header><a class=brand href='/'>DataExodus Box</a><nav><a href='/check'>Check a link</a>"
        "<a href='/me'>My device</a><a href='/about'>How it works</a></nav></header>"
        f"<main>{body}</main><footer>DataExodus: a privacy prototype on a Raspberry Pi 5. "
        "Links are opened on the Pi, never on your device. A low score is not a guarantee.</footer></body></html>")


@app.get("/portal.css")
def stylesheet():
    return Response(CSS, media_type="text/css", headers={"Cache-Control": "max-age=3600"})


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


# --------------------------------------------------------------- welcome

WHAT_IS_RECORDED = (
    "<details><summary>What is recorded, and for how long</summary><ul class=small>"
    "<li>Only if you tick <b>Show my device's connections</b>: the server names your device looks up (DNS), "
    "the time and the addresses returned. Not page contents, messages or passwords: HTTPS keeps those encrypted, "
    "and this Pi does not inspect your traffic.</li>"
    "<li>Kept on this Raspberry Pi for {hours} hours, then deleted automatically. "
    "<b>Forget this device</b> deletes it at once. Only this device is shown its lookups; the box "
    "owner's dashboard leaves them out.</li>"
    "<li>Your device is recognised by its Wi-Fi hardware address on this network. Most phones use a random "
    "one for each network.</li>"
    "<li>Links you check are opened by the Pi. The link and its result stay in the Pi's memory for an hour.</li>"
    "<li>Leave the box unticked to use the Wi-Fi and the link checker with nothing recorded.</li></ul></details>")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    me = devices().get(client_ip(request))
    if not me:
        return layout("Welcome", (
            "<div class=eyebrow>DataExodus Box</div><h1>Welcome to the DataExodus Wi-Fi</h1>"
            "<p>This Wi-Fi runs on a Raspberry Pi 5 as a privacy demonstration. It gives you internet access "
            "and two tools:</p><div class=tiles>"
            "<div class=tile><b>Check a link</b>The Pi opens a suspicious link in an isolated browser, scores it "
            "and shows what it tried to do. Your device never loads it.</div>"
            "<div class=tile><b>See your device's connections</b>Optional: which companies your apps contact, and in "
            "which countries their servers are.</div></div>"
            "<form class=card method=post action='/join'>"
            "<label class=check><input type=checkbox name=watch value=1 checked><span><b>Show my device's "
            "connections</b> on this page<br><span class='muted small'>Records the server names your device looks up, "
            f"for {retention_hours()} hours, visible only on this device.</span></span></label>"
            "<label class=check><input type=checkbox name=block value=1><span><b>Block known trackers</b> on my device"
            "<br><span class='muted small'>Tracker and malware names get no answer. Some apps or adverts may stop "
            "working while this is on.</span></span></label>"
            "<button>Join and continue</button></form>" + WHAT_IS_RECORDED.format(hours=retention_hours())))
    watching = "on" if me.get("watch") else "off"
    blocking = "on" if me.get("block") else "off"
    return layout("Home", (
        "<div class=eyebrow>DataExodus Box</div><h1>You're online</h1>"
        f"<p class=muted>This page is at <span class=url>{e(origin())}</span> or "
        f"<span class=url>{e(origin(portal_name()))}</span> whenever you are on this Wi-Fi.</p><div class=tiles>"
        "<a class=tile href='/check'><b>Check a link</b>Paste a link, or a whole text message or email. "
        "Try the samples to see a scam caught.</a>"
        f"<a class=tile href='/me'><b>My device</b>Connections shown: {watching} · tracker blocking: {blocking}</a>"
        "<a class=tile href='/about'><b>How it works</b>The sandbox, the score and what this Wi-Fi records.</a></div>"))


@app.post("/join")
async def join(request: Request):
    fields = await form(request)
    devices().set(client_ip(request), watch=fields.get("watch") == "1", block=fields.get("block") == "1")
    return see_other("/")


def joined(request: Request) -> dict | None:
    return devices().get(client_ip(request))


# ------------------------------------------------------------ link check

def samples() -> list[dict]:
    if os.getenv("PORTAL_SAMPLES", "1") != "1":
        return []
    from examples.sample_links import samples as sample_list
    return sample_list(port=int(os.getenv("PORTAL_SAMPLES_PORT", "8030")))


@app.get("/check", response_class=HTMLResponse)
def check_page(request: Request, error: str = ""):
    if not joined(request):
        return see_other("/")
    message = {"url": "No link found. Paste a link starting with http:// or https://, or a site name.",
               "busy": "You have checked a lot of links in a short time. Please wait a few minutes.",
               "browse": "Safe Browse is busy (one visitor at a time). Try again in a minute.",
               "gone": "That check or Safe Browse session has ended."}.get(error, "")
    sample_rows = "".join(
        f"<div class=sample><b>{e(s['title'])}</b><br><span class='muted small'>{e(s['what'])}</span>"
        f"<form method=post action='/check'><input type=hidden name=text value='{e(s['url'])}'>"
        "<button class=secondary>Check this sample</button></form></div>" for s in samples())
    return layout("Check a link", (
        "<h1>Check a link</h1><p>Paste a link, or a whole text message or email that contains one. The Raspberry Pi "
        "opens it in an isolated browser and tells you what it found. <b>Your device does not open it.</b></p>"
        + (f"<p class='banner danger small'>{e(message)}</p>" if message else "")
        + "<form class=card method=post action='/check'><textarea name=text required "
          "placeholder='e.g. Your parcel is on hold, pay the redelivery fee: https://...'></textarea>"
          "<button>Check link</button><button class=secondary formaction='/browse'>Open in Safe Browse</button></form>"
        + (f"<h2>Try a sample</h2><div class=card>{sample_rows}<p class='tiny muted'>Fictional sites served "
           "by the Pi itself, so they work without internet. Nothing harmful is on them.</p></div>" if sample_rows else "")))


@app.post("/check")
async def check(request: Request):
    me = joined(request)
    if not me:
        return see_other("/")
    url = extract_url((await form(request)).get("text", ""))
    if not url:
        return see_other("/check?error=url")
    if not allow("check", me["key"], limit=12):
        return see_other("/check?error=busy")
    return see_other(f"/check/{start_job(me['key'], url).id}")


def owned_job(request: Request, jid: str) -> Job | None:
    me = joined(request)
    job = JOBS.get(jid) if JOB_ID.match(jid or "") else None
    return job if me and job and job.owner == me["key"] else None


def describe_signals(r: dict) -> list[str]:
    out = []
    if r.get("downloads"):
        out.append("Tried to download: " + ", ".join(r["downloads"][:3]) + " (blocked by the sandbox)")
    if r.get("popups"):
        out.append(f"Tried to open {r['popups']} new window(s) (closed)")
    if r.get("dialogs"):
        out.append(f"Opened {r['dialogs']} dialog box(es) (dismissed)")
    names = {"notification_prompt": "Asked to send notifications", "clipboard_write": "Wrote to the clipboard",
             "device_prompt": "Asked for location, camera or microphone",
             "fingerprinting": "Read canvas/graphics details (device fingerprinting)"}
    out += [names[s] for s in r.get("signals") or [] if s in names]
    if r.get("refused_internal"):
        out.append(f"Tried to reach {len(r['refused_internal'])} local-network address(es) (refused)")
    return out


def render_result(job: Job) -> str:
    r = job.result or {}
    a = r.get("assessment") or {"level": "unknown", "label": "Not assessed", "score": None, "reasons": [],
                                "note": "This sandbox service did not return a score."}
    if not r.get("ok"):
        a = {**a, "level": "unknown", "label": "Could not open the link"}
    level = a.get("level") if a.get("level") in ("low", "caution", "danger") else "unknown"
    score = "" if a.get("score") is None else f"<div class=score>Score {int(a['score'])} / 100</div>"
    advice = {"low": "Nothing risky was seen in one visit. Still be careful with sign-in pages and payments.",
              "caution": "Be careful: this link tracks you or behaves like an advert or scam. Do not enter details.",
              "danger": "We recommend you do not open this link on your device.",
              "unknown": e(r.get("error") or job.error or "")}[level]
    reasons = "".join(f"<li><span class=points>+{int(x['points'])}</span><span>{e(x['text'])}</span></li>"
                      for x in a.get("reasons", [])) or "<li><span>No risk signals were observed.</span></li>"
    chain = "".join(f"<li class=url>{e(hop)}</li>" for hop in r.get("redirect_chain") or [job.url])
    shot = r.get("screenshot_jpeg_b64")
    image = (f"<img class=shot alt='Screenshot taken inside the sandbox' src='data:image/jpeg;base64,{shot}'>"
             if isinstance(shot, str) and B64.match(shot) else "<p class=muted>No screenshot.</p>")
    trackers = r.get("trackers") or []
    tracker_rows = "".join(
        f"<tr><td>{e(t.get('domain'))}</td><td>{e(t.get('owner') or '')}</td><td>{e(t.get('country') or '?')}</td></tr>"
        for t in trackers[:25])
    third = r.get("third_parties") or []
    if r.get("classifier_available") is False:
        tracker_note = "<p class=muted>Tracker lists are not installed on the Pi, so trackers are not recognised.</p>"
    else:
        tracker_note = "" if trackers else "<p>No recognised trackers.</p>"
    actions = "".join(f"<li>{e(x)}</li>" for x in describe_signals(r)) or "<li>Nothing unusual.</li>"
    clean = r.get("clean_url")
    clean_html = ""
    if clean:
        clean_html = ("<h3>Clean link (tracking IDs removed)</h3>"
                      f"<input type=text readonly value='{e(clean)}' aria-label='Clean link'>")
        if (urlsplit(clean).hostname or "").startswith("127."):
            clean_html += "<p class='small muted'>Sample sites exist only inside the Pi, so they cannot be opened on your device.</p>"
        elif level == "low":
            clean_html += f"<p><a class=button href='{e(clean)}' rel='noopener noreferrer' target=_blank>Open clean link</a></p>"
    return (
        f"<div class='banner {level}'><div class=label>{e(a.get('label'))}</div>{score}<p>{advice}</p></div>"
        "<div class=card><h2>Why</h2><ul class=reasons>" + reasons + "</ul>"
        f"<p class='tiny muted'>{e(a.get('note') or NOTE)}</p></div>"
        "<form method=post action='/browse'><input type=hidden name=job value='" + e(job.id) + "'>"
        "<button>Open in Safe Browse</button><a class='button secondary' href='/check'>Check another link</a></form>"
        "<div class=card><h2>Where the link goes</h2><ol class=chain>" + chain + "</ol>" + clean_html + "</div>"
        f"<div class=card><h2>What the page looked like</h2>{image}"
        f"<p class='muted small'>{e(r.get('title') or '')}</p></div>"
        "<div class=card><h2>What the page tried to do</h2><ul>" + actions + "</ul></div>"
        f"<div class=card><h2>Trackers ({len(trackers)}) and other companies ({len(third)})</h2>{tracker_note}"
        + (f"<table><tr><th>Tracker</th><th>Company</th><th>Server country</th></tr>{tracker_rows}</table>" if tracker_rows else "")
        + (f"<p class='small muted'>Other sites contacted: {e(', '.join(third[:15]))}</p>" if third else "")
        + f"<p class='tiny muted'>Opened on: {e(r.get('sandbox_host') or 'the sandbox')}. The sandbox has no cookies, "
          "logins or saved data, and cannot reach this network's devices.</p></div>")


@app.get("/check/{jid}", response_class=HTMLResponse)
def check_result(request: Request, jid: str):
    job = owned_job(request, jid)
    if not job:
        return see_other("/check?error=gone")
    if job.result is None and job.error is None:
        return layout("Checking…", (
            "<h1>Checking the link…</h1><div class='banner unknown'><p>The Raspberry Pi is opening the link in an "
            "isolated browser. This takes 10 to 30 seconds.</p></div>"
            f"<p class=url>{e(job.url)}</p>"), refresh=2)
    return layout("Result", "<h1>Link check</h1>" + f"<p class=url>{e(job.url)}</p>" + render_result(job))


# ------------------------------------------------------------ Safe Browse

@app.post("/browse")
async def browse_start(request: Request):
    me = joined(request)
    if not me:
        return see_other("/")
    fields = await form(request)
    job = owned_job(request, fields.get("job", ""))
    url = job.url if job else extract_url(fields.get("text", ""))
    if not url:
        return see_other("/check?error=url")
    if not allow("browse", me["key"], limit=8):
        return see_other("/check?error=busy")
    for sid, session in list(SESSIONS.items()):
        if session["owner"] == me["key"]:  # one session per device: end the previous one
            SESSIONS.pop(sid, None)
            try:
                guard("DELETE", f"/sandbox/browse/{sid}", timeout=10)
            except requests.RequestException:
                pass
    try:
        response = guard("POST", "/sandbox/browse", json={"url": url}, timeout=60)
    except requests.RequestException:
        return see_other("/check?error=browse")
    state = response.json() if response.status_code == 200 else {}
    if not state.get("ok") or not JOB_ID.match(str(state.get("id", ""))):
        return see_other("/check?error=browse")
    SESSIONS[state["id"]] = {"owner": me["key"], "state": state}
    return see_other(f"/browse/{state['id']}")


def owned_session(request: Request, sid: str) -> dict | None:
    me = joined(request)
    session = SESSIONS.get(sid) if JOB_ID.match(sid or "") else None
    return session if me and session and session["owner"] == me["key"] else None


@app.get("/browse/{sid}", response_class=HTMLResponse)
def browse_page(request: Request, sid: str):
    session = owned_session(request, sid)
    if not session:
        return see_other("/check?error=gone")
    s = session["state"]
    shot = s.get("screenshot_jpeg_b64")
    width, height = int(s.get("width") or 360), int(s.get("height") or 640)
    screen = (f"<input class=screen type=image name=tap width={width} height={height} "
              f"alt='The page, running on the Raspberry Pi. Tap to click.' src='data:image/jpeg;base64,{shot}'>"
              if isinstance(shot, str) and B64.match(shot) else "<p>No picture of the page yet. Tap Refresh.</p>")
    seen = describe_signals(s)
    if s.get("third_party_sites"):
        seen.append(f"Contacted {int(s['third_party_sites'])} other site(s)")
    return layout("Safe Browse", (
        "<h1>Safe Browse</h1><p class=small>This page runs on the Raspberry Pi; you see pictures of it. "
        "<b>Tap the picture to click.</b> Never type real passwords or card numbers here.</p>"
        f"<p class=url>{e(s.get('url'))}</p>"
        + (f"<p class='banner caution small'>{e(s['error'])}</p>" if s.get("error") else "")
        + f"<form method=post action='/browse/{e(sid)}'><div class=screen-wrap>{screen}</div>"
          "<div class=controls><button name=do value=up class=secondary>▲ Up</button>"
          "<button name=do value=down class=secondary>▼ Down</button>"
          "<button name=do value=back class=secondary>◀ Back</button>"
          "<button name=do value=refresh class=secondary>⟳ Refresh</button>"
          "<button name=do value=end class=danger>End</button></div></form>"
          # A separate form: pressing Enter in the text box must type, not tap the picture.
          f"<form method=post action='/browse/{e(sid)}' class=typebar>"
          "<input type=text name=text maxlength=200 autocomplete=off "
          "placeholder='Tap a field in the picture, then type here' aria-label='Text to type'>"
          "<button name=do value=type class=secondary>Type</button>"
          "<button name=do value=enter class=secondary>Enter ↵</button></form>"
        + "<div class=card><h3>Seen in this session</h3><ul class=small>"
        + ("".join(f"<li>{e(x)}</li>" for x in seen) or "<li>Nothing unusual yet.</li>") + "</ul>"
        + f"<p class='tiny muted'>Ends after 2 minutes without a tap, 10 minutes at most "
          f"(about {int(s.get('expires_in') or 0)} s left). Opened on: {e(s.get('sandbox_host') or 'the sandbox')}.</p></div>"))


@app.post("/browse/{sid}")
async def browse_act(request: Request, sid: str):
    session = owned_session(request, sid)
    if not session:
        return see_other("/check?error=gone")
    fields = await form(request)
    width, height = int(session["state"].get("width") or 360), int(session["state"].get("height") or 640)
    action: dict | None
    if "tap.x" in fields:
        try:
            action = {"action": "tap", "x": min(max(int(fields["tap.x"]), 0), width - 1),
                      "y": min(max(int(fields.get("tap.y", "0")), 0), height - 1)}
        except ValueError:
            action = None
    else:
        action = {"up": {"action": "scroll", "dy": -450}, "down": {"action": "scroll", "dy": 450},
                  "back": {"action": "back"}, "enter": {"action": "key", "key": "Enter"},
                  "type": {"action": "type", "text": fields.get("text", "")[:200]}}.get(fields.get("do", ""))
    if fields.get("do") == "end":
        SESSIONS.pop(sid, None)
        try:
            guard("DELETE", f"/sandbox/browse/{sid}", timeout=10)
        except requests.RequestException:
            pass
        return see_other("/check")
    try:
        if action is None:  # refresh: a new picture of the page as it is now
            response = guard("GET", f"/sandbox/browse/{sid}", timeout=45)
        else:
            response = guard("POST", f"/sandbox/browse/{sid}", json=action, timeout=60)
    except requests.RequestException:
        return see_other(f"/browse/{sid}")
    if response.status_code == 404:
        SESSIONS.pop(sid, None)
        return see_other("/check?error=gone")
    if response.status_code == 200:
        session["state"] = response.json()
    return see_other(f"/browse/{sid}")


# ------------------------------------------------------------- my device

_classifier = {"key": None, "value": None}


def classifier():
    blocklists = Path(os.getenv("BLOCKLIST_DIR", ROOT / "data" / "blocklists"))
    try:
        key = tuple(p.stat().st_mtime for p in sorted(blocklists.iterdir()))
    except OSError:
        return False
    if _classifier["key"] != key:
        _classifier.update(key=key, value=dns_report._classifier(blocklists) or False)
    return _classifier["value"]


@app.get("/me", response_class=HTMLResponse)
def my_device(request: Request, live: int = 1):
    me = joined(request)
    if not me:
        return see_other("/")
    settings = ("<form class=card method=post action='/me'><h2>Settings for this device</h2>"
                f"<label class=check><input type=checkbox name=watch value=1{' checked' if me.get('watch') else ''}>"
                "<span><b>Show my device's connections</b></span></label>"
                f"<label class=check><input type=checkbox name=block value=1{' checked' if me.get('block') else ''}>"
                "<span><b>Block known trackers</b> on my device</span></label><button>Save</button></form>"
                "<form method=post action='/forget'><button class=danger>Forget this device</button>"
                "<span class='small muted'> Deletes this device's lookups and choices now.</span></form>")
    if not me.get("watch"):
        return layout("My device", "<h1>My device</h1><p>Showing connections is off, so nothing is recorded for this "
                      "device. Switch it on below to see which companies your apps contact.</p>" + settings)
    s = dns_report.summarise(dns_db(), hours=retention_hours(), classifier=classifier(), device=me["key"],
                             since=me.get("watch_since"), recent=40)
    if not s.get("available"):
        s = {"queries": 0, "tracker_queries": 0, "blocked": 0, "owners": [], "countries": [], "recent": [],
             "located_answers": 0, "offshore_answers": 0, "reference_lists": False}
    owners = "".join(f"<tr><td>{e(o)}</td><td>{int(n)}</td></tr>" for o, n in s["owners"][:12])
    countries = "".join(f"<tr><td>{e(c)}</td><td>{int(n)}</td></tr>" for c, n in s["countries"][:12])
    rows = "".join(
        f"<tr><td class='tiny nowrap'>{datetime.fromtimestamp(r['ts']).strftime('%H:%M')}</td><td class=url>{e(r['name'])}"
        + ("<span class='badge tracker'>tracker</span>" if r["tracker"] else "")
        + ("<span class='badge blocked'>blocked</span>" if r["blocked"] else "")
        + f"</td><td>{e(r['owner'] or '')}</td><td class=nowrap>{e(r['country'] or '')}</td></tr>" for r in s.get("recent", []))
    notes = "" if s.get("reference_lists") else ("<p class='small muted'>Tracker lists are not installed on the Pi: "
                                                  "tracker labels are unavailable, not zero.</p>")
    live_link = ("<a href='/me?live=0'>Pause live updates</a>" if live else "<a href='/me'>Resume live updates</a>")
    return layout("My device", (
        f"<h1>My device</h1><p class=small>What this device looked up on this Wi-Fi in the last {retention_hours()} "
        f"hours. Open a few apps or websites, then watch this page. {live_link}</p><div class=stats>"
        f"<div class=stat><b>{s['queries']:,}</b>lookups</div>"
        f"<div class=stat><b>{dns_report.pct(s['tracker_queries'], s['queries'])}</b>to trackers</div>"
        f"<div class=stat><b>{s['blocked']:,}</b>blocked</div>"
        f"<div class=stat><b>{dns_report.pct(s['offshore_answers'], s['located_answers'])}</b>servers outside Australia</div>"
        "</div>" + notes
        + "<div class=card><h2>Latest lookups</h2><table><tr><th>Time</th><th>Name</th><th>Company</th><th>Country</th></tr>"
        + (rows or "<tr><td colspan=4>Nothing yet. Open an app or a website.</td></tr>") + "</table></div>"
        + "<div class=card><h2>Companies behind the names</h2><table>" + (owners or "<tr><td>None recognised yet</td></tr>")
        + "</table></div><div class=card><h2>Countries of the servers</h2><table>"
        + (countries or "<tr><td>Unknown so far</td></tr>") + "</table>"
        + "<p class='tiny muted'>A lookup shows that your device was about to connect, not what it sent. The country is "
          "an estimate of where the answering server is, not proof of where data is stored.</p></div>" + settings),
        refresh=10 if live else None)


@app.post("/me")
async def save_settings(request: Request):
    if not joined(request):
        return see_other("/")
    fields = await form(request)
    devices().set(client_ip(request), watch=fields.get("watch") == "1", block=fields.get("block") == "1")
    return see_other("/me")


@app.post("/forget")
def forget(request: Request):
    me = joined(request)
    if me:
        if dns_db().exists():
            con = sqlite3.connect(dns_db(), timeout=5)
            try:
                con.execute("DELETE FROM queries WHERE device = ?", (me["key"],))
                con.commit()
            finally:
                con.close()
        with LOCK:
            for jid in [j for j, job in JOBS.items() if job.owner == me["key"]]:
                JOBS.pop(jid)
        devices().forget(client_ip(request))
    return see_other("/")


# ------------------------------------------------------------------ about

@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    rules = "".join(f"<tr><td>+{points}</td><td>{e(text)}</td></tr>" for points, text in RULES.values())
    levels = " · ".join(f"{label}: {floor}+" for floor, _, label in LEVELS)
    return layout("How it works", (
        "<h1>How it works</h1><div class=card><h2>The sandbox</h2><p>When you check a link, a fresh Chromium browser "
        "on the Raspberry Pi opens it with no cookies, logins or saved data, then is thrown away. The Pi's firewall "
        "stops that browser from reaching any device on this Wi-Fi or the home network. Downloads are cancelled, "
        "new windows closed and dialog boxes dismissed. Your device only receives a report and pictures.</p></div>"
        "<div class=card><h2>The score</h2><p>Each observation adds points (" + e(levels) + "). There is no hidden "
        "model: these are all the rules.</p><table>" + rules + "</table>"
        f"<p class='tiny muted'>{e(NOTE)}</p></div>"
        "<div class=card><h2>This Wi-Fi</h2><p>The Pi is the router for this network. Its DNS watch answers your "
        "device's name lookups. It records them only for devices that switched on <b>Show my device's connections</b>, "
        f"for {retention_hours()} hours, and shows each device only its own. <b>Block known trackers</b> refuses "
        "tracker and malware names for your device only. Apps that use encrypted DNS (DoH) bypass the watch.</p></div>"
        "<div class=card><h2>Limits</h2><ul class=small><li>One anonymous visit: a scam page can show different "
        "content to other visitors or to automated browsers.</li><li>No score proves a link safe.</li>"
        "<li>Tracker and country labels come from public lists (EasyPrivacy, DuckDuckGo Tracker Radar) and GeoLite2; "
        "unknown stays unknown.</li><li>This is a student prototype, not a security product.</li></ul></div>"))


@app.get("/api/health")
def health(request: Request):
    return JSONResponse({"ok": True, "joined": bool(joined(request))})


def main():
    import uvicorn
    uvicorn.run(app, host=portal_ip(), port=portal_port(), access_log=False, server_header=False,
                proxy_headers=False)


if __name__ == "__main__":
    main()
