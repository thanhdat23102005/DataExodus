import json
import pytest
from pydantic import ValidationError
from analysis.guard_report import build_report


def test_guard_report_keeps_observation_and_enforcement_separate(tmp_path):
    event = {"signals": ["identifier_hash"], "resource_type": "request", "third_party": None,
             "kind": "identity_match", "domain": "collector.example", "enforcement": "observed_only",
             "evidence_quality": "local_identifier_match", "time": "2026-10-22T00:00:00Z", "tab_id": 3}
    data = {"schema": "dataexodus.guard.v1", "exported_at": "2026-10-22T00:01:00Z", "limits": "bounded events", "events": [event]}
    source = tmp_path / "export.json"
    source.write_text(json.dumps(data))
    assert build_report(source, tmp_path / "report") == {"observed_only": 1}
    rendered = (tmp_path / "report/guard-audit.html").read_text()
    assert "prevention not established" in rendered
    assert "Page-reported interventions, unverified" in rendered
    data["events"][0]["domain"] = '<script>alert(1)</script>'
    source.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        build_report(source, tmp_path / "bad")


def test_network_quarantine_report_preserves_handling_and_rejects_forged_source(tmp_path):
    event = {"signals": ["tracker_rule"], "resource_type": "navigation", "third_party": None,
             "kind": "network_rule", "domain": "ads.example", "enforcement": "navigation_quarantined",
             "evidence_quality": "chrome_rule_match", "time": "2026-10-23T00:00:00Z", "tab_id": 3}
    data = {"schema": "dataexodus.guard.v1", "exported_at": "2026-10-23T00:01:00Z", "limits": "bounded", "events": [event]}
    source = tmp_path / "events.json"
    source.write_text(json.dumps(data))
    assert build_report(source, tmp_path / "report") == {"navigation_quarantined": 1}
    assert "Network navigations routed to offline quarantine" in (tmp_path / "report/guard-audit.html").read_text()
    data["events"][0]["evidence_quality"] = "page_report_unverified"
    source.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        build_report(source, tmp_path / "bad")


def test_closed_popup_tab_is_counted_apart_from_page_reports(tmp_path):
    event = {"signals": ["popup_without_link"], "resource_type": "popup", "third_party": None,
             "kind": "popup", "domain": "casino.example", "enforcement": "interaction_prevented",
             "evidence_quality": "chrome_tab_observed", "time": "2026-10-28T00:00:00Z", "tab_id": 3}
    data = {"schema": "dataexodus.guard.v1", "exported_at": "2026-10-28T00:01:00Z", "limits": "bounded", "events": [event]}
    source = tmp_path / "events.json"
    source.write_text(json.dumps(data))
    assert build_report(source, tmp_path / "report") == {"interaction_prevented": 1}
    rendered = (tmp_path / "report/guard-audit.html").read_text()
    assert "<b>1</b>Pop-up tabs closed, seen by Chrome" in rendered
    assert "<b>0</b>Page-reported interventions, unverified" in rendered
    data["events"][0]["kind"] = "overlay"
    source.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        build_report(source, tmp_path / "bad")
