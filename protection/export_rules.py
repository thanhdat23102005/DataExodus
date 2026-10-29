"""Export a reviewed subset of audit reference domains for Guard import.

Only unconditional EasyPrivacy domain rules supported by the existing classifier
are used. This is not a full ABP/uBlock rule converter. No network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline.classify import Classifier


def export_rules(source: Path, out: Path, limit=500):
    if not (source / "easyprivacy.txt").is_file():
        raise ValueError("A local easyprivacy.txt is required; run setup_data.py first")
    classifier = Classifier.load(source)
    domains = sorted(classifier.tracker_domains)
    if not domains:
        raise ValueError("No supported unconditional domain rules were found")
    payload = {
        "schema": "dataexodus.guard.domains.v1", "domains": domains[:limit],
        "supported_rule_count": len(domains), "exported_rule_count": min(limit, len(domains)),
        "source": "easyprivacy.txt; supported unconditional domain-wide rules only",
        "source_sha256": hashlib.sha256((source / "easyprivacy.txt").read_bytes()).hexdigest(),
        "limits": "No path/options/exception conversion. Review before applying. Source license still applies.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocklists", type=Path, default=Path("data/blocklists"))
    parser.add_argument("--out", type=Path, default=Path("reports/guard-domains.json"))
    parser.add_argument("--limit", type=int, choices=range(1, 501), metavar="1..500", default=500)
    args = parser.parse_args()
    payload = export_rules(args.blocklists, args.out, args.limit)
    print(f"Exported {payload['exported_rule_count']} / {payload['supported_rule_count']} supported rules to {args.out}")


if __name__ == "__main__":
    main()
