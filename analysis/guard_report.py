"""Turn a Guard JSON export into an escaped, offline evidence report."""
from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from protection.api import Evidence


class GuardEvent(Evidence):
    kind: Literal["network_rule", "identity_match", "overlay", "popup"]
    domain: str = Field(max_length=253)
    evidence_quality: Literal["chrome_rule_match", "local_identifier_match", "page_report_unverified", "chrome_tab_observed"]
    time: datetime
    tab_id: int

    @model_validator(mode="after")
    def consistent_source(self):
        expected = {
            "network_rule": ("network_blocked", "chrome_rule_match"),
            "identity_match": ("observed_only", "local_identifier_match"),
            "overlay": ("interaction_prevented", "page_report_unverified"),
            "popup": ("interaction_prevented", "page_report_unverified"),
        }
        valid = (self.enforcement, self.evidence_quality) == expected[self.kind]
        if self.kind == "network_rule" and self.enforcement == "navigation_quarantined" and self.evidence_quality == "chrome_rule_match":
            valid = True
        # A pop-under tab Guard closed: Chrome itself reported the tab, not the page.
        if self.kind == "popup" and (self.enforcement, self.evidence_quality) == ("interaction_prevented", "chrome_tab_observed"):
            valid = True
        if not valid:
            raise ValueError("Event handling and source are inconsistent")
        return self

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value):
        if value and not re.fullmatch(r"[a-zA-Z0-9.-]+", value):
            raise ValueError("Only domain names are accepted; remove URL paths and values")
        return value


class GuardExport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_name: Literal["dataexodus.guard.v1"] = Field(alias="schema")
    exported_at: datetime
    limits: str = Field(max_length=1000)
    events: list[GuardEvent] = Field(max_length=200)


def build_report(source: Path, out: Path):
    capture = GuardExport.model_validate_json(source.read_text(encoding="utf-8"))
    counts = Counter(event.enforcement for event in capture.events)
    closed = sum(event.evidence_quality == "chrome_tab_observed" for event in capture.events)
    rows = []
    for event in capture.events:
        cells = [event.time.isoformat(), event.domain or "unknown", ", ".join(event.signals),
                 event.enforcement, event.evidence_quality]
        rows.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>")
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>DataExodus Guard evidence</title>
<style>body{{font:15px/1.6 system-ui;background:#edf4f1;color:#193b39;margin:40px auto;max-width:1200px;padding:24px}}h1{{font-size:38px;letter-spacing:-1px}}.cards{{display:flex;gap:15px;flex-wrap:wrap}}.card{{padding:20px;background:white;border:1px solid #d1dfd7;border-radius:14px;flex:1}}b{{font-size:30px;display:block}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;border:1px solid #d5e2d9;text-align:left;overflow-wrap:anywhere}}.scroll{{overflow:auto}}small{{color:#527067}}</style>
<p>DATAEXODUS / GUARD EVIDENCE</p><h1>Protection with a record.</h1>
<p>Exported {html.escape(capture.exported_at.isoformat())}. Recent local events; not a complete browsing session.</p>
<div class="cards"><div class="card"><b>{counts['network_blocked']}</b>Chrome rule matches</div>
<div class="card"><b>{counts['interaction_prevented'] - closed}</b>Page-reported interventions, unverified</div>
<div class="card"><b>{closed}</b>Pop-up tabs closed, seen by Chrome</div>
<div class="card"><b>{counts['observed_only']}</b>Observations; prevention not established</div></div>
<p>Network navigations routed to offline quarantine: <strong>{counts['navigation_quarantined']}</strong>. The destination is not loaded by the quarantine page.</p>
<p>Chrome rule matches and local identity observations can describe the same attempted request. Do not add them to estimate unique requests or a prevention rate. A rule match is not a malware diagnosis.</p>
<p>Receiver-side lab receipts are required to corroborate whether the synthetic identifier arrived. Page reports can be forged or bypassed. No findings is not proof of safety.</p>
<div class="scroll"><table><thead><tr><th>Time</th><th>Destination</th><th>Signals</th><th>Handling</th><th>Evidence source</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="5">No events in this export.</td></tr>'}</tbody></table></div>
<p><small>Destination domains and timestamps can reveal browsing history. Review before sharing. This report performs no cloud calls.</small></p></html>"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "guard-audit.html").write_text(page, encoding="utf-8")
    (out / "guard-audit.json").write_text(json.dumps(capture.model_dump(mode="json", by_alias=True), indent=2), encoding="utf-8")
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/guard-audit"))
    args = parser.parse_args()
    print(build_report(args.events, args.out))
    print(f"Open {args.out / 'guard-audit.html'}")


if __name__ == "__main__":
    main()
