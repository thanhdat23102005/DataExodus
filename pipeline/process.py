#!/usr/bin/env python3
"""
DataExodus — Batch Processing Pipeline
Reads raw crawl JSON → enriches → writes DuckDB.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import yaml

from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.risk import score_request


def init_db(db_path: str | Path):
    """Create tables if not exist, recreating 'requests' if a different
    (e.g. older) schema is already sitting at this path - it's fully
    rebuilt from data/raw/ on every run, never hand-appended to, so
    replacing it is safe."""
    conn = duckdb.connect(str(db_path))
    existing_cols = {
        row[0] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'requests'"
        ).fetchall()
    }
    if existing_cols and "id" not in existing_cols:
        print("[process] 'requests' table has an incompatible schema, recreating...")
        conn.execute("DROP TABLE requests")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY,
            session_id VARCHAR,
            site VARCHAR,
            sector VARCHAR,
            url VARCHAR,
            domain VARCHAR,
            initiator VARCHAR,
            resource_type VARCHAR,
            is_tracker BOOLEAN,
            category VARCHAR,
            owner VARCHAR,
            country VARCHAR,
            country_adequacy BOOLEAN,
            pii_detected BOOLEAN,
            pii_details VARCHAR,
            fingerprinting BOOLEAN,
            risk_score INTEGER,
            timestamp DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR PRIMARY KEY,
            site VARCHAR,
            sector VARCHAR,
            started_at DOUBLE,
            ended_at DOUBLE,
            total_requests INTEGER,
            tracker_requests INTEGER
        )
    """)
    conn.close()


def process_batch(
    raw_dir: Path,
    db_path: Path,
    classifier: Classifier,
    pii: PIIDetector | None,
):
    conn = duckdb.connect(str(db_path))
    # Get current max id
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
    next_id = (row[0] or 0) + 1

    raw_files = sorted(raw_dir.glob("*.json"))
    print(f"[process] Found {len(raw_files)} raw files")

    for rf in raw_files:
        data = json.loads(rf.read_text(encoding="utf-8"))
        session_id = data.get("session_id", rf.stem)
        site = data.get("site", "unknown")
        sector = data.get("sector", "unknown")
        requests = data.get("requests", [])

        tracker_count = 0
        rows = []
        for req in requests:
            url = req.get("url", "")
            initiator = req.get("initiator")
            resource_type = req.get("type", "")
            body = req.get("body")
            cookies = req.get("cookies")
            headers = req.get("headers", {})
            ts = req.get("timestamp", 0.0)
            fp = req.get("fingerprinting", False)

            cls = classifier.classify(url, initiator, resource_type)
            pii_hits = pii.scan_request(url, body, cookies, headers) if pii else []
            risk = score_request({**cls, "url": url, "fingerprinting": fp}, pii_hits)

            if cls["is_tracker"]:
                tracker_count += 1

            rows.append((
                next_id, session_id, site, sector,
                url, cls["domain"], initiator, resource_type,
                cls["is_tracker"], cls["category"], cls["owner"],
                cls["country"], cls["country_adequacy"],
                bool(pii_hits), json.dumps(pii_hits) if pii_hits else None,
                fp, risk, ts
            ))
            next_id += 1

        # Bulk insert
        if rows:
            conn.executemany("""
                INSERT INTO requests VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, rows)

        # Upsert session
        conn.execute("""
            INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, site, sector,
            data.get("started_at", 0.0), data.get("ended_at", 0.0),
            len(requests), tracker_count
        ))
        print(f"[process] {site}: {len(requests)} requests, {tracker_count} trackers")

    conn.close()
    print(f"[process] Done. Database: {db_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw", help="Raw JSON directory")
    parser.add_argument("--db", default="data/dataexodus.duckdb", help="Output DuckDB path")
    parser.add_argument("--identities", default="data/identities.local.yaml", help="PII identities file")
    parser.add_argument("--blocklists", default="data/blocklists", help="Blocklist directory")
    parser.add_argument("--geoip", default="data/blocklists/GeoLite2-Country.mmdb", help="GeoIP DB")
    args = parser.parse_args()

    raw_dir = Path(args.raw)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    init_db(db_path)
    classifier = Classifier.load(args.blocklists, args.geoip)

    pii = None
    if Path(args.identities).exists():
        pii = PIIDetector.from_yaml(args.identities)
    else:
        print(f"[process] No identities file at {args.identities}, PII detection disabled")

    process_batch(raw_dir, db_path, classifier, pii)


if __name__ == "__main__":
    main()
