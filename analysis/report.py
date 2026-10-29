"""Descriptive research outputs. Sector comparisons are not significance tests."""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from analysis.audit import build_audit, write_audit


def _table(cursor) -> str:
    names = [d[0] for d in cursor.description]
    def clean(value):
        return str(value if value is not None else "unknown").replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(names) + " |", "| " + " | ".join("---" for _ in names) + " |"]
    lines.extend("| " + " | ".join(clean(v) for v in row) + " |" for row in cursor.fetchall())
    return "\n".join(lines)


def write_research_summary(db_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    audit = build_audit(db_path, "DataExodus research capture")
    write_audit(audit, out_dir)
    lines = ["# DataExodus descriptive results", "",
             "SYNTHETIC DEMO — not public website measurements." if audit["synthetic"] else "Observed capture data only.",
             "", "The unit of comparison below is a website. Repeated captures are pooled within each site. "
             "Incomplete captures are excluded from sector rates. No hypothesis is declared supported from these descriptive tables alone.", ""]
    with duckdb.connect(str(db_path), read_only=True) as conn:
        queries = {
            "Capture coverage": """SELECT sector, crawl_status, COUNT(*) sessions,
                                  COUNT(DISTINCT site) sites FROM sessions GROUP BY sector, crawl_status ORDER BY sector, crawl_status""",
            "Per-site mean rates by sector (successful captures only)": """
                WITH site_rates AS (
                  SELECT s.sector, s.site, COUNT(r.id) n,
                         COUNT(r.id) FILTER (WHERE r.is_tracker) * 100.0 / NULLIF(COUNT(r.id),0) tracker_pct,
                         COUNT(r.id) FILTER (WHERE r.pii_detected) * 100.0 / NULLIF(COUNT(r.id),0) matched_identifier_pct
                  FROM sessions s LEFT JOIN requests r ON r.session_id=s.session_id
                  WHERE s.crawl_status='ok' GROUP BY s.sector, s.site
                ) SELECT sector, COUNT(*) sites, ROUND(AVG(tracker_pct),2) mean_site_tracker_pct,
                         ROUND(AVG(matched_identifier_pct),2) mean_site_matched_identifier_pct
                  FROM site_rates GROUP BY sector ORDER BY sector
            """,
            "Destination location coverage": """SELECT sector, COUNT(*) requests,
                COUNT(*) FILTER (WHERE offshore) non_au_estimate,
                COUNT(*) FILTER (WHERE country='AU') au_estimate,
                COUNT(*) FILTER (WHERE country IS NULL) unknown FROM requests GROUP BY sector ORDER BY sector""",
            "Listed tracker recipients": """SELECT domain, owner, tracker_source, COUNT(*) requests,
                COUNT(DISTINCT site) sites FROM requests WHERE is_tracker AND third_party
                GROUP BY domain, owner, tracker_source ORDER BY requests DESC, domain""",
            "Fingerprint API observations by session": """SELECT sector, COUNT(*) sessions,
                SUM(fingerprinting_events) api_observations FROM sessions GROUP BY sector ORDER BY sector""",
        }
        for title, query in queries.items():
            lines.extend(["## " + title, "", _table(conn.execute(query)), ""])
    lines.extend(["## Interpretation", ""] + ["- " + w for w in audit["warnings"]] + [
        "- API calls such as canvas reads can have legitimate uses. These are observations, not confirmed fingerprinting.",
        "- A passive fresh-profile visit may never send a test email because the visitor has not supplied it. A zero match count cannot refute the hash-linkability mechanism.",
        "- Compare sector distributions after the complete study and manual label validation; do not treat requests as independent people or independent websites.",
    ])
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/dataexodus.duckdb")
    parser.add_argument("--out", default="reports/research")
    args = parser.parse_args()
    write_research_summary(Path(args.db), Path(args.out))
    print(f"[report] Descriptive tables + audit → {args.out}")


if __name__ == "__main__":
    main()
