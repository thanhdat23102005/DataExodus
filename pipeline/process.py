#!/usr/bin/env python3
"""
DataExodus — Batch Processing Pipeline
Reads raw crawl JSON → enriches → writes DuckDB.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

import duckdb

from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.risk import score_request


def _identity_profile(pii):
    if not pii or not pii.identity_count:
        return None
    # Local secret: exported signatures cannot be used as email dictionaries.
    path = Path(__file__).resolve().parent.parent / "data" / ".audit-profile-key"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    return hmac.new(path.read_bytes(), json.dumps(sorted(pii.patterns)).encode(), hashlib.sha256).hexdigest()


def init_db(db_path: str | Path):
    """Create/migrate the current schema without silently dropping evidence."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    existing_cols = {
        row[0] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'requests'"
        ).fetchall()
    }
    if existing_cols and "id" not in existing_cols:
        conn.close()
        raise ValueError("Incompatible legacy database: use a new --db path and reprocess the original raw files")
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
    for name, sql_type in {
        "third_party": "BOOLEAN", "offshore": "BOOLEAN", "insecure": "BOOLEAN",
        "tracker_source": "VARCHAR", "owner_source": "VARCHAR",
    }.items():
        conn.execute(f"ALTER TABLE requests ADD COLUMN IF NOT EXISTS {name} {sql_type}")
    for name, sql_type in {
        "crawl_status": "VARCHAR", "http_status": "INTEGER", "error": "VARCHAR",
        "fingerprinting_events": "INTEGER", "provenance": "VARCHAR",
    }.items():
        conn.execute(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {name} {sql_type}")
    conn.execute("CREATE TABLE IF NOT EXISTS scan_metadata (key VARCHAR PRIMARY KEY, value VARCHAR)")
    conn.close()


def process_batch(
    raw_dir: Path,
    db_path: Path,
    classifier: Classifier,
    pii: PIIDetector | None,
):
    raw_files = sorted(raw_dir.glob("*.json"))
    if not raw_files:
        raise ValueError(f"No raw crawl JSON in {raw_dir}; run the crawler or the controlled demo first")
    sessions = [json.loads(rf.read_text(encoding="utf-8")) for rf in raw_files]
    session_ids = [s.get("session_id", rf.stem) for s, rf in zip(sessions, raw_files)]
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("Duplicate session IDs in raw files; keep each capture once")
    conn = duckdb.connect(str(db_path))
    next_id = 1

    print(f"[process] Found {len(raw_files)} raw files")

    try:
        conn.execute("BEGIN TRANSACTION")
        # This is a derived database. Rebuild exactly the input directory, atomically.
        conn.execute("DELETE FROM requests")
        conn.execute("DELETE FROM sessions")
        metadata = {
            "schema_version": 2, "tracker_domain_rules": len(classifier.tracker_domains),
            "entity_records": len(classifier.entity_map), "geoip_available": bool(classifier.geoip),
            "configured_identities": pii.identity_count if pii else 0,
            "identity_profile": _identity_profile(pii),
            "reference_profile": hashlib.sha256(json.dumps({
                "rules": sorted(classifier.tracker_domains), "entities": classifier.entity_map,
            }, sort_keys=True).encode()).hexdigest(),
            "protocols": sorted({json.dumps(s.get("protocol", {}), sort_keys=True) for s in sessions}),
            "classifier_profile": hashlib.sha256(b"".join(
                (Path(__file__).parent / name).read_bytes() for name in ("classify.py", "pii.py", "risk.py")
            )).hexdigest(),
            "raw_sha256": {rf.name: hashlib.sha256(rf.read_bytes()).hexdigest() for rf in raw_files},
        }
        conn.execute("DELETE FROM scan_metadata")
        conn.executemany("INSERT INTO scan_metadata VALUES (?, ?)",
                         [(key, json.dumps(value)) for key, value in metadata.items()])
        for rf, data in zip(raw_files, sessions):
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

                cls = classifier.classify(url, site, resource_type)
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
                    fp, risk, ts, cls["third_party"], cls["offshore"], cls["insecure"],
                    cls["tracker_source"], cls["owner_source"]
                ))
                next_id += 1

            # Insert this capture within the transaction.
            conn.execute("DELETE FROM requests WHERE session_id = ?", [session_id])
            if rows:
                conn.executemany("""
                    INSERT INTO requests (
                        id, session_id, site, sector, url, domain, initiator, resource_type,
                        is_tracker, category, owner, country, country_adequacy, pii_detected,
                        pii_details, fingerprinting, risk_score, timestamp,
                        third_party, offshore, insecure, tracker_source, owner_source
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, rows)

            # Upsert session
            conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, site, sector, started_at, ended_at, total_requests, tracker_requests,
                    crawl_status, http_status, error, fingerprinting_events, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, site, sector,
                data.get("started_at", 0.0), data.get("ended_at", 0.0),
                len(requests), tracker_count,
                data.get("crawl_status", "unknown"), data.get("http_status"), data.get("error"),
                len(data.get("fingerprinting_events", [])), data.get("provenance", "observed_capture")
            ))
            print(f"[process] {site}: {len(requests)} requests, {tracker_count} trackers")

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    print(f"[process] Done. Database: {db_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw", help="Raw JSON directory")
    parser.add_argument("--db", default="data/dataexodus.duckdb", help="Output DuckDB path")
    parser.add_argument("--identities", default="data/identities.local.yaml", help="PII identities file")
    parser.add_argument("--blocklists", default="data/blocklists", help="Blocklist directory")
    parser.add_argument("--geoip", default="data/blocklists/GeoLite2-Country.mmdb", help="GeoIP DB")
    parser.add_argument("--skip-export", action="store_true", help="Skip per-site CSV/XLSX export")
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

    try:
        process_batch(raw_dir, db_path, classifier, pii)
        if not args.skip_export:
            from analysis.export_sheet import export
            export(db_path, db_path.parent)
    finally:
        classifier.close()


if __name__ == "__main__":
    main()
