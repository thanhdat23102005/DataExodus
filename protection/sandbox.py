"""Isolated link check and Safe Browse: open untrusted links in a throwaway headless Chromium.

Two ways in, both on the DataExodus service (protection/api.py):

* preview(url)       /sandbox/preview: one visit, then a report: the redirect
                     chain, a screenshot, the trackers and other companies the
                     page contacts, what it tried to do (download a file, write
                     to the clipboard, ask for notifications, collect a password
                     for another site) and a 0-100 score (protection/verdict.py).
* BrowseSession      /sandbox/browse: a live page the user drives by tapping a
                     screenshot, scrolling and typing. The page runs here; the
                     user's device only ever receives JPEG images.

In the recommended setup this runs on a Raspberry Pi 5. The laptop reaches it
through an SSH tunnel and hotspot devices through the captive portal
(pi/portal.py). Pages are loaded on a separate machine whose service account
the Pi's firewall keeps off the LAN (pi/nftables-dataexodus.nft). The sandbox
has no cookies, logins, storage, service workers or downloads, so the site
sees an anonymous visitor.

Environment:
  CHROMIUM_PATH                 use this browser (Raspberry Pi OS: /usr/bin/chromium)
  DATAEXODUS_CHROMIUM_SANDBOX   1 = keep Chromium's own process sandbox on (Pi default)
  SANDBOX_SLOTS                 concurrent link checks (default 2; a Pi 5 copes with two)
  SANDBOX_BROWSE_SESSIONS       concurrent Safe Browse sessions (default 1)
  SANDBOX_ALLOW_HOSTS           local sample sites only, e.g. 127.0.0.48/28; never outside the lab
  BLOCKLIST_DIR                 reference lists for tracker and URLhaus labels (default data/blocklists)
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import os
import re
import secrets
import socket
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Kept identical to AD_CLICK in guard/core.js (tests/test_guard_manifest.py).
AD_CLICK_PATTERNS = {
    "Google Ads": r"^https?://([a-z0-9-]+\.)*(googleadservices\.com|doubleclick\.net|googlesyndication\.com)/",
    "Google Search ad": r"^https?://(www\.)?google\.[a-z.]+/aclk\?",
    "Microsoft Ads": r"^https?://(www\.)?bing\.com/aclick\?",
    "Amazon Ads": r"^https?://([a-z0-9-]+\.)*amazon-adsystem\.com/",
    "Taboola": r"^https?://trc\.taboola\.com/",
    "Outbrain": r"^https?://paid\.outbrain\.com/",
    "Criteo": r"^https?://([a-z0-9-]+\.)*criteo\.(com|net)/",
    "Xandr": r"^https?://([a-z0-9-]+\.)*adnxs\.com/",
}
_AD_CLICK_RE = {name: re.compile(p, re.I) for name, p in AD_CLICK_PATTERNS.items()}

# Click-ID / campaign parameters removed before the destination is opened for
# real, so the advertiser cannot tie the visit back to the click. Same list as
# TRACKING_PARAMS in guard/core.js.
TRACKING_PARAMS = {
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "fbclid", "msclkid", "ttclid",
    "twclid", "li_fat_id", "mc_eid", "_hsenc", "_hsmi", "yclid", "igshid", "epik", "s_cid",
}

# What a page tries to do, reported by wrappers installed before any page
# script runs (every frame). A page can add signals but cannot remove one: the
# wrapper reports before calling the real function.
SIGNALS = {"notification_prompt", "clipboard_write", "device_prompt", "fingerprinting"}
SIGNAL_SCRIPT = r"""(() => {
  const report = window.__dataexodus_signal;
  if (typeof report !== "function") return;
  const seen = new Set();
  const hit = name => { if (seen.has(name)) return; seen.add(name); try { report(name); } catch (e) {} };
  const wrap = (owner, name, signal, test) => {
    if (!owner || typeof owner[name] !== "function") return;
    const original = owner[name];
    Object.defineProperty(owner, name, {configurable: true, writable: true, value: function (...args) {
      if (!test || test(args)) hit(signal);
      return original.apply(this, args);
    }});
  };
  if (window.Notification) wrap(Notification, "requestPermission", "notification_prompt");
  if (window.PushManager) wrap(PushManager.prototype, "subscribe", "notification_prompt");
  if (window.Clipboard) { wrap(Clipboard.prototype, "writeText", "clipboard_write"); wrap(Clipboard.prototype, "write", "clipboard_write"); }
  wrap(Document.prototype, "execCommand", "clipboard_write", a => /^(copy|cut)$/i.test(String(a[0])));
  if (window.Geolocation) { wrap(Geolocation.prototype, "getCurrentPosition", "device_prompt"); wrap(Geolocation.prototype, "watchPosition", "device_prompt"); }
  if (window.MediaDevices) wrap(MediaDevices.prototype, "getUserMedia", "device_prompt");
  wrap(HTMLCanvasElement.prototype, "toDataURL", "fingerprinting");
  if (window.CanvasRenderingContext2D) wrap(CanvasRenderingContext2D.prototype, "getImageData", "fingerprinting");
  const unmasked = a => a[0] === 37445 || a[0] === 37446;
  if (window.WebGLRenderingContext) wrap(WebGLRenderingContext.prototype, "getParameter", "fingerprinting", unmasked);
  if (window.WebGL2RenderingContext) wrap(WebGL2RenderingContext.prototype, "getParameter", "fingerprinting", unmasked);
})();"""

# Password and payment-card fields, where their forms send, and the visible
# text (for scam wording). Run in every frame after the page has loaded.
PAGE_SCRIPT = r"""() => {
  const out = {password: 0, card: 0, actions: [], text: ""};
  const cardName = /(card.?num|ccnum|cc-?num|cvv|cvc|csc|security.?code|expiry|exp.?date|expiration)/i;
  for (const input of document.querySelectorAll("input")) {
    const type = (input.type || "").toLowerCase();
    const auto = (input.getAttribute("autocomplete") || "").toLowerCase();
    const label = [input.name, input.id, input.placeholder, input.getAttribute("aria-label")].join(" ");
    const isCard = auto.startsWith("cc-") || cardName.test(label);
    if (type === "password") out.password++;
    if (isCard) out.card++;
    if ((type === "password" || isCard) && input.form) out.actions.push(input.form.action || location.href);
  }
  out.text = document.body ? document.body.innerText.slice(0, 20000) : "";
  return out;
}"""

BROWSE_VIEWPORT = {"width": 360, "height": 640}

_slots: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(max(1, int(os.getenv("SANDBOX_SLOTS", "2"))))
    return _slots


def host_label() -> str:
    """Shown with each preview so the user can see which machine opened it."""
    return os.getenv("DATAEXODUS_HOST_LABEL") or socket.gethostname()


def match_ad_click(url: str) -> str | None:
    found = next((name for name, rx in _AD_CLICK_RE.items() if rx.match(url or "")), None)
    if found is None and lab_allowed(urlparse(url or "").hostname or "") and urlparse(url).path == "/aclk":
        return "Sample ad network (local lab)"
    return found


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def _lab_entries() -> list[str]:
    # Explicit opt-in for the loopback labs (examples/guard_lab.py,
    # examples/sample_links.py), e.g. SANDBOX_ALLOW_HOSTS=127.0.0.3 or
    # 127.0.0.48/28. Never set this outside the lab.
    return [h.strip().lower() for h in os.getenv("SANDBOX_ALLOW_HOSTS", "").split(",") if h.strip()]


def lab_allowed(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    for entry in _lab_entries():
        if "/" in entry:
            try:
                if ipaddress.ip_address(host) in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        elif host == entry:
            return True
    return False


def is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified or ip in ipaddress.ip_network("100.64.0.0/10"))


@lru_cache(maxsize=1024)
def _resolves_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    return bool(infos) and all(is_public_ip(info[4][0]) for info in infos)


def is_public_url(url: str) -> bool:
    """SSRF guard: the service runs on a Pi inside the home LAN, so nothing
    opened in the sandbox may reach the router, this service or other LAN
    hosts. Checked for the first URL and again for every request the page
    makes. On the Pi the firewall enforces the same rule for the service
    account, which also covers DNS rebinding between this check and the
    browser's own lookup."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if lab_allowed(parsed.hostname):
        return True
    return _resolves_public(parsed.hostname)


async def _launch(p):
    options = {"headless": True, "chromium_sandbox": os.getenv("DATAEXODUS_CHROMIUM_SANDBOX") == "1"}
    if os.getenv("CHROMIUM_PATH"):
        options["executable_path"] = os.environ["CHROMIUM_PATH"]
    return await p.chromium.launch(**options)


def _user_agent(browser, mobile: bool) -> str:
    # Headless Chromium announces itself ("HeadlessChrome"), and some scam
    # pages show a harmless page to it. An ordinary user agent avoids the
    # simplest cloaking; it does not defeat a page that probes harder.
    major = (browser.version or "130").split(".")[0]
    if mobile:
        return (f"Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{major}.0.0.0 Mobile Safari/537.36")
    return f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"


async def _instrument(context, signals: set, requests_seen: list, refused: set):
    async def guard(route):
        target = route.request.url
        if target.startswith("data:") or await asyncio.to_thread(is_public_url, target):
            if len(requests_seen) < 2000:
                requests_seen.append(target)
            await route.continue_()
        else:
            refused.add(urlparse(target).hostname or "")
            await route.abort()

    def signal(_source, name):
        if name in SIGNALS:
            signals.add(name)

    await context.route("**/*", guard)
    await context.expose_binding("__dataexodus_signal", signal)
    await context.add_init_script(SIGNAL_SCRIPT)


async def _page_facts(page) -> dict:
    facts = {"password": 0, "card": 0, "actions": [], "text": ""}
    for frame in page.frames[:20]:
        try:
            found = await asyncio.wait_for(frame.evaluate(PAGE_SCRIPT), 3)
        except Exception:  # noqa: BLE001 - detached or cross-process frame
            continue
        if not isinstance(found, dict):
            continue
        facts["password"] += int(found.get("password") or 0)
        facts["card"] += int(found.get("card") or 0)
        facts["actions"] += [str(a)[:500] for a in (found.get("actions") or [])][:20]
        facts["text"] = (facts["text"] + "\n" + str(found.get("text") or ""))[:40000]
    facts["actions"] = list(dict.fromkeys(facts["actions"]))
    return facts


def _first_line(exc: Exception) -> str:
    return (str(exc).splitlines() or [type(exc).__name__])[0][:300]


async def preview(url: str, timeout_s: int = 15) -> dict:
    if not await asyncio.to_thread(is_public_url, url):
        return {"ok": False, "error": "Only public http(s) URLs can be opened in the sandbox.",
                "sandbox_host": host_label()}
    try:
        return await asyncio.wait_for(_preview(url, timeout_s), timeout_s + 30)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "The sandbox took too long and was stopped.", "sandbox_host": host_label()}


async def _preview(url: str, timeout_s: int) -> dict:
    from playwright.async_api import async_playwright

    requests_seen: list[str] = []
    refused: set[str] = set()
    signals: set[str] = set()
    downloads: list[str] = []
    counts = {"popups": 0, "dialogs": 0}
    async with _semaphore(), async_playwright() as p:
        try:
            browser = await _launch(p)
        except Exception as exc:  # noqa: BLE001 - reported to the user, not swallowed
            return {"ok": False, "sandbox_host": host_label(),
                    "error": "Sandbox browser failed to start (run `python -m playwright install chromium`, "
                             f"or set CHROMIUM_PATH): {_first_line(exc)}"}
        try:
            context = await browser.new_context(accept_downloads=False, service_workers="block",
                                                viewport={"width": 1280, "height": 800},
                                                user_agent=_user_agent(browser, mobile=False),
                                                locale="en-AU", timezone_id="Australia/Sydney")
            await _instrument(context, signals, requests_seen, refused)
            page = await context.new_page()

            def popup(extra):
                # Pop-ups and pop-unders opened by the page are closed, not followed.
                counts["popups"] += 1
                asyncio.ensure_future(extra.close())

            def dialog(box):
                counts["dialogs"] += 1
                asyncio.ensure_future(box.dismiss())

            context.on("page", popup)
            page.on("dialog", dialog)
            # Downloads are cancelled (accept_downloads=False); only the name is kept.
            page.on("download", lambda d: downloads.append(d.suggested_filename[:120]))
            error, response = None, None
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
                await page.wait_for_timeout(2500)  # let late trackers and scripts fire
            except Exception as exc:  # noqa: BLE001
                error = _first_line(exc)
                if "Download is starting" in error:
                    error = None
                    await page.wait_for_timeout(500)

            chain: list[str] = []
            req = response.request if response else None
            while req is not None:
                chain.append(req.url)
                req = req.redirected_from
            chain.reverse()
            final_url = page.url if page.url.startswith(("http://", "https://")) else (chain[-1] if chain else url)
            title, shot = "", None
            facts = await _page_facts(page)
            try:
                title = (await page.title())[:300]
                shot = base64.b64encode(await page.screenshot(type="jpeg", quality=55)).decode()
            except Exception:  # noqa: BLE001 - a page that dies mid-render still has a chain
                pass
        finally:
            await browser.close()

    from protection import verdict

    landscape = await asyncio.to_thread(_landscape, requests_seen, final_url, chain)
    still_ad = match_ad_click(final_url) is not None
    hosts = {urlparse(u).hostname or "" for u in [url, *chain, final_url, *requests_seen]}
    result = {
        "ok": error is None or bool(chain),
        "error": error,
        "sandbox_host": host_label(),
        "requested_url": url,
        "ad_network": match_ad_click(url),
        "redirect_chain": chain or [url],
        "final_url": final_url,
        "clean_url": None if still_ad else clean_url(final_url),
        "title": title,
        "screenshot_jpeg_b64": shot,
        "request_count": len(requests_seen),
        **landscape,
        "refused_internal": sorted(refused),
        "signals": sorted(signals),
        "downloads": downloads[:10],
        "popups": counts["popups"],
        "dialogs": counts["dialogs"],
        "forms": {"password": facts["password"], "card": facts["card"], "actions": facts["actions"]},
        "scam_phrases": verdict.scam_phrases(facts["text"]),
        "known_threat_hosts": known_threats(hosts),
    }
    result["verdict"] = "tracking" if result["trackers"] else "clean"
    result["assessment"] = verdict.assess(result, lab_hosts={h for h in hosts if lab_allowed(h)})
    return result


def _landscape(requests_seen: list[str], page_url: str, chain: list[str] | None = None) -> dict:
    """Which other sites the page contacted, which of them are recognised
    trackers (audit classifier, when its reference lists are present: python
    setup_data.py) and where their servers are (GeoLite2, when present). The
    link's own redirect hops are reported in the chain, not counted here."""
    from pipeline.classify import hostname, registrable_domain

    page_site = registrable_domain(page_url)
    hops = set(chain or [])
    domains = list(dict.fromkeys(hostname(u) for u in requests_seen if not u.startswith("data:") and u not in hops))
    third = [d for d in domains if d and registrable_domain(d) != page_site]
    third_sites = list(dict.fromkeys(registrable_domain(d) for d in third))
    try:
        classifier = _classifier()
    except Exception:  # noqa: BLE001 - classifier data is optional for the sandbox
        classifier = None
    trackers: dict[str, dict] = {}
    countries: dict[str, str] = {}
    if classifier is not None:
        for i, domain in enumerate(third):
            # Country lookups resolve names; the first 25 third parties are enough.
            info = classifier.classify("https://" + domain + "/", page_url) if i < 25 else classifier.label(domain)
            if info.get("country"):
                countries[registrable_domain(domain)] = info["country"]
            if info.get("is_tracker") and domain not in trackers:
                trackers[domain] = {"domain": domain, "owner": info.get("owner"), "category": info.get("category"),
                                    "country": info.get("country")}
    return {"trackers": list(trackers.values()), "classifier_available": classifier is not None,
            "third_parties": third_sites[:60], "third_party_countries": countries}


@lru_cache(maxsize=1)
def _classifier():
    from pipeline.classify import Classifier
    blocklists = Path(os.getenv("BLOCKLIST_DIR", "data/blocklists"))
    if not blocklists.exists():
        return None
    mmdb = blocklists / "GeoLite2-Country.mmdb"
    return Classifier.load(blocklists, mmdb if mmdb.exists() else None)


_threats: dict = {"mtime": None, "domains": frozenset()}


def threat_domains() -> frozenset:
    """URLhaus malware hosts (setup_data.py keeps a hosts-file mirror), reloaded when the file changes."""
    path = Path(os.getenv("BLOCKLIST_DIR", "data/blocklists")) / "urlhaus_hosts.txt"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return frozenset()
    if _threats["mtime"] != mtime:
        found = set()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("#", 1)[0].split()
            name = parts[1] if len(parts) == 2 and parts[0] in ("0.0.0.0", "127.0.0.1") else parts[0] if parts else ""
            if "." in name:
                found.add(name.lower().rstrip("."))
        _threats.update(mtime=mtime, domains=frozenset(found))
    return _threats["domains"]


def known_threats(hosts) -> list[str]:
    listed = threat_domains()
    found = []
    for host in sorted(h for h in hosts if h):
        labels = host.lower().split(".")
        if any(".".join(labels[i:]) in listed for i in range(len(labels) - 1)) or host.lower() in listed:
            found.append(host)
    return found[:10]


# ---------------------------------------------------------------- Safe Browse

_browse: dict[str, "BrowseSession"] = {}
_reaper: asyncio.Task | None = None


class SandboxBusy(Exception):
    """Every Safe Browse slot is in use."""


def _browse_limit() -> int:
    return max(1, int(os.getenv("SANDBOX_BROWSE_SESSIONS", "1")))


class BrowseSession:
    """One live sandbox page, driven by taps on its screenshot. Closed after
    SANDBOX_BROWSE_IDLE seconds without input (default 120) and at most
    SANDBOX_BROWSE_MAX seconds after it started (default 600)."""

    def __init__(self):
        self.id = secrets.token_urlsafe(18)
        self.created = self.used = time.monotonic()
        self.idle = int(os.getenv("SANDBOX_BROWSE_IDLE", "120"))
        self.max_age = int(os.getenv("SANDBOX_BROWSE_MAX", "600"))
        self.lock = asyncio.Lock()
        self.signals: set[str] = set()
        self.requests: list[str] = []
        self.refused: set[str] = set()
        self.downloads: list[str] = []
        self.popups = self.dialogs = 0
        self.last_tap = 0.0
        self.pending: asyncio.Task | None = None
        self.error: str | None = None
        self.pw = self.browser = self.context = self.page = None

    def expired(self) -> bool:
        now = time.monotonic()
        return now - self.used > self.idle or now - self.created > self.max_age

    async def open(self, url: str):
        from playwright.async_api import async_playwright

        self.pw = await async_playwright().start()
        self.browser = await _launch(self.pw)
        self.context = await self.browser.new_context(
            accept_downloads=False, service_workers="block", viewport=BROWSE_VIEWPORT, device_scale_factor=1,
            is_mobile=True, has_touch=True, user_agent=_user_agent(self.browser, mobile=True),
            locale="en-AU", timezone_id="Australia/Sydney")
        await _instrument(self.context, self.signals, self.requests, self.refused)
        self.page = await self.context.new_page()
        self.page.on("download", lambda d: self.downloads.append(d.suggested_filename[:120]))
        self.page.on("dialog", self._dialog)
        self.context.on("page", self._popup)
        await self._navigate(self.page.goto(url, wait_until="domcontentloaded", timeout=15000))
        await self._settle()

    def _dialog(self, box):
        self.dialogs += 1
        asyncio.ensure_future(box.dismiss())

    def _popup(self, popup):
        if popup == self.page:
            return
        self.popups += 1
        self.pending = asyncio.ensure_future(self._follow(popup))

    async def _follow(self, popup):
        # A link with target=_blank opens a new window. Its address is opened
        # in this same page when the user tapped just before; pop-unders are
        # only counted. The extra window is always closed.
        target = ""
        try:
            await popup.wait_for_url(re.compile(r"^https?://"), wait_until="commit", timeout=4000)
            target = popup.url
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                await popup.close()
            except Exception:  # noqa: BLE001
                pass
        if target and time.monotonic() - self.last_tap < 4 and await asyncio.to_thread(is_public_url, target):
            await self._navigate(self.page.goto(target, wait_until="domcontentloaded", timeout=15000))

    async def _navigate(self, step):
        try:
            await step
            self.error = None
        except Exception as exc:  # noqa: BLE001
            message = _first_line(exc)
            self.error = None if "Download is starting" in message else message

    async def _settle(self):
        await self.page.wait_for_timeout(700)
        if self.pending is not None:
            try:
                await asyncio.wait_for(self.pending, 20)
            except Exception:  # noqa: BLE001
                pass
            self.pending = None
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:  # noqa: BLE001
            pass
        await self.page.wait_for_timeout(400)

    async def act(self, action: str, x: int | None = None, y: int | None = None, dy: int | None = None,
                  text: str | None = None, key: str | None = None) -> dict:
        async with self.lock:
            self.used = time.monotonic()
            page = self.page
            if action == "tap":
                self.last_tap = time.monotonic()
                x = min(max(int(x or 0), 0), BROWSE_VIEWPORT["width"] - 1)
                y = min(max(int(y or 0), 0), BROWSE_VIEWPORT["height"] - 1)
                await self._navigate(page.mouse.click(x, y))
            elif action == "scroll":
                await self._navigate(page.mouse.wheel(0, max(-3000, min(3000, int(dy or 500)))))
            elif action == "back":
                await self._navigate(page.go_back(wait_until="domcontentloaded", timeout=10000))
            elif action == "type":
                await self._navigate(page.keyboard.type((text or "")[:200], delay=15))
            elif action == "key" and key in ("Enter", "Backspace", "Tab", "Escape"):
                await self._navigate(page.keyboard.press(key))
            elif action == "reload":
                await self._navigate(page.reload(wait_until="domcontentloaded", timeout=15000))
            await self._settle()
            return await self.state()

    async def state(self) -> dict:
        from pipeline.classify import hostname, registrable_domain

        shot, title = None, ""
        try:
            shot = base64.b64encode(await self.page.screenshot(type="jpeg", quality=60)).decode()
            title = (await self.page.title())[:200]
        except Exception:  # noqa: BLE001
            pass
        url = self.page.url
        site = registrable_domain(url)
        others = {registrable_domain(hostname(u)) for u in self.requests if not u.startswith("data:")} - {site, ""}
        now = time.monotonic()
        return {"ok": True, "id": self.id, "url": url, "title": title, "screenshot_jpeg_b64": shot,
                "width": BROWSE_VIEWPORT["width"], "height": BROWSE_VIEWPORT["height"], "error": self.error,
                "expires_in": int(max(0, min(self.idle - (now - self.used), self.max_age - (now - self.created)))),
                "signals": sorted(self.signals), "downloads": self.downloads[-5:], "popups": self.popups,
                "dialogs": self.dialogs, "refused_internal": sorted(self.refused)[:10],
                "third_party_sites": len(others), "sandbox_host": host_label()}

    async def close(self):
        for closer in (self.browser and self.browser.close, self.pw and self.pw.stop):
            if closer:
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    pass


async def _reap():
    for sid, session in list(_browse.items()):
        if session.expired():
            _browse.pop(sid, None)
            await session.close()


async def _reap_forever():
    global _reaper
    try:
        while _browse:
            await asyncio.sleep(10)
            await _reap()
    finally:
        _reaper = None


async def browse_start(url: str) -> dict:
    global _reaper
    if not await asyncio.to_thread(is_public_url, url):
        return {"ok": False, "error": "Only public http(s) URLs can be opened in the sandbox.",
                "sandbox_host": host_label()}
    await _reap()
    if len(_browse) >= _browse_limit():
        raise SandboxBusy()
    session = BrowseSession()
    _browse[session.id] = session
    try:
        await asyncio.wait_for(session.open(url), 45)
    except Exception as exc:  # noqa: BLE001
        _browse.pop(session.id, None)
        await session.close()
        message = "the sandbox took too long" if isinstance(exc, asyncio.TimeoutError) else _first_line(exc)
        return {"ok": False, "error": "Safe Browse could not start: " + message, "sandbox_host": host_label()}
    if _reaper is None:
        _reaper = asyncio.ensure_future(_reap_forever())
    return await session.state()


async def browse_act(sid: str, **action) -> dict | None:
    session = _browse.get(sid)
    if session is None or session.expired():
        await browse_close(sid)
        return None
    try:
        return await asyncio.wait_for(session.act(**action), 40)
    except asyncio.TimeoutError:
        return {**await session.state(), "error": "The page did not respond in time."}


async def browse_state(sid: str) -> dict | None:
    session = _browse.get(sid)
    if session is None or session.expired():
        await browse_close(sid)
        return None
    async with session.lock:
        return await session.state()


async def browse_close(sid: str) -> bool:
    session = _browse.pop(sid, None)
    if session is None:
        return False
    await session.close()
    return True
