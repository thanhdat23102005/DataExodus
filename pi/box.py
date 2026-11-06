"""DataExodus Box dashboard: what the Raspberry Pi is doing, on one page.

Runs on the Pi at 127.0.0.1:8020 only. Open it from the laptop through the SSH
tunnel (pi/connect-pi.ps1) at http://127.0.0.1:8020. Read-only: it shows the
Guard service, the DataExodus Wi-Fi and its printable "try it" card (QR codes
to join and to open the portal), the DNS watch summary, scheduled study runs
and their reports, reference data and the Pi's temperature.

  python -m uvicorn pi.box:app --host 127.0.0.1 --port 8020
"""
from __future__ import annotations

import html
import json
import os
import socket
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from pi import dns_report
from pi.devices import Devices

app = FastAPI(title="DataExodus Box", docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(__file__).resolve().parents[1]
REPORT_TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json", ".md": "text/plain; charset=utf-8",
                ".csv": "text/csv; charset=utf-8", ".log": "text/plain; charset=utf-8", ".xlsx":
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
e = lambda value: html.escape(str(value))  # noqa: E731


def state() -> Path:
    return Path(os.getenv("DATAEXODUS_STATE", ROOT / "data"))


def blocklists() -> Path:
    return Path(os.getenv("BLOCKLIST_DIR", ROOT / "data" / "blocklists"))


def dns_db() -> Path:
    return Path(os.getenv("DNSWATCH_DB", state() / "dnswatch.sqlite"))


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Reached through the SSH tunnel as localhost. Any other Host header is a
    # DNS-rebinding attempt by a web page, refused before any route runs.
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy",
                                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def guard_status() -> dict:
    token = os.getenv("DATAEXODUS_GUARD_TOKEN", "")
    try:
        r = requests.get("http://127.0.0.1:8010/health", headers={"Authorization": "Bearer " + token}, timeout=2)
        return {"running": True, **(r.json() if r.ok else {"ok": False, "http_status": r.status_code})}
    except (requests.RequestException, ValueError):
        return {"running": False}


def pi_status() -> dict:
    out = {"host": os.getenv("DATAEXODUS_HOST_LABEL") or socket.gethostname()}
    try:
        out["cpu_temp_c"] = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        out["cpu_temp_c"] = None
    out["load"] = os.getloadavg() if hasattr(os, "getloadavg") else None
    return out


def runs(limit: int = 8) -> list[dict]:
    root = state() / "runs"
    found = []
    for run in sorted(root.iterdir(), reverse=True) if root.exists() else []:
        status_file = run / "status.json"
        if not status_file.is_file():
            continue
        status = json.loads(status_file.read_text(encoding="utf-8"))
        status["name"] = run.name
        status["links"] = [p.relative_to(run).as_posix() for p in
                           (run / "audit" / "audit.html", run / "report" / "report.md") if p.is_file()]
        found.append(status)
        if len(found) >= limit:
            break
    return found


def hotspot() -> dict:
    """The DataExodus Wi-Fi (pi/hotspot.sh), if it is set up."""
    ssid = os.getenv("HOTSPOT_SSID", "")
    if not ssid:
        return {"enabled": False}
    leases = Path(os.getenv("HOTSPOT_LEASES", "/var/lib/NetworkManager/dnsmasq-wlan0.leases"))
    try:
        connected = sum(1 for line in leases.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        connected = None
    joined = Devices(os.getenv("PORTAL_DEVICES", str(state() / "portal" / "devices.json"))).all()
    return {"enabled": True, "ssid": ssid, "psk": os.getenv("HOTSPOT_PSK", ""), "connected": connected,
            "joined": len(joined), "watching": sum(1 for d in joined.values() if d.get("watch")),
            "portal": "http://" + os.getenv("PORTAL_IP", "10.42.0.1"),
            "portal_name": "http://" + os.getenv("PORTAL_HOSTNAME", "dataexodus.home.arpa")}


def reference_data() -> list[tuple[str, str]]:
    rows = []
    for name in ("easyprivacy.txt", "tracker_radar.json", "urlhaus_hosts.txt", "GeoLite2-Country.mmdb"):
        path = blocklists() / name
        rows.append((name, datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d") if path.exists() else "missing"))
    return rows


@app.get("/api/status")
def api_status():
    wifi = {k: v for k, v in hotspot().items() if k != "psk"}
    return {"pi": pi_status(), "guard": guard_status(), "dns": dns_report.summarise(dns_db(), 24, blocklists()),
            "hotspot": wifi, "runs": runs(), "reference_data": dict(reference_data())}


STYLE = """body{font:15px/1.5 system-ui;margin:0;background:#edf4f3;color:#163840}main{max-width:1000px;margin:28px auto;padding:24px;background:#fff;border-radius:18px}
.eyebrow{font-size:11px;letter-spacing:2px;color:#207c69;font-weight:800}h1{margin:6px 0 16px}h2{margin:26px 0 8px;font-size:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}.card{background:#edf5f1;border-radius:12px;padding:14px}
.card b{display:block;font-size:24px}.ok{color:#0e7461}.bad{color:#b42318}table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #e2ebe7;overflow-wrap:anywhere}.note{color:#557079;font-size:13px}a{color:#0e7461}
nav a{margin-right:14px}@media(max-width:600px){main{margin:0;border-radius:0;padding:16px}}"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>"
                        f"<title>{e(title)}</title><style>{STYLE}</style><main><div class=eyebrow>DATAEXODUS / RASPBERRY PI BOX</div>"
                        f"<nav><a href='/'>Overview</a><a href='/dns'>DNS watch</a><a href='/dns?hours=168'>DNS (7 days)</a>"
                        f"<a href='/card'>Wi-Fi card</a></nav>"
                        f"<h1>{e(title)}</h1>{body}</main></html>")


@app.get("/", response_class=HTMLResponse)
def overview():
    pi, guard, dns = pi_status(), guard_status(), dns_report.summarise(dns_db(), 24, blocklists())
    wifi = hotspot()
    state_cls = lambda ok: "ok" if ok else "bad"  # noqa: E731
    guard_text = ("running" if guard.get("ok") else "running, token mismatch" if guard["running"] else "not running")
    last = datetime.fromtimestamp(dns["last"]).strftime("%H:%M") if dns.get("last") else "no lookups yet"
    wifi_card = (f"<div class=card><b>{e(wifi['ssid'])}</b>Wi-Fi: {e(wifi['connected'] if wifi['connected'] is not None else '?')} "
                 f"connected, {e(wifi['joined'])} joined the portal · <a href='/card'>printable card</a></div>"
                 if wifi["enabled"] else
                 "<div class=card><b>off</b>DataExodus Wi-Fi (sudo bash pi/hotspot.sh)</div>")
    cards = (f"<div class=cards><div class=card><b class={state_cls(guard.get('ok'))}>{e(guard_text)}</b>"
             "Guard service and sandbox</div>" + wifi_card +
             f"<div class=card><b>{dns.get('queries', 0):,}</b>DNS lookups in 24 h (last: {e(last)})</div>"
             f"<div class=card><b>{dns_report.pct(dns.get('tracker_queries', 0), dns.get('queries', 0))}</b>lookups to listed tracker / malware names</div>"
             f"<div class=card><b>{e(pi['cpu_temp_c']) if pi['cpu_temp_c'] is not None else 'n/a'} °C</b>{e(pi['host'] or 'this machine')} CPU temperature</div></div>")
    rows = "".join(
        f"<tr><td>{e(r['name'])}</td><td class={state_cls(r['ok'])}>{'ok' if r['ok'] else 'failed'}</td>"
        f"<td>{e(r.get('sessions', 0))} sites</td><td>{e(', '.join(r.get('resolvers') or []) or 'not recorded')}</td>"
        f"<td>{e(r.get('baseline') or 'first run')}</td><td>"
        + " ".join(f"<a href='/runs/{e(r['name'])}/{e(link)}'>{e(link.split('/')[0])}</a>" for link in r["links"])
        + "</td></tr>" for r in runs()) or "<tr><td colspan=6>No scheduled study run yet (systemctl start dataexodus-study).</td></tr>"
    ref = "".join(f"<tr><td>{e(name)}</td><td>{e(date)}</td></tr>" for name, date in reference_data())
    body = (cards + "<h2>Scheduled study runs</h2><table><tr><th>Run (UTC)</th><th>Status</th><th>Captures</th><th>DNS used</th>"
            "<th>Compared with</th><th>Reports</th></tr>"
            + rows + "</table><h2>Reference data</h2><table>" + ref + "</table>"
            "<p class=note>Every service listens on the Pi's loopback only; this page and Guard reach them through your SSH tunnel. "
            "The DNS watch is the one service on the network, and it answers only the client networks you allowed.</p>")
    return page("Overview", body)


@app.get("/dns", response_class=HTMLResponse)
def dns(hours: float = 24):
    hours = min(max(hours, 1), 720)
    return page(f"DNS watch, last {hours:g} h", dns_report.render(dns_report.summarise(dns_db(), hours, blocklists())))


CARD_STYLE = """body{font:16px/1.45 system-ui;margin:0;background:#fff;color:#14323a}.sheet{max-width:720px;margin:20px auto;padding:24px;
border:2px dashed #9fbdb5;border-radius:18px}h1{margin:0 0 4px;font-size:28px}.eyebrow{font-size:12px;letter-spacing:2px;color:#0e7461;font-weight:800}
.steps{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:14px}.step{text-align:center}.step img{width:220px;height:220px}
.big{font:700 18px ui-monospace,Consolas,monospace}ol{margin:16px 0 0 0;padding-left:22px}.note{font-size:12px;color:#587078}
.noprint{text-align:center;margin:12px}@media(max-width:600px){.steps{grid-template-columns:1fr}}@media print{.noprint{display:none}.sheet{margin:0}}"""


@app.get("/card", response_class=HTMLResponse)
def card():
    """A printable card for the assessor: scan to join the Wi-Fi, then the portal opens."""
    wifi = hotspot()
    if not wifi["enabled"]:
        return page("Wi-Fi card", "<p>The DataExodus Wi-Fi is not set up. On the Pi: <code>sudo bash pi/hotspot.sh</code></p>")
    import segno
    from segno import helpers

    join = helpers.make_wifi(ssid=wifi["ssid"], password=wifi["psk"], security="WPA").svg_data_uri(scale=8, border=2)
    portal = segno.make(wifi["portal"] + "/", error="m").svg_data_uri(scale=8, border=2)
    return HTMLResponse(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>Try DataExodus</title><style>{CARD_STYLE}</style><div class=sheet><div class=eyebrow>DATAEXODUS BOX · "
        "RASPBERRY PI 5</div><h1>Try it with your own phone</h1><p>A privacy Wi-Fi that checks suspicious links in an "
        "isolated browser on the Pi and shows which companies your apps contact.</p><div class=steps>"
        f"<div class=step><img alt='QR code: join the Wi-Fi' src='{join}'><div><b>1. Scan to join the Wi-Fi</b></div>"
        f"<div>Name <span class=big>{e(wifi['ssid'])}</span></div><div>Password <span class=big>{e(wifi['psk'])}</span></div></div>"
        f"<div class=step><img alt='QR code: open the portal' src='{portal}'><div><b>2. The welcome page opens</b></div>"
        f"<div>If it does not, scan this or open <span class=big>{e(wifi['portal'])}</span></div></div></div>"
        "<ol><li><b>Check a link</b>: try the samples, or paste a link from a real scam text or email.</li>"
        "<li><b>Open in Safe Browse</b>: use the suspicious page on the Pi by tapping its picture.</li>"
        "<li><b>My device</b> (optional): open a few apps and see which companies they contact, and where. "
        "Switch on tracker blocking and watch the count change.</li><li>When you finish: <b>Forget this device</b>, "
        "then forget the Wi-Fi network.</li></ol>"
        "<p class=note>Nothing is recorded unless you choose it on the welcome page. Recorded lookups are deleted "
        f"after {e(os.getenv('PORTAL_RETENTION_HOURS', '24'))} hours or when you press Forget this device.</p></div>"
        "<p class=noprint><a href='/'>Back to the dashboard</a> · use your browser's Print command for a paper copy</p></html>")


@app.get("/runs/{name}/{path:path}")
def run_file(name: str, path: str):
    root = (state() / "runs").resolve()
    target = (root / name / path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix not in REPORT_TYPES or "raw" in target.parts:
        raise HTTPException(404)
    # Reports are self-contained; their scripts run sandboxed with no network.
    headers = {"Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
                                          "style-src 'unsafe-inline'; img-src data:"}
    return FileResponse(target, media_type=REPORT_TYPES[target.suffix], headers=headers)


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("BOX_PORT", "8020")), access_log=False)


if __name__ == "__main__":
    main()
