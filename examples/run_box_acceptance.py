"""Real-browser acceptance run of the DataExodus Box visitor flow, on one computer.

What an assessor does with their phone on the Pi's Wi-Fi, reproduced with real
processes on loopback addresses: the captive portal (pi/portal.py) on
127.0.0.10, the sandbox service (protection/api.py, headless Chromium), the DNS
watch (pi/dnswatch.py) with hotspot rules, and the sample links
(examples/sample_links.py). A second Chromium plays the visitor's phone.

Checked: the connectivity check redirects until the visitor chooses, then
passes; the four samples get the expected levels; a pasted scam text is
recognised; Safe Browse taps a field, types and submits the fake bank form on
the sandbox (the sample collector counts the post); the DNS watch logs only
after opting in, blocks per device and answers captive names with the portal;
"Forget this device" deletes the device's lookups; cross-site posts and foreign
Host headers are refused. Not covered: the Wi-Fi radio, NetworkManager and the
Pi's firewall, which need the Pi itself (docs/HOTSPOT.md has the checks).

  python -m examples.run_box_acceptance --out docs/evidence/box-v05
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dnslib import DNSRecord

ROOT = Path(__file__).resolve().parents[1]
PORTAL_IP = "127.0.0.10"


def free_port(host="127.0.0.1", kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def wait_http(host, port, path="/", headers=None, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            con = http.client.HTTPConnection(host, port, timeout=3)
            con.request("GET", path, headers=headers or {})
            con.getresponse().read()
            return True
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{host}:{port} did not start")


def raw(method, port, path, host_header, body=None, headers=None):
    con = http.client.HTTPConnection(PORTAL_IP, port, timeout=10)
    con.request(method, path, body=body, headers={"Host": host_header, **(headers or {})})
    response = con.getresponse()
    response.read()
    return response.status, response.getheader("Location")


def dns(port, name, qtype="A"):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(5)
        s.sendto(DNSRecord.question(name, qtype).pack(), (PORTAL_IP, port))
        reply = DNSRecord.parse(s.recv(4096))
    return [str(r.rdata) for r in reply.rr]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("docs/evidence/box-v05"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from examples.sample_links import SampleLinks
    from pi import dnswatch
    from pi.devices import Devices

    state = Path(tempfile.mkdtemp(prefix="dataexodus-box-"))
    token = secrets.token_urlsafe(32)
    api_port, portal_port, dns_port = free_port(), free_port(PORTAL_IP), free_port(PORTAL_IP, socket.SOCK_DGRAM)
    sample_port = free_port("127.0.0.49")
    env = {**os.environ, "DATAEXODUS_GUARD_TOKEN": token, "SANDBOX_ALLOW_HOSTS": "127.0.0.48/28",
           "BLOCKLIST_DIR": str(ROOT / "data" / "blocklists"), "DATAEXODUS_STATE": str(state),
           "DATAEXODUS_HOST_LABEL": "acceptance-sandbox", "PORTAL_IP": PORTAL_IP, "PORTAL_PORT": str(portal_port),
           "PORTAL_NET": "127.0.0.0/24", "PORTAL_HOSTNAME": "dataexodus.home.arpa",
           "PORTAL_DEVICES": str(state / "portal" / "devices.json"), "DNSWATCH_DB": str(state / "dnswatch.sqlite"),
           "PORTAL_GUARD_API": f"http://127.0.0.1:{api_port}", "PORTAL_SAMPLES": "1",
           "PORTAL_SAMPLES_PORT": str(sample_port), "PYTHONPATH": str(ROOT)}
    checks: dict[str, bool] = {}
    details: dict = {}
    procs = []

    def check(name, ok, detail=None):
        checks[name] = bool(ok)
        if detail is not None:
            details[name] = detail
        print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail is not None else ""), flush=True)

    with SampleLinks(sample_port) as lab:
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "protection.api:app", "--host", "127.0.0.1",
                                       "--port", str(api_port), "--no-access-log"], cwd=ROOT, env=env))
        procs.append(subprocess.Popen([sys.executable, "-m", "pi.portal"], cwd=ROOT, env=env))
        watch = dnswatch.Watch(state / "dnswatch.sqlite", "auto", ["127.0.0.0/8"],
                               dnswatch.load_blocklist([ROOT / "pi" / "dns_trackers.txt",
                                                        ROOT / "data" / "blocklists" / "easyprivacy.txt"]),
                               portal_net="127.0.0.0/24", portal_ip=PORTAL_IP, portal_name="dataexodus.home.arpa",
                               devices=Devices(state / "portal" / "devices.json", refresh=0))
        loop = asyncio.new_event_loop()
        ready = asyncio.Event()
        threading.Thread(target=lambda: loop.run_until_complete(dnswatch.serve(watch, PORTAL_IP, dns_port, ready)),
                         daemon=True).start()
        try:
            wait_http("127.0.0.1", api_port, "/health")
            wait_http(PORTAL_IP, portal_port, "/portal.css", {"Host": PORTAL_IP})
            origin = f"http://{PORTAL_IP}:{portal_port}"

            status, location = raw("GET", portal_port, "/generate_204", "connectivitycheck.gstatic.com")
            check("captive check redirects before the visitor chooses", status == 302 and location == origin + "/",
                  [status, location])
            check("DNS answers the captive name with the portal", dns(dns_port, "connectivitycheck.gstatic.com") == [PORTAL_IP])
            dns(dns_port, "before-joining.example.com")

            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not args.headed)
                details["chromium"] = browser.version
                phone = browser.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2,
                                            is_mobile=True, has_touch=True, locale="en-AU")
                page = phone.new_page()
                page.goto(origin + "/")
                page.screenshot(path=str(args.out / "01-welcome.png"), full_page=True)
                check("welcome page asks before recording", page.locator("text=Join and continue").count() == 1)
                page.click("text=Join and continue")
                page.wait_for_selector("text=You're online")
                status, _ = raw("GET", portal_port, "/generate_204", "connectivitycheck.gstatic.com")
                check("captive check passes after joining", status == 204, status)

                levels = {}
                for sample in lab.samples():
                    page.goto(origin + "/check")
                    if sample["id"] == "news":
                        page.screenshot(path=str(args.out / "02-check-a-link.png"), full_page=True)
                    page.locator(".sample", has_text=sample["title"]).locator("button").click()
                    page.wait_for_selector("h1:text('Link check')", timeout=120000)
                    banner = page.locator(".banner").first
                    level = (banner.get_attribute("class") or "").replace("banner", "").strip()
                    score = page.locator(".banner .score").first.inner_text() if page.locator(".banner .score").count() else ""
                    reasons = page.locator(".reasons li").all_inner_texts()
                    levels[sample["id"]] = {"expected": sample["expect"], "level": level, "score": score,
                                            "reasons": [" ".join(r.split()) for r in reasons]}
                    page.screenshot(path=str(args.out / f"03-result-{sample['id']}.png"), full_page=True)
                    check(f"sample '{sample['id']}' is rated {sample['expect']}", level == sample["expect"],
                          f"{level} {score}")
                details["samples"] = levels

                bank = next(s for s in lab.samples() if s["id"] == "bank")
                page.goto(origin + "/check")
                page.fill("textarea[name=text]", f"KoalaBank: unusual sign-in detected. Verify within 24h: {bank['url']} Reply STOP to opt out")
                page.click("button:text('Check link')")
                page.wait_for_selector("h1:text('Link check')", timeout=120000)
                check("a pasted scam text is checked", "danger" in (page.locator(".banner").first.get_attribute("class") or ""),
                      page.locator("p.url").first.inner_text())

                # Safe Browse on the fake bank page: tap the password field, type, press Enter.
                probe = browser.new_context(viewport={"width": 360, "height": 640}, is_mobile=True, has_touch=True,
                                            device_scale_factor=1)
                probe_page = probe.new_page()
                probe_page.goto(lab.origin["bank"] + "/koala-bank/verify?ref=sms")
                field = probe_page.locator("#pw").bounding_box()
                probe.close()
                page.click("button:text('Open in Safe Browse')")
                page.wait_for_selector("input.screen", timeout=90000)
                page.screenshot(path=str(args.out / "04-safe-browse-start.png"), full_page=True)
                screen = page.locator("input.screen")
                check("Safe Browse shows the sandbox page at 1:1 size",
                      screen.bounding_box()["width"] == 360 and screen.bounding_box()["height"] == 640)
                screen.click(position={"x": field["x"] + field["width"] / 2, "y": field["y"] + field["height"] / 2})
                page.wait_for_selector("input.screen")
                page.fill("input[name=text]", "not-a-real-password")
                page.click("button:text('Type')")
                page.wait_for_selector("input.screen")
                page.click("button:text('Enter ↵')")
                page.wait_for_selector("input.screen")
                page.screenshot(path=str(args.out / "05-safe-browse-submitted.png"), full_page=True)
                url_now = page.locator("p.url").first.inner_text()
                check("Safe Browse tap + type + Enter submitted the form on the sandbox",
                      lab.form_posts == 1 and url_now.startswith(lab.origin["collector"]), [lab.form_posts, url_now])
                page.click("button:text('End')")
                page.wait_for_selector("h1:text('Check a link')")

                # My device: lookups appear only after joining; per-device blocking.
                for name in ("www.google-analytics.com", "connect.facebook.net", "www.abc.net.au", "example.com"):
                    dns(dns_port, name)
                page.goto(origin + "/me?live=0")
                text = page.inner_text("main")
                check("My device lists this device's lookups", "www.google-analytics.com" in text and "www.abc.net.au" in text)
                check("lookups before joining are not recorded", "before-joining.example.com" not in text)
                page.screenshot(path=str(args.out / "06-my-device.png"), full_page=True)
                page.check("input[name=block]")
                page.click("button:text('Save')")
                answer = dns(dns_port, "www.google-analytics.com")
                check("tracker blocking applies to this device", answer == ["0.0.0.0"], answer)
                page.goto(origin + "/me?live=0")
                check("blocked lookups are shown", page.locator(".badge.blocked").count() >= 1)
                page.screenshot(path=str(args.out / "07-my-device-blocking.png"), full_page=True)

                status, _ = raw("POST", portal_port, "/join", PORTAL_IP, body="watch=1",
                                headers={"Origin": "http://evil.example", "Content-Type": "application/x-www-form-urlencoded"})
                check("cross-site form posts are refused", status == 403, status)
                status, _ = raw("GET", portal_port, "/", "attacker.example")
                check("foreign Host headers are refused (DNS rebinding)", status == 403, status)

                page.goto(origin + "/me?live=0")
                page.click("button:text('Forget this device')")
                page.wait_for_selector("text=Join and continue")
                left = sqlite3.connect(state / "dnswatch.sqlite").execute(
                    "SELECT COUNT(*) FROM queries WHERE device IS NOT NULL").fetchone()[0]
                check("Forget this device deletes its lookups", left == 0, left)
                status, _ = raw("GET", portal_port, "/generate_204", "connectivitycheck.gstatic.com")
                check("after forgetting, the captive check shows the welcome page again", status == 302, status)
                browser.close()
        finally:
            for proc in procs:
                proc.terminate()
            for proc in procs:
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            loop.call_soon_threadsafe(loop.stop)

    from importlib.metadata import version
    summary = {"provenance": "real_chromium_loopback_box_flow", "generated": datetime.now(timezone.utc).isoformat(),
               "python": sys.version.split()[0], "playwright": version("playwright"), "chromium": details.pop("chromium", None),
               "passed": all(checks.values()), "checks": checks, "details": details,
               "not_covered": ["Wi-Fi radio and NetworkManager hotspot", "nftables firewall", "Raspberry Pi hardware"]}
    (args.out.parent / (args.out.name + "-acceptance.json")).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{sum(checks.values())}/{len(checks)} checks passed -> {args.out.parent / (args.out.name + '-acceptance.json')}")
    sys.exit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
