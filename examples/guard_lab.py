"""Interactive, loopback-only Guard lab. Synthetic identifiers, no real malware.

Six local servers, one role each, so receipts show who received what:
  127.0.0.1  the website (also counts the legitimate document it serves)
  127.0.0.2  a listed collector (lab rules)          127.0.0.4  an unlisted collector
  127.0.0.3  ad server: popups and an ad-click redirector (lab rules)
  127.0.0.5  an unlisted POST collector              127.0.0.6  the advertiser's landing page
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

EMAIL = "student.demo@example.com"
DIGEST = hashlib.sha256(EMAIL.encode()).hexdigest()
ROLES = (("127.0.0.1", "site"), ("127.0.0.2", "collector"), ("127.0.0.3", "ads"),
         ("127.0.0.4", "collector"), ("127.0.0.5", "collector"), ("127.0.0.6", "advertiser"))
CLICK_IDS = ("gclid", "fbclid", "msclkid")


class GuardLab:
    def __init__(self, port=8875):
        self.port = port
        self.servers = []
        self.receipts = []
        self.docs_served = 0  # negative control: the legitimate page must still load
        self.lock = threading.Lock()

    def add(self, receipt):
        with self.lock:
            self.receipts.append(receipt)

    def __enter__(self):
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, payload, mime="application/json", status=200):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                if self.headers.get("Origin") == lab.site:
                    self.send_header("Access-Control-Allow-Origin", lab.site)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def receiver(self):
                return {"127.0.0.4": "unlisted_url", "127.0.0.5": "post_collector"}.get(
                    self.server.server_address[0], self.server.role)

            def do_GET(self):
                route = urlsplit(self.path)
                query = parse_qs(route.query)
                role = self.server.role
                if role == "site":
                    if route.path == "/receipts":
                        with lab.lock:
                            self.reply({"receipts": list(lab.receipts), "count": len(lab.receipts)})
                    elif route.path == "/docs":
                        with lab.lock:
                            lab.docs_served += 1
                        self.reply(b"<title>Legitimate document</title><h1>Legitimate documentation opened.</h1>", "text/html")
                    elif route.path == "/":
                        page = (Path(__file__).with_name("guard_lab.html")).read_text(encoding="utf-8")
                        for key, value in (("__COLLECTOR__", lab.collector), ("__POPUP__", lab.ads),
                                           ("__UNLISTED__", lab.unlisted), ("__POST_COLLECTOR__", lab.post_collector),
                                           ("__SPONSORED__", lab.sponsored)):
                            page = page.replace(key, json.dumps(value))
                        self.reply(page.encode(), "text/html; charset=utf-8")
                    else:
                        self.reply({"error": "not found"}, status=404)
                elif role == "collector":
                    value = query.get("uid", [""])[0]
                    if route.path != "/collect" or value not in (EMAIL, DIGEST):
                        self.reply({"error": "Only the synthetic lab identity is accepted"}, status=400)
                        return
                    lab.add({"kind": "identifier", "representation": "raw" if value == EMAIL else "sha256",
                             "transport": "url", "receiver": self.receiver()})
                    self.reply({"received": True})
                elif role == "advertiser":
                    if route.path != "/landing":
                        self.reply(b"", status=204)
                        return
                    # Did the advertiser learn which click (and so which user) this was?
                    lab.add({"kind": "advertiser_visit", "click_id": any(k in query for k in CLICK_IDS),
                             "from_user_page": bool(self.headers.get("Referer"))})
                    self.reply(b"<title>Advertiser landing page</title><h1>Lab Shoes</h1><p>Advertiser landing page. Local lab only.</p>",
                               "text/html")
                elif route.path == "/aclk":
                    # Ad-click redirector: logs the click, then bounces to the advertiser
                    # with a click ID. A click from the user's page carries its Referer;
                    # the sandbox opens the link directly and carries none.
                    lab.add({"kind": "ad_click", "from_user_page": bool(self.headers.get("Referer"))})
                    self.send_response(302)
                    self.send_header("Location", lab.advertiser + "/landing?gclid=lab-click-id&utm_source=lab")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif route.path in ("/ad", "/overlay"):
                    lab.add({"kind": "popup_navigation"})
                    self.reply(b"<title>Simulated ad destination</title><h1>Simulated advertisement</h1><p>Local lab only. No malware.</p>", "text/html")
                else:
                    self.reply(b"", status=204)

            def do_POST(self):
                route = urlsplit(self.path)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.reply({"error": "invalid size"}, status=400)
                    return
                if not 0 < size <= 4096:
                    self.reply({"error": "invalid size"}, status=400)
                    return
                value = parse_qs(self.rfile.read(size).decode("utf-8", errors="replace")).get("uid", [""])[0]
                site_submit = self.server.role == "site" and route.path == "/same-site-submit"
                if not ((self.server.role == "collector" and route.path == "/collect") or site_submit) or value != EMAIL:
                    self.reply({"error": "Only the synthetic lab identity is accepted"}, status=400)
                    return
                lab.add({"kind": "first_party_submit" if site_submit else "identifier",
                         "representation": "raw", "transport": "body", "receiver": self.receiver()})
                self.reply({"received": True})

        try:
            for i, (host, role) in enumerate(ROLES):
                server = ThreadingHTTPServer((host, self.port + i if self.port else 0), Handler)
                server.role = role
                self.servers.append(server)
            self.site, self.collector, self.ads, self.unlisted, self.post_collector, self.advertiser = (
                f"http://{host}:{server.server_port}" for (host, _), server in zip(ROLES, self.servers))
            self.sponsored = (f"{self.ads}/aclk?ad=lab-shoes&adurl="
                              + quote(self.advertiser + "/landing?utm_source=lab", safe=""))
            for server in self.servers:
                threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
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
    parser.add_argument("--port", type=int, default=8875)
    args = parser.parse_args()
    with GuardLab(args.port) as lab:
        print(f"Open {lab.site}\nCollector receipts: {lab.site}/receipts\n"
              "For sandbox previews of the lab ad, start the service with "
              "SANDBOX_ALLOW_HOSTS=127.0.0.3,127.0.0.6 (lab only).\nStop with Ctrl+C", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
