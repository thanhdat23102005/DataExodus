#!/usr/bin/env python3
"""
DataExodus — Real-time Agent (FastAPI + WebSocket)
Receives batched data from Chrome extension, enriches, stores, broadcasts.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import duckdb
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from fastapi.responses import FileResponse, JSONResponse

from pipeline.classify import Classifier, hostname
from pipeline.pii import PIIDetector
from pipeline.risk import score_request, level

# --- Global state ---
queue: asyncio.Queue = asyncio.Queue()
clients: set[WebSocket] = set()
classifier: Classifier | None = None
pii: PIIDetector | None = None
DB_PATH = Path("data/live.duckdb")

ROOT_DIR = Path(__file__).parent.parent


class RequestEvent(BaseModel):
    url: str = Field(min_length=1, max_length=32768)
    initiator: str | None = None
    type: str = "other"
    ts: float = 0.0
    body: str | None = Field(default=None, max_length=131072)
    cookies: str | None = Field(default=None, max_length=65536)
    headers: dict[str, str] = Field(default_factory=dict)
    fingerprinting: bool = False

    @field_validator("url")
    @classmethod
    def http_only(cls, value):
        if not value.lower().startswith(("http://", "https://")) or not hostname(value):
            raise ValueError("Only HTTP(S) requests with a host are accepted")
        return value


class IngestBatch(BaseModel):
    events: list[RequestEvent] = Field(default_factory=list, max_length=1000)


def init_live_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_requests (
                id INTEGER PRIMARY KEY, ts DOUBLE, url VARCHAR, domain VARCHAR,
                initiator VARCHAR, is_tracker BOOLEAN, category VARCHAR, owner VARCHAR,
                country VARCHAR, country_adequacy BOOLEAN, pii_detected BOOLEAN,
                pii_details VARCHAR, fingerprinting BOOLEAN, risk_score INTEGER
            )
        """)
        for name, sql_type in {"page_domain": "VARCHAR", "third_party": "BOOLEAN",
                               "offshore": "BOOLEAN", "tracker_source": "VARCHAR"}.items():
            conn.execute(f"ALTER TABLE live_requests ADD COLUMN IF NOT EXISTS {name} {sql_type}")


def load_classifier():
    global classifier
    classifier = Classifier.load(os.getenv("BLOCKLIST_DIR", "data/blocklists"),
                                 os.getenv("GEOIP_MMDB", "data/blocklists/GeoLite2-Country.mmdb"))


def load_pii():
    global pii
    path = Path(os.getenv("IDENTITIES_PATH", "data/identities.local.yaml"))
    pii = PIIDetector.from_yaml(path) if path.exists() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue
    queue = asyncio.Queue(maxsize=100)
    init_live_db()
    load_classifier()
    load_pii()
    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        if classifier:
            classifier.close()


app = FastAPI(title="DataExodus Agent", lifespan=lifespan)

# The agent holds browsing history and identifier matches. Only three callers
# are accepted: the dashboard it serves itself, the DataExodus extension
# (chrome-extension:// origin) and non-browser clients (no Origin header).
# Without this, any website could open ws://localhost:8000/live, and a
# DNS-rebinding page (evil.example resolving to 127.0.0.1) could read /recent.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
_EXTRA_HOSTS = {h.strip().lower() for h in os.getenv("AGENT_ALLOWED_HOSTS", "").split(",") if h.strip()}


def _host_allowed(host_header: str | None) -> bool:
    host = (host_header or "").lower()
    name = host.split("]")[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
    return name in _LOCAL_HOSTS or name in _EXTRA_HOSTS


def _origin_allowed(origin: str | None, host_header: str | None) -> bool:
    if not origin:
        return True
    if origin.startswith(("chrome-extension://", "moz-extension://")):
        return True
    return urlparse(origin).netloc.lower() == (host_header or "").lower()


@app.middleware("http")
async def local_only(request: Request, call_next):
    if not _host_allowed(request.headers.get("host")):
        return JSONResponse({"detail": "Host not allowed"}, status_code=403)
    if not _origin_allowed(request.headers.get("origin"), request.headers.get("host")):
        return JSONResponse({"detail": "Cross-site requests to the local agent are refused"}, status_code=403)
    # <img>/<script> loads carry no Origin header but are marked by Sec-Fetch-Site.
    if request.headers.get("sec-fetch-site") == "cross-site" and request.headers.get("sec-fetch-mode") != "navigate":
        return JSONResponse({"detail": "Cross-site subresource requests are refused"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.post("/ingest")
async def ingest(payload: IngestBatch):
    if payload.events:
        try:
            queue.put_nowait([event.model_dump() for event in payload.events])
        except asyncio.QueueFull:
            raise HTTPException(503, "Ingestion queue full; retry this batch")
    return {"ok": True, "queued": len(payload.events)}


@app.get("/")
async def dashboard():
    return FileResponse(ROOT_DIR / "pipeline" / "dashboard.html")


@app.get("/recent")
async def recent(limit: int = Query(40, ge=1, le=500)):
    with duckdb.connect(str(DB_PATH)) as conn:
        cursor = conn.execute("""
            SELECT ts, domain, owner, category, country, is_tracker, pii_detected,
                   fingerprinting, risk_score, third_party, offshore, tracker_source
            FROM live_requests ORDER BY id DESC LIMIT ?
        """, [limit])
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        row["risk_level"] = level(row["risk_score"] or 0)
    return rows


@app.get("/site/{domain}")
async def site_info(domain: str):
    domain = hostname(domain)
    with duckdb.connect(str(DB_PATH)) as conn:
        total, trackers, offshore, pii_count, risk = conn.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE is_tracker),
                   COUNT(*) FILTER (WHERE offshore), COUNT(*) FILTER (WHERE pii_detected),
                   COALESCE(MAX(risk_score), 0)
            FROM live_requests WHERE page_domain = ?
        """, [domain]).fetchone()
        owners = conn.execute("""
            SELECT owner, COUNT(*) c FROM live_requests
            WHERE page_domain = ? AND third_party AND owner IS NOT NULL
            GROUP BY owner ORDER BY c DESC, owner LIMIT 5
        """, [domain]).fetchall()
    insights = []
    if trackers:
        insights.append(f"{trackers} request(s) matched supported tracker reference rules.")
    if offshore:
        insights.append(f"{offshore} endpoint(s) estimated outside Australia; not a legal finding.")
    if pii_count:
        insights.append(f"{pii_count} request(s) matched configured identifiers (raw or hashed).")
    if not insights:
        insights.append("No findings in the captured traffic; this is not a website safety verdict.")
    return {"domain": domain, "requests": total, "tracker_requests": trackers,
            "offshore_requests": offshore, "pii_requests": pii_count, "risk_score": risk,
            "risk_level": level(risk), "top_owners": [o for o, _ in owners], "insights": insights}


@app.get("/summary")
async def summary():
    with duckdb.connect(str(DB_PATH)) as conn:
        total, trackers, offshore, pii_count, unknown = conn.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE is_tracker),
                   COUNT(*) FILTER (WHERE offshore), COUNT(*) FILTER (WHERE pii_detected),
                   COUNT(*) FILTER (WHERE country IS NULL) FROM live_requests
        """).fetchone()
        owners = conn.execute("""
            SELECT owner, COUNT(*) c FROM live_requests
            WHERE third_party AND owner IS NOT NULL GROUP BY owner ORDER BY c DESC, owner LIMIT 5
        """).fetchall()
    return {"total_requests": total, "tracker_requests": trackers, "offshore_requests": offshore,
            "pii_requests": pii_count, "unknown_country_requests": unknown,
            "top_owners": [{"owner": o, "count": c} for o, c in owners],
            "coverage": {"geoip_available": bool(classifier and classifier.geoip),
                         "configured_identities": pii.identity_count if pii else 0,
                         "reference_lists_available": bool(classifier and (classifier.tracker_domains or classifier.entity_map))}}


@app.websocket("/live")
async def live_ws(websocket: WebSocket):
    if not (_host_allowed(websocket.headers.get("host")) and
            _origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host"))):
        await websocket.close(code=1008)
        return
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
    with duckdb.connect(str(DB_PATH)) as conn:
        next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM live_requests").fetchone()[0]
        while True:
            events = await queue.get()
            try:
                enriched = []
                for ev in events:
                    cls = classifier.classify(ev["url"], ev["initiator"], ev["type"])
                    hits = pii.scan_request(ev["url"], ev["body"], ev["cookies"], ev["headers"]) if pii else []
                    ts = ev["ts"] / 1000 if ev["ts"] > 100_000_000_000 else ev["ts"]
                    event = {"id": next_id, "ts": ts, "url": ev["url"],
                             "initiator": ev["initiator"], **cls,
                             "page_domain": hostname(ev["initiator"]), "pii_detected": bool(hits),
                             "pii_details": json.dumps(hits) if hits else None,
                             "fingerprinting": ev["fingerprinting"],
                             "risk_score": score_request({**cls, "url": ev["url"],
                                                          "fingerprinting": ev["fingerprinting"]}, hits)}
                    enriched.append(event)
                    next_id += 1
                columns = ["id", "ts", "url", "domain", "initiator", "is_tracker", "category", "owner",
                           "country", "country_adequacy", "pii_detected", "pii_details", "fingerprinting",
                           "risk_score", "page_domain", "third_party", "offshore", "tracker_source"]
                if enriched:
                    conn.executemany("INSERT INTO live_requests (" + ",".join(columns) + ") VALUES ("
                                     + ",".join("?" for _ in columns) + ")",
                                     [[event.get(col) for col in columns] for event in enriched])
                dead = set()
                message = json.dumps({"events": enriched, "alerts": []})
                for client in clients:
                    try:
                        await client.send_text(message)
                    except Exception:
                        dead.add(client)
                clients.difference_update(dead)
            except Exception as exc:
                print(f"[agent] Failed batch: {type(exc).__name__}; inspect the local agent log.")
            finally:
                queue.task_done()
