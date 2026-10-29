"""Produce an actionable, redacted privacy audit and a cautious before/after comparison."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import duckdb

ROOT = Path(__file__).resolve().parent.parent


def _origin(url):
    from pipeline.classify import hostname
    parsed = urlparse(url)
    return f"{parsed.scheme}://{hostname(url)}" if hostname(url) else "[unknown origin]"


def _rows(conn, query):
    cursor = conn.execute(query)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def finding_key(finding: dict) -> str:
    return "|".join(str(finding.get(k) or "") for k in
                    ("site", "rule", "recipient", "surface", "form", "algorithm"))


def build_audit(db_path: Path, label: str = "Website privacy audit") -> dict:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        sessions = _rows(conn, "SELECT * FROM sessions ORDER BY site, session_id")
        rows = _rows(conn, "SELECT * FROM requests ORDER BY site, session_id, id")
        metadata = {key: json.loads(value) for key, value in
                    conn.execute("SELECT key, value FROM scan_metadata").fetchall()}
    if not sessions:
        raise ValueError("No captured sessions: an empty database cannot establish an absence of findings")
    for session in sessions:
        session["site"] = _origin(session["site"])
        if session.get("error"):
            session["error"] = "Navigation error; inspect the local raw capture for details."
    for row in rows:
        row["site"] = _origin(row["site"])
    findings = {}
    links = defaultdict(lambda: {"sites": set(), "recipients": set()})
    link_key = secrets.token_bytes(32)

    def add(row, rule, severity, title, why, action, hit=None):
        hit = hit or {}
        finding = {
            "site": row["site"], "rule": rule, "severity": severity, "title": title,
            "recipient": row["domain"], "owner": row["owner"], "country": row["country"],
            "surface": hit.get("surface"), "form": hit.get("form"),
            "algorithm": hit.get("algo"), "explanation": why, "remediation": action,
            "confidence": "matched configured identifier" if hit else "reference-list match",
            "tracker_source": row.get("tracker_source"), "evidence": [],
        }
        key = finding_key(finding)
        if key not in findings:
            finding["id"] = "DX-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper()
            findings[key] = finding
        # Export no URL path/query values, body, cookie, identifier or matched digest.
        parsed = urlparse(row["url"])
        evidence = {
            "request_id": row["id"], "session_id": row["session_id"],
            "endpoint": f"{parsed.scheme}://{row['domain']}/[path-redacted]",
            "resource_type": row["resource_type"], "timestamp": row["timestamp"],
            "surface": hit.get("surface"), "encoding": hit.get("encoding"),
            "observation": "outbound request observed; receipt or subsequent use not verified",
        }
        findings[key]["evidence"].append(evidence)

    for row in rows:
        hits = json.loads(row["pii_details"] or "[]")
        if row["third_party"] and row["is_tracker"]:
            add(row, "KNOWN_TRACKER", "medium", "Review a listed third-party tracker",
                "The destination matches a supported reference rule; a match does not establish illegality.",
                "Identify the responsible tag or plugin. Remove unused tags or restrict their firing; retest the same journey.")
        for hit in hits:
            if row["third_party"]:
                form = hit["form"]
                add(row, "IDENTIFIER_TO_THIRD_PARTY", "high", f"{form.capitalize()} identifier in a third-party request",
                    f"A locally configured {hit['type']} matched on {hit.get('surface', 'unknown surface')}. "
                    + ("The deterministic hash is linkable; actual downstream profiling is unverified."
                       if form == "hashed" else "The request contains the configured identifier in readable form."),
                    "Remove this identifier from the tag payload or URL. Check tag-manager variables and SDK settings; use a test identity and repeat the journey.", hit)
                if hit.get("hash"):
                    # Link within this local audit; never export the original digest.
                    token = hmac.new(link_key, hit["hash"].encode(), hashlib.sha256).hexdigest()[:16]
                    links[token]["sites"].add(row["site"])
                    links[token]["recipients"].add(row["domain"])
            if row["insecure"]:
                add(row, "IDENTIFIER_OVER_HTTP", "critical", "Identifier in an unencrypted HTTP request",
                    "The browser attempted an HTTP request containing a matched identifier.",
                    "Remove identifiers from URLs and payloads where unnecessary; enforce HTTPS and review the sending integration.", hit)

    ordered = sorted(findings.values(), key=lambda f: (
        {"critical": 0, "high": 1, "medium": 2}[f["severity"]], f["site"], f["id"]))
    synthetic = any(s.get("provenance") in {"synthetic_fixture", "controlled_local_browser"} for s in sessions)
    warnings = [
        "This report covers captured requests in the stated sessions, not the entire website or all users.",
        "Country is a DNS/GeoIP estimate of an endpoint, not proof of data storage or an APP 8 breach.",
        "A listed tracker, third-party request or fingerprint API call alone is not proof of misuse.",
        "Redacted reports still contain site/domain history. Review them before sharing; raw captures and databases contain more sensitive data.",
    ]
    if synthetic:
        warnings.insert(0, "CONTROLLED DEMO: generated fixtures or local test sites with synthetic identities; not public website measurements.")
    if not metadata.get("configured_identities"):
        warnings.append("No configured identifiers: absence of identity matches is inconclusive.")
    if not metadata.get("tracker_domain_rules") and not metadata.get("entity_records"):
        warnings.append("Reference lists are missing: tracker detection coverage is unavailable.")
    if not metadata.get("geoip_available"):
        warnings.append("GeoIP is unavailable: destinations remain unknown, not Australian by default.")
    incomplete = [s["site"] for s in sessions if s.get("crawl_status") != "ok"]
    if incomplete:
        warnings.append("Incomplete or unverified captures: " + ", ".join(sorted(set(incomplete))))
    return {
        "schema_version": 1, "label": label, "synthetic": synthetic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "sites": len({s["site"] for s in sessions}), "sessions": len(sessions),
            "requests": len(rows), "third_party_requests": sum(r["third_party"] is True for r in rows),
            "tracker_requests": sum(bool(r["is_tracker"]) for r in rows),
            "matched_identifier_requests": sum(bool(r["pii_detected"]) for r in rows),
            "offshore_requests": sum(r["offshore"] is True for r in rows),
            "unknown_country_requests": sum(r["country"] is None for r in rows),
            "findings": len(ordered), "high_or_critical": sum(f["severity"] in {"high", "critical"} for f in ordered),
        },
        "sessions": sessions, "metadata": metadata, "findings": ordered,
        "linkability": [{"match_token": token, "sites": sorted(v["sites"]),
                         "recipients": sorted(v["recipients"]),
                         "interpretation": "same deterministic hash observed across sites; downstream use unverified"}
                        for token, v in sorted(links.items()) if len(v["sites"]) > 1],
        "warnings": warnings,
    }


def compare_audits(before: dict, current: dict) -> dict:
    old = {finding_key(f): f for f in before["findings"]}
    new = {finding_key(f): f for f in current["findings"]}
    old_sites = {s["site"] for s in before["sessions"]}
    new_sites = {s["site"] for s in current["sessions"]}
    capture_ok = all(s.get("crawl_status") == "ok" for s in before["sessions"] + current["sessions"])
    same_mode = before["synthetic"] == current["synthetic"]
    metadata_keys = ("reference_profile", "identity_profile", "classifier_profile", "protocols",
                     "geoip_available", "configured_identities")
    matching_coverage = all(before["metadata"].get(k) == current["metadata"].get(k) for k in metadata_keys)
    comparable = old_sites == new_sites and capture_ok and same_mode and matching_coverage
    return {
        "comparable": comparable,
        "interpretation": "Absence in a retest is evidence for this capture only; it is not a permanent fix or compliance certification.",
        "new": [new[k] for k in sorted(new.keys() - old.keys())],
        "persists": [new[k] for k in sorted(new.keys() & old.keys())],
        "not_observed_in_retest": [old[k] for k in sorted(old.keys() - new.keys())] if comparable else [],
        "inconclusive": [old[k] for k in sorted(old.keys() - new.keys())] if not comparable else [],
        "baseline_summary": before["summary"], "current_summary": current["summary"],
    }


def write_audit(report: dict, out_dir: Path, before: dict | None = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"current": report, "baseline": before,
               "comparison": compare_audits(before, report) if before else None}
    (out_dir / "audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    template = (ROOT / "analysis" / "audit_template.html").read_text(encoding="utf-8")
    safe_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    (out_dir / "audit.html").write_text(template.replace("__AUDIT_PAYLOAD__", safe_json), encoding="utf-8")
    lines = ["# " + report["label"], "", "SYNTHETIC DEMO" if report["synthetic"] else "Captured website traffic", ""]
    for key, value in report["summary"].items():
        lines.append(f"- {key.replace('_', ' ')}: {value}")
    lines.extend(["", "## Findings", ""])
    for f in report["findings"]:
        lines.extend([f"### {f['id']} — {f['title']}", f"{f['site']} → {f['recipient']}",
                      f["explanation"], "", "Action: " + f["remediation"], ""])
    lines.extend(["## Interpretation and coverage", ""] + ["- " + w for w in report["warnings"]])
    if payload["comparison"]:
        c = payload["comparison"]
        lines.extend(["", "## Retest", "", f"Comparable captures: {c['comparable']}",
                      f"New: {len(c['new'])}; persists: {len(c['persists'])}; not observed: {len(c['not_observed_in_retest'])}; inconclusive: {len(c['inconclusive'])}.",
                      c["interpretation"]])
    (out_dir / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/dataexodus.duckdb")
    parser.add_argument("--baseline", help="Earlier audit.json to compare with")
    parser.add_argument("--out", default="reports/current")
    parser.add_argument("--label", default="Website privacy audit")
    args = parser.parse_args()
    before = json.loads(Path(args.baseline).read_text(encoding="utf-8"))["current"] if args.baseline else None
    report = build_audit(Path(args.db), args.label)
    write_audit(report, Path(args.out), before)
    print(f"[audit] {report['summary']['findings']} findings → {args.out}/audit.html")


if __name__ == "__main__":
    main()
