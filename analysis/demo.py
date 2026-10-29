"""Generate a controlled before/after audit using the real classification pipeline, offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analysis.audit import ROOT, build_audit, write_audit
from analysis.export_sheet import export
from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.process import init_db, process_batch


def run_demo(out_dir: Path) -> dict:
    digest = hashlib.sha256(b"student.demo@example.com").hexdigest()
    unrelated = hashlib.sha256(b"someone.else@example.com").hexdigest()
    pii = PIIDetector.from_yaml(ROOT / "examples" / "identities.demo.yaml")
    classifier = Classifier(
        tracker_domains={"telemetry.example.net"},
        entity_map={"telemetry.example.net": {"owner": "Example Analytics (fictional)", "category": "analytics"}},
    )
    audits = {}
    for phase in ("before", "after"):
        raw_dir = out_dir / phase / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for number, (sector, site) in enumerate([
            ("demo_shop", "https://shop.example.com"),
            ("demo_clinic", "https://clinic.example.org"),
        ]):
            requests = [
                {"url": site + "/", "type": "document"},
                {"url": site + "/assets/style.css", "type": "stylesheet"},
                # Negative control: third party, but no configured identifier.
                {"url": f"https://cdn.example.net/image?v={unrelated}", "type": "image"},
            ]
            if phase == "before":
                requests.extend([
                    {"url": f"https://telemetry.example.net/pixel?uid={digest}", "type": "image"},
                    {"url": "https://telemetry.example.net/collect", "type": "fetch",
                     "body": "email=student.demo%40example.com"},
                ])
            for index, req in enumerate(requests):
                req.update(timestamp=1792627200 + number * 10 + index, initiator=site, headers={})
            session = {
                "session_id": f"demo_{phase}_{number}", "site": site, "sector": sector,
                "started_at": 1792627200 + number * 10, "ended_at": 1792627208 + number * 10,
                "crawl_status": "ok", "http_status": 200, "provenance": "synthetic_fixture",
                "fingerprinting_events": [], "requests": requests,
                "protocol": {"fixture": "controlled identity payload removed in after phase"},
            }
            (raw_dir / f"{number}.json").write_text(json.dumps(session, indent=2), encoding="utf-8")
        db = out_dir / phase / "demo.duckdb"
        init_db(db)
        process_batch(raw_dir, db, classifier, pii)
        export(db, out_dir / phase)
        audits[phase] = build_audit(db, f"Controlled demo — {phase}")
        write_audit(audits[phase], out_dir / phase)
    payload = write_audit(audits["after"], out_dir, audits["before"])
    print(f"[demo] Open {out_dir / 'audit.html'}")
    print("[demo] Synthetic fixtures only — no public websites contacted.")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/demo")
    args = parser.parse_args()
    run_demo(Path(args.out))


if __name__ == "__main__":
    main()
