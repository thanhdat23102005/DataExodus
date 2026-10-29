import copy
import json

import duckdb
import pytest

from analysis.audit import build_audit, compare_audits, write_audit
from analysis.demo import run_demo
from analysis.export_sheet import fetch_rows
from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.process import init_db, process_batch


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo")
    return path, run_demo(path)


def test_demo_uses_real_pipeline_and_negative_control(demo):
    _, payload = demo
    before, after = payload["baseline"], payload["current"]
    assert before["summary"]["requests"] == 10
    assert before["summary"]["matched_identifier_requests"] == 4
    assert before["summary"]["high_or_critical"] == 4
    assert len(before["linkability"]) == 1
    assert len(before["linkability"][0]["sites"]) == 2
    assert after["summary"]["requests"] == 6
    assert after["summary"]["matched_identifier_requests"] == 0
    assert payload["comparison"]["comparable"] is True
    assert len(payload["comparison"]["not_observed_in_retest"]) == 6
    assert before["synthetic"] is True


def test_incomplete_or_changed_config_cannot_look_fixed(demo):
    _, payload = demo
    for mutation in ("status", "identity", "references", "mode", "protocol"):
        current = copy.deepcopy(payload["current"])
        if mutation == "status": current["sessions"][0]["crawl_status"] = "failed"
        elif mutation == "identity": current["metadata"]["identity_profile"] = "different"
        elif mutation == "references": current["metadata"]["reference_profile"] = "different"
        elif mutation == "mode": current["synthetic"] = False
        elif mutation == "protocol": current["metadata"]["protocols"] = ["different"]
        result = compare_audits(payload["baseline"], current)
        assert not result["comparable"]
        assert result["not_observed_in_retest"] == []
        assert len(result["inconclusive"]) == 6


def test_report_exports_no_identifier_values_or_body(demo):
    path, payload = demo
    text = (path / "audit.json").read_text()
    assert "student.demo@example.com" not in text
    assert "student.demo%40example.com" not in text
    assert "uid=" not in text
    assert all(r["endpoint"].endswith("/[path-redacted]")
               for f in payload["baseline"]["findings"] for r in f["evidence"])


def test_html_escapes_script_injection(demo, tmp_path):
    _, payload = demo
    report = copy.deepcopy(payload["baseline"])
    report["label"] = "</script><script>alert(1)</script>"
    write_audit(report, tmp_path)
    html = (tmp_path / "audit.html").read_text()
    assert "</script><script>alert(1)</script>" not in html
    assert "__AUDIT_PAYLOAD__" not in html


def test_reprocessing_rebuilds_exact_input_without_duplicates(demo):
    path, _ = demo
    db = path / "before" / "demo.duckdb"
    classifier = Classifier({"telemetry.example.net"}, {})
    process_batch(path / "before" / "raw", db, classifier, PIIDetector({}))
    with duckdb.connect(str(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2
    columns, rows = fetch_rows(db)
    assert len(rows) == 2
    assert sum(row[columns.index("total_requests")] for row in rows) == 10


def test_invalid_batch_does_not_destroy_previous_evidence(tmp_path):
    db = tmp_path / "test.duckdb"
    init_db(db)
    raw = tmp_path / "raw"
    raw.mkdir()
    capture = {"session_id": "one", "site": "https://example.com", "requests": [{"url": "https://example.com"}]}
    (raw / "one.json").write_text(json.dumps(capture))
    process_batch(raw, db, Classifier(set(), {}), None)
    capture["requests"] = [{"url": None}]
    (raw / "one.json").write_text(json.dumps(capture))
    with pytest.raises((TypeError, AttributeError)):
        process_batch(raw, db, Classifier(set(), {}), None)
    with duckdb.connect(str(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 1


def test_empty_raw_directory_is_not_a_success(tmp_path):
    db = tmp_path / "test.duckdb"
    init_db(db)
    with pytest.raises(ValueError, match="No raw"):
        process_batch(tmp_path, db, Classifier(set(), {}), None)
