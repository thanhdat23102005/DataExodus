import json
import pytest
from protection.export_rules import export_rules


def test_export_reuses_supported_audit_rules_and_records_source(tmp_path):
    blocklists = tmp_path / "blocklists"
    blocklists.mkdir()
    (blocklists / "easyprivacy.txt").write_text("||tracker.example^\n||other.example^\n||path.example/track\n@@||allowed.example^\n||option.example^$third-party\n")
    out = tmp_path / "rules.json"
    result = export_rules(blocklists, out, limit=1)
    assert result["domains"] == ["other.example"]
    assert result["supported_rule_count"] == 2
    assert len(result["source_sha256"]) == 64
    assert json.loads(out.read_text())["schema"] == "dataexodus.guard.domains.v1"
    with pytest.raises(ValueError):
        export_rules(tmp_path / "absent", out)
