"""Run a real browser capture against the local before/after lab. Chromium is required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.audit import ROOT, build_audit, write_audit
from crawler.crawl import crawl_site
from examples.demo_lab import Lab
from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.process import init_db, process_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/local-lab")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = Path(args.out)
    classifier = Classifier({"127.0.0.2"}, {"127.0.0.2": {"owner": "Local lab collector", "category": "analytics"}})
    pii = PIIDetector.from_yaml(ROOT / "examples" / "identities.demo.yaml")
    audits = {}
    for phase in ("before", "after"):
        phase_dir = root / phase
        raw = phase_dir / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        # Give each execution its own output root to preserve prior evidence.
        if list(raw.glob("*.json")):
            raise SystemExit(f"{raw} already contains evidence; choose a fresh --out directory")
        with Lab(phase, args.port) as lab:
            for index, site in enumerate(lab.origins):
                session = crawl_site(site, f"local_demo_{index}", raw, dwell=2, timeout=15)
                session["provenance"] = "controlled_local_browser"
                (raw / (session["session_id"] + ".json")).write_text(json.dumps(session, indent=2), encoding="utf-8")
            (phase_dir / "collector_receipts.json").write_text(json.dumps(lab.received, indent=2), encoding="utf-8")
            expected = 2 if phase == "before" else 0
            if len(lab.received) != expected:
                raise RuntimeError(f"Expected {expected} local collector receipts; got {len(lab.received)}. Inspect capture errors.")
        db = phase_dir / "capture.duckdb"
        init_db(db)
        process_batch(raw, db, classifier, pii)
        audits[phase] = build_audit(db, f"Controlled local browser lab — {phase}")
        write_audit(audits[phase], phase_dir)
    write_audit(audits["after"], root, audits["before"])
    print(f"Open {root / 'audit.html'}; collector_receipts.json confirms local receipt.")


if __name__ == "__main__":
    main()
