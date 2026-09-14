#!/usr/bin/env python3
"""
DataExodus — Real-time Agent (FastAPI + WebSocket)
Receives batched data from Chrome extension, enriches, stores, broadcasts.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.risk import score_request

# --- Global state ---
queue: asyncio.Queue = asyncio.Queue()
clients: set[WebSocket] = set()
classifier: Classifier | None = None
pii: PIIDetector | None = None
DB_PATH = Path("data/live.duckdb")

ROOT_DIR = Path(__file__).parent.parent


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _risk_level(score: int) -> str:
    if score >= 50:
        return "red"
    if score >= 20:
        return "yellow"
    return "green"


_influx_env = _load_env_file(ROOT_DIR / "monitoring" / "influxdb" / "credentials.env")
_influx_write_api = None
if _influx_env.get("INFLUX_TOKEN"):
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    _influx_client = InfluxDBClient(
        url=_influx_env.get("INFLUX_URL", "http://127.0.0.1:8086"),
        token=_influx_env["INFLUX_TOKEN"],
        org=_influx_env.get("INFLUX_ORG", "dataexodus"),
    )
    _influx_write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    _influx_bucket = _influx_env.get("INFLUX_BUCKET", "live_requests")
else:
    print(
        "[agent] warning: no InfluxDB credentials at "
        "monitoring/influxdb/credentials.env - Grafana dashboard will stay "
        "empty. Run monitoring/setup_monitoring.sh."
    )


def write_influx_point(event: dict) -> None:
    if _influx_write_api is None:
        return
    from influxdb_client import Point

    initiator_host = ""
    if event.get("initiator"):
        from urllib.parse import urlparse
        initiator_host = urlparse(event["initiator"]).hostname or ""

    country_adequacy = event.get("country_adequacy")
    offshore = bool(event.get("country")) and country_adequacy is False
    risk_score = event.get("risk_score") or 0

    point = (
        Point("requests")
        .tag("page_domain", initiator_host or "unknown")
        .tag("domain", event.get("domain") or "unknown")
        .tag("owner", event.get("owner") or "none")
        .tag("country", event.get("country") or "unknown")
        .tag("category", event.get("category") or "none")
        .tag("resource_type", event.get("resource_type") or "other")
        .tag("risk_level", _risk_level(risk_score))
        .field("risk_score", risk_score)
        .field("is_tracker", int(bool(event.get("is_tracker"))))
        .field("pii_findings", int(bool(event.get("pii_detected"))))
        .field("offshore", int(offshore))
        .field("fingerprinting", int(bool(event.get("fingerprinting"))))
    )
    try:
        _influx_write_api.write(bucket=_influx_bucket, record=point)
    except Exception as exc:  # InfluxDB down/unreachable shouldn't break ingestion
        print(f"[agent] warning: InfluxDB write failed: {exc}")

ADEQUATE_COUNTRIES = {
    "AU", "NZ", "GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT",
    "SE", "NO", "DK", "FI", "CH", "IE", "PT", "LU", "IS", "LI",
    "CA", "JP", "KR", "SG", "IL", "UY", "AR", "BR", "MX", "CL",
    "CO", "PE", "ZA", "IN", "MY", "PH", "TH", "VN", "ID", "TW",
    "HK", "MO",
}


def init_live_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS live_requests (
            id INTEGER PRIMARY KEY,
            ts DOUBLE,
            url VARCHAR,
            domain VARCHAR,
            initiator VARCHAR,
            is_tracker BOOLEAN,
            category VARCHAR,
            owner VARCHAR,
            country VARCHAR,
            country_adequacy BOOLEAN,
            pii_detected BOOLEAN,
            pii_details VARCHAR,
            fingerprinting BOOLEAN,
            risk_score INTEGER
        )
    """)
    conn.close()


def load_classifier():
    global classifier
    blocklist_dir = os.getenv("BLOCKLIST_DIR", "data/blocklists")
    geoip_mmdb = os.getenv("GEOIP_MMDB", "data/blocklists/GeoLite2-Country.mmdb")
    classifier = Classifier.load(blocklist_dir, geoip_mmdb if Path(geoip_mmdb).exists() else None)


def load_pii():
    global pii
    ident_path = os.getenv("IDENTITIES_PATH", "data/identities.local.yaml")
    if Path(ident_path).exists():
        pii = PIIDetector.from_yaml(ident_path)
    else:
        print("[agent] PII detection disabled (no identities file)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_live_db()
    load_classifier()
    load_pii()
    task = asyncio.create_task(worker())
    yield
    task.cancel()


app = FastAPI(title="DataExodus Agent", lifespan=lifespan)


@app.post("/ingest")
async def ingest(payload: dict):
    """Extension pushes batched events here."""
    events = payload.get("events", [])
    if events:
        await queue.put(events)
    return {"ok": True, "queued": len(events)}


@app.get("/")
async def dashboard():
    """Human-facing dashboard. /summary is the raw JSON API behind it."""
    return FileResponse(Path(__file__).parent / "dashboard.html")


@app.get("/recent")
async def recent(limit: int = 40):
    """Most recent classified requests, for the dashboard's live feed table."""
    conn = duckdb.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT ts, domain, owner, category, country, is_tracker,
               pii_detected, fingerprinting, risk_score
        FROM live_requests ORDER BY id DESC LIMIT ?
    """, [limit]).fetchall()
    conn.close()
    return [
        {
            "ts": r[0], "domain": r[1], "owner": r[2], "category": r[3],
            "country": r[4], "is_tracker": r[5], "pii_detected": r[6],
            "fingerprinting": r[7], "risk_score": r[8],
            "risk_level": _risk_level(r[8] or 0),
        }
        for r in rows
    ]


@app.get("/site/{domain}")
async def site_info(domain: str):
    """
    Rolling per-site stats, keyed on the initiating page's host. This is what
    drives the extension's traffic-light badge, so it stays cheap: one
    aggregate query, no joins.
    """
    conn = duckdb.connect(str(DB_PATH))
    row = conn.execute("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE is_tracker),
               COUNT(*) FILTER (WHERE country_adequacy = FALSE),
               COUNT(*) FILTER (WHERE pii_detected),
               COALESCE(MAX(risk_score), 0)
        FROM live_requests
        WHERE initiator LIKE '%' || ? || '%'
    """, [domain]).fetchone()
    owners = conn.execute("""
        SELECT owner, COUNT(*) c FROM live_requests
        WHERE initiator LIKE '%' || ? || '%' AND owner IS NOT NULL
        GROUP BY owner ORDER BY c DESC LIMIT 5
    """, [domain]).fetchall()
    conn.close()

    total, trackers, offshore, pii_count, max_risk = row
    insights = []
    if trackers:
        names = ", ".join(o for o, _ in owners) or "unidentified third parties"
        insights.append(f"Sent data to {len(owners) or trackers} third party(ies): {names}.")
    if offshore:
        insights.append(f"{offshore} request(s) went to a country outside the adequacy list.")
    if pii_count:
        insights.append(f"{pii_count} request(s) carried personal data (raw or hashed).")
    if not insights:
        insights.append("No tracking or personal-data leakage detected yet.")

    return {
        "domain": domain,
        "requests": total,
        "tracker_requests": trackers,
        "offshore_requests": offshore,
        "pii_requests": pii_count,
        "risk_score": max_risk,
        "risk_level": _risk_level(max_risk or 0),
        "top_owners": [o for o, _ in owners],
        "insights": insights,
    }


@app.get("/summary")
async def summary():
    """Quick stats from live DB."""
    conn = duckdb.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) FROM live_requests").fetchone()[0]
    trackers = conn.execute("SELECT COUNT(*) FROM live_requests WHERE is_tracker=TRUE").fetchone()[0]
    offshore = conn.execute("SELECT COUNT(*) FROM live_requests WHERE country_adequacy=FALSE").fetchone()[0]
    pii_count = conn.execute("SELECT COUNT(*) FROM live_requests WHERE pii_detected=TRUE").fetchone()[0]
    top_owners = conn.execute("""
        SELECT owner, COUNT(*) as c FROM live_requests
        WHERE owner IS NOT NULL GROUP BY owner ORDER BY c DESC LIMIT 5
    """).fetchall()
    conn.close()
    return {
        "total_requests": total,
        "tracker_requests": trackers,
        "offshore_requests": offshore,
        "pii_requests": pii_count,
        "top_owners": [{"owner": o, "count": c} for o, c in top_owners],
    }


@app.websocket("/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


async def worker():
    """Background worker: dequeue → enrich → store → broadcast."""
    conn = duckdb.connect(str(DB_PATH))
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM live_requests").fetchone()
    next_id = (row[0] or 0) + 1

    while True:
        events = await queue.get()
        enriched = []
        alerts = []

        for ev in events:
            url = ev.get("url", "")
            initiator = ev.get("initiator")
            resource_type = ev.get("type", "")
            body = ev.get("body")
            cookies = ev.get("cookies")
            headers = ev.get("headers", {})
            ts = ev.get("ts", 0.0)
            fp = ev.get("fingerprinting", False)

            cls = classifier.classify(url, initiator, resource_type) if classifier else {}
            pii_hits = pii.scan_request(url, body, cookies, headers) if pii else []
            risk = score_request({**cls, "url": url, "fingerprinting": fp}, pii_hits)

            # Alerts
            if pii_hits and not cls.get("country_adequacy", True):
                alerts.append(f"PII sent to {cls.get('country', 'unknown')}: {cls.get('domain', url)}")
            if cls.get("domain_age_days") is not None and cls.get("domain_age_days", 999) < 30:
                alerts.append(f"Newly registered domain: {cls.get('domain', url)}")

            event = {
                "id": next_id,
                "ts": ts,
                "url": url,
                "domain": cls.get("domain"),
                "initiator": initiator,
                "resource_type": resource_type,
                "is_tracker": cls.get("is_tracker"),
                "category": cls.get("category"),
                "owner": cls.get("owner"),
                "country": cls.get("country"),
                "country_adequacy": cls.get("country_adequacy"),
                "pii_detected": bool(pii_hits),
                "pii_details": json.dumps(pii_hits) if pii_hits else None,
                "fingerprinting": fp,
                "risk_score": risk,
            }
            enriched.append(event)
            write_influx_point(event)
            next_id += 1

        # Bulk insert
        if enriched:
            rows = [(
                e["id"], e["ts"], e["url"], e["domain"], e["initiator"],
                e["is_tracker"], e["category"], e["owner"], e["country"],
                e["country_adequacy"], e["pii_detected"], e["pii_details"],
                e["fingerprinting"], e["risk_score"]
            ) for e in enriched]
            conn.executemany("""
                INSERT INTO live_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

        # Broadcast
        dead = set()
        msg = json.dumps({"events": enriched, "alerts": alerts})
        for ws in clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        clients.difference_update(dead)

        queue.task_done()
