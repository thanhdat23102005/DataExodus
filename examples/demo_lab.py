"""Two local test sites and a local collector. All traffic stays on loopback."""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

EMAIL = "student.demo@example.com"
DIGEST = hashlib.sha256(EMAIL.encode()).hexdigest()


class Lab:
    def __init__(self, phase="before", base_port=8765):
        self.phase = phase
        self.base_port = base_port
        self.servers = []
        self.received = []
        self.origins = []

    def __enter__(self):
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.server.is_collector:
                    query = parse_qs(urlparse(self.path).query)
                    if urlparse(self.path).path != "/collect" or query.get("uid") != [DIGEST]:
                        self.send_error(400, "This lab accepts only the synthetic demo hash")
                        return
                    origin = self.headers.get("Origin", "")
                    lab.received.append({"sha256": DIGEST, "origin": origin, "phase": lab.phase})
                    self.send_response(200)
                    if origin in lab.origins:
                        self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"received":true}')
                    return
                if urlparse(self.path).path != "/":
                    self.send_error(404)
                    return
                enabled = lab.phase == "before"
                script = """
                    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode('student.demo@example.com'));
                    const hash=Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
                    await fetch(COLLECTOR+'/collect?uid='+hash);
                    document.getElementById('result').textContent='Collector received the synthetic hashed email.';
                """ if enabled else "document.getElementById('result').textContent='Identifier-sending tag removed. No collector request was made.';"
                body = """<!doctype html><html lang="en"><meta charset="utf-8"><title>DataExodus controlled lab</title>
                <style>body{font:18px/1.6 system-ui;max-width:760px;margin:70px auto;padding:25px;color:#183646;background:#f3f6f8}main{background:white;padding:35px;border-radius:15px}.tag{color:#13715e;font-weight:bold}code{font-size:15px}</style>
                <main><div class="tag">CONTROLLED LOCAL LAB · SYNTHETIC DATA</div><h1>LAB_NAME</h1>
                <p>This page demonstrates a third-party integration using a test email. Nothing goes to the public internet.</p>
                <p>Phase: <b>PHASE</b></p><p>Test identity: <code>student.demo@example.com</code></p>
                <p id="result">Running test integration…</p><p>Open the browser Network panel or run the DataExodus crawler to inspect the request.</p></main>
                <script>(async()=>{const COLLECTOR=COLLECTOR_URL;SCRIPT})().catch(e=>document.getElementById('result').textContent='Test failed: '+e.message);</script></html>"""
                body = body.replace("LAB_NAME", self.server.lab_name).replace("PHASE", lab.phase)
                body = body.replace("COLLECTOR_URL", json.dumps(lab.collector_url)).replace("SCRIPT", script)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body.encode())

        try:
            for index, host in enumerate(("127.0.0.1", "127.0.0.1", "127.0.0.2")):
                port = self.base_port + index if self.base_port else 0
                server = ThreadingHTTPServer((host, port), Handler)
                server.is_collector = index == 2
                server.lab_name = ("Example Shop", "Example Clinic", "Collector")[index]
                threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
                self.servers.append(server)
            self.origins = [f"http://127.0.0.1:{self.servers[0].server_port}",
                            f"http://localhost:{self.servers[1].server_port}"]
            self.collector_url = f"http://127.0.0.2:{self.servers[2].server_port}"
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        for server in self.servers:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after"], default="before")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with Lab(args.phase, args.port) as lab:
        print(f"Phase: {args.phase}; open either local site:", *lab.origins, sep="\n", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
