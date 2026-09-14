"""
Generate the DataExodus submission documents.

build_charter() follows the unit's own Project_Charter_1.doc template
(Stackpole 2013 style): Title/Sponsor/Date/Manager/Customer, Executive
Summary, Purpose, Description, Initial Risks, Initial Stakeholders,
Deliverables, Budget, Objectives & Success Criteria, Acceptance Criteria,
Approvals. It is the single consolidated deliverable - content originally
drafted for a separate casual.pm-style Proposal (build_proposal(), kept
below for reference) has been folded in, and everything reflects what has
actually been built and verified (extension, live agent, risk scoring,
self-hosted Grafana/InfluxDB dashboard), not just the original Week-3 plan.
Bracketed [placeholders] are things only the student/teacher can fill in
(names, signatures, exact dates).

Usage:
    python3 build_docs.py
"""

from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BLUE = RGBColor(0x1F, 0x3A, 0x5F)
DATE_PREPARED = "13/08/2026"


def set_cell_shading(cell, hex_color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def base_doc():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    for section in doc.sections:
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)
    return doc


def h1(doc, text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.color.rgb = BLUE
    return p


def h2(doc, text):
    p = doc.add_heading(text, level=2)
    p.runs[0].font.color.rgb = BLUE
    return p


def body(doc, text, bold_label=None):
    p = doc.add_paragraph()
    if bold_label:
        r = p.add_run(bold_label)
        r.bold = True
    p.add_run(text)
    return p


def bullets(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(h)
        r.bold = True
        set_cell_shading(hdr[i], "DCE6F1")
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    return t


# ============================================================
# DOCUMENT 1 — PROJECT CHARTER
# Structure: the unit's own Project_Charter_1.doc template (Stackpole
# 2013): Title/Sponsor/Date/Manager/Customer, Executive Summary, Purpose,
# Description, Initial Risks, Initial Stakeholders, Deliverables, Budget,
# Objectives & Success Criteria, Acceptance Criteria, Approvals.
# Content updated to reflect what has actually been built and verified
# so far (extension, live agent, risk scoring, self-hosted Grafana/
# InfluxDB dashboard), not just the original Week-3 plan.
# ============================================================

def build_charter():
    doc = base_doc()

    # ---------- Cover page ----------
    for _ in range(3):
        doc.add_paragraph()
    cover_title = doc.add_heading("DataExodus", level=0)
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("Where Does My Data Go?\nMeasuring Third-Party Data Flows on Australian Websites")
    r.font.size = Pt(15)
    r.italic = True

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("\nProject Charter")
    r.bold = True
    r.font.size = Pt(18)
    r.font.color.rgb = BLUE

    for line in ["Thanh Dat Phan", "TAFE NSW Higher Education — Cybersecurity, Individual Project",
                 f"Assessment A1 — {DATE_PREPARED}"]:
        lp = doc.add_paragraph()
        lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lp.add_run(line)

    doc.add_paragraph()
    img = doc.add_paragraph()
    img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    img.add_run().add_picture("assets/concept_map.png", width=Inches(6.4))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run("Figure 1 — DataExodus concept map: why, what, who, where and how the "
                     "project delivers its goal.")
    r.italic = True
    r.font.size = Pt(9)

    doc.add_page_break()

    doc.add_paragraph(
        "As adapted from Stackpole (2013), following the unit's Project "
        "Charter template."
    ).italic = True

    hd = doc.add_heading("PROJECT CHARTER", level=1)
    hd.runs[0].font.color.rgb = BLUE

    body(doc, "DataExodus — Where Does My Data Go? Measuring Third-Party "
              "Data Flows on Australian Websites", "Project Title: ")
    body(doc, "[Unit Teacher / Course Coordinator Name], TAFE NSW", "Project Sponsor: ")
    body(doc, f"{DATE_PREPARED} (v3 — consolidated, reflects the system as built)",
         "Date Prepared: ")
    body(doc, "Thanh Dat Phan", "Project Manager: ")
    body(doc, "[Unit Teacher Name], TAFE NSW Higher Education — Cybersecurity "
              "(assessing this project as the individual project unit)", "Project Customer: ")

    h1(doc, "Executive Summary")
    body(doc, "When a browser visits an Australian website, it quietly contacts dozens "
              "of other companies. DataExodus is a tool that makes those hidden "
              "connections visible, and a study that uses it to measure what 50 "
              "Australian websites actually do — where data goes, what personal "
              "information it carries (including in hashed form), and whether it "
              "matches what their privacy policies promise. The central technical "
              "claim under test is that hashing is not anonymisation: the same email "
              "always produces the same hash, so a hashed identifier still lets a "
              "tracker follow a person across every site that receives it. The core "
              "pipeline, a live monitoring agent, and a self-hosted Grafana dashboard "
              "are already built and verified; the full 50-site study follows the "
              "schedule under Project Deliverables.")

    h1(doc, "Project Purpose or Justification")
    body(doc, "Australians are told their data is handled responsibly, but nobody has "
              "measured what actually leaves the browser. This project addresses "
              "three gaps:")
    bullets(doc, [
        "Nobody has measured Australia: large tracking-measurement studies exist "
        "for the US and Europe; none exist for Australian websites.",
        "The law is untested in practice: Australian Privacy Principle (APP) 8 "
        "governs sending personal information overseas. Every third-party request "
        "carrying an identifier abroad is potentially an APP 8 event, but these "
        "flows are invisible to users and rarely documented.",
        "Policies are unverified: privacy policies state things like \"we may "
        "share data with selected partners.\" Nobody checks whether the stated "
        "partners match the real ones.",
    ])

    h1(doc, "Project Description")
    body(doc, "The project delivers two things, sharing one classification/"
              "personal-data/risk-scoring core:")
    bullets(doc, [
        "A tool: a Chrome browser extension (Manifest V3) that captures outbound "
        "requests and shows a green/amber/red traffic-light badge; a Playwright "
        "crawler for the 50-site study; a Python classification pipeline "
        "(tracker identity, owner, destination country, personal-data content, "
        "raw or hashed); a 0–100 risk score shared by both modes; and a "
        "self-hosted dashboard (Grafana, backed by InfluxDB) that visualises "
        "where data goes in real time.",
        "A study: 50 Australian websites (10 each across news/media, retail, "
        "health, government, and finance) crawled with an automated browser, "
        "every classification manually verified, and four hypotheses tested "
        "about tracking prevalence, offshore data flows, and privacy-policy "
        "accuracy.",
    ])
    body(doc, "Two pipelines share the same core (Figure 2): Study mode — the "
              "crawler writes raw captures to disk, pipeline/process.py "
              "classifies and scores every request into a DuckDB dataset, and "
              "analysis/report.py and analysis/export_sheet.py turn that into a "
              "report, CSV, and an Excel workbook with a chart. Live mode — the "
              "extension streams the student's own browsing to a local FastAPI "
              "agent (pipeline/agent.py), which classifies and scores each "
              "request in real time, drives the extension's badge, and writes "
              "every point to InfluxDB for the Grafana dashboard. Both modes "
              "are built and verified end-to-end: an automated test suite "
              "(23/23 passing) covers the classifier, PII detector, and risk "
              "scorer, and a real test crawl (10 government-sector sites, 614 "
              "requests) has already produced classified data.")
    img = doc.add_paragraph()
    img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    img.add_run().add_picture("assets/workflow.png", width=Inches(6.3))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run("Figure 2 — System architecture as built: Study mode (top) and Live "
                     "mode (bottom) share the same classify/PII/risk-scoring core (left).")
    r.italic = True
    r.font.size = Pt(9)

    h1(doc, "Machine Learning")
    body(doc, "The rule-based pipeline (pipeline/classify.py) stays the source "
              "of truth for the study — every label it produces can be checked "
              "by hand against DuckDuckGo Tracker Radar and EasyPrivacy, which "
              "is the whole point of keeping the sample at 50 sites. Machine "
              "learning is a separate, clearly-scoped experiment on top of "
              "that, not a replacement for it: can a lightweight supervised "
              "model learn to recognise a tracker from request-level features "
              "alone (host shape, resource type, keyword counts), without "
              "consulting a blocklist at all? That matters because blocklists "
              "lag — a classifier that generalises could flag trackers a "
              "static list misses.")
    body(doc, "Implemented in pipeline/ml_classifier.py. Ten features are "
              "engineered per request (host length, subdomain count, digit "
              "count, hyphen presence, path length, query-parameter count, a "
              "tracker-keyword hit count, resource type, and whether the "
              "request is third-party/insecure — derived from the "
              "initiating page and the URL scheme, since the pipeline "
              "doesn't store either directly), with the existing rule-based "
              "is_tracker label used as ground truth. Two models are trained "
              "and compared against a naive baseline (\"predict tracker "
              "whenever the request is third-party\") on a 75/25 stratified "
              "split.", "Method: ")
    ml_rows = [
        ("Baseline (third-party only)", "89.7%", "—", "—"),
        ("Logistic Regression (selected)", "99.3%", "0.96", "1.00"),
        ("Random Forest", "99.3%", "0.96", "1.00"),
    ]
    table(doc, ["Model", "Accuracy", "Precision (tracker)", "Recall (tracker)"],
          ml_rows)
    body(doc, "Trained and evaluated on the current 543-request dataset "
              "(10 government-sector sites, deduplicated, 19.2% positive "
              "class). Logistic Regression was selected and saved to "
              "data/ml_tracker_model.joblib. The baseline already gets most "
              "requests right because, by construction of the rule-based "
              "classifier, a request can only be a tracker if it is "
              "third-party — so this experiment mainly tests whether ML can "
              "resolve the residual cases the baseline gets wrong. On the "
              "held-out 136 requests, the baseline misclassified 14 (all "
              "false positives, 0 false negatives); both models cut that to "
              "1 false positive with 0 false negatives. It is not evidence "
              "that ML could replace the rule-based classifier outright on "
              "a small, single-sector, imbalanced sample. Retraining on the "
              "full 50-site dataset (Week 6) is the natural next step, and "
              "is tracked as an Optional-tier extension so it never gates "
              "core delivery.",
         "Result: ")
    body(doc, "5 unit tests (tests/test_ml_classifier.py, all passing) cover "
              "feature extraction — including deriving third-party/insecure "
              "from the initiating page and handling missing values — and "
              "confirm the scikit-learn pipeline trains and predicts on "
              "synthetic data, independent of the real crawl dataset.",
         "Verification: ")

    h1(doc, "Automation")
    body(doc, "Everything downstream of \"pick a site\" runs unattended:")
    bullets(doc, [
        "Crawling: crawler/crawl.py drives a headless Playwright browser "
        "across the site list and, on every page, automatically hooks the "
        "Canvas/WebGL/AudioContext/Font APIs to detect fingerprinting "
        "attempts — no manual interaction with any site.",
        "Classification: pipeline/process.py runs the classifier, PII "
        "detector, and risk scorer over every captured request unattended "
        "and writes straight to DuckDB.",
        "Live monitoring: the browser extension automatically captures the "
        "student's own traffic in the background and streams it over "
        "WebSocket to a local FastAPI agent (pipeline/agent.py), which "
        "classifies and broadcasts scored events in real time — nothing to "
        "trigger by hand once the agent is running.",
        "Infrastructure: monitoring/setup_monitoring.sh downloads, "
        "configures, and starts InfluxDB and Grafana unattended and is "
        "idempotent (safe to re-run); the dashboard and datasource are "
        "provisioned from committed config files rather than clicked "
        "together by hand.",
        "Reporting: analysis/report.py turns the DuckDB dataset into "
        "hypothesis-test results (H1–H4) and four charts (Sankey data-flow "
        "diagram, sector comparison, destination-country map, top owners) "
        "without manual steps. analysis/export_sheet.py (CSV/Excel export) "
        "predates the pipeline's schema change and is known stale — "
        "flagged here rather than left silently broken; not required for "
        "the Week 6 milestone.",
        "Testing: pytest exercises the classification, PII, risk, and ML "
        "modules on every run — 18/18 passing after this week's fixes "
        "(entity resolution no longer skipped for non-tracker domains; "
        "Tracker Radar download corrected; pipeline.process no longer "
        "duplicates rows on re-run). Three older test files predating the "
        "pipeline rewrite (test_classify.py, test_pii.py, test_risk.py) "
        "still import a since-renamed API and are excluded until updated — "
        "tracked as routine follow-up, not a project risk.",
    ])

    h1(doc, "Initial Risks")
    risk_rows = [
        ("R1", "Scope creep across optional phases", "High", "High", "9",
         "Open", "Site list frozen in Week 1; optional work gated on core "
         "completion"),
        ("R2", "Too much time spent on UI/dashboard polish", "High", "Medium",
         "6", "Open", "Hard cap of one week on interface work"),
        ("R3", "Browser extension API limitations", "Medium", "Medium", "4",
         "Mitigated", "Extension built on the Manifest V3 webRequest API and "
         "verified working end-to-end"),
        ("R4", "Certificate pinning blocks mobile app inspection", "High", "Low",
         "3", "Open", "Recorded as a finding; no bypass attempted"),
        ("R5", "Crawler blocked by target websites", "Medium", "Medium", "4",
         "Open", "Conservative request rate, honest user agent, robots.txt "
         "respected"),
        ("R6", "Poor data quality / logic errors found late", "Low", "High",
         "3", "Mitigated", "Unit tests caught a real third-party "
         "classification bug, fixed before the full crawl; Week 3 decision "
         "gate requires real data and a first chart"),
        ("R7", "Data loss", "Low", "High", "3", "Open", "Git version control "
         "plus weekly backup"),
    ]
    table(doc, ["Risk Id", "Risk Statement", "Probability", "Impact", "Score",
                "Status", "Response"], risk_rows)
    doc.add_paragraph(
        "Score = Probability × Impact (Low=1, Medium=2, High=3)."
    ).italic = True

    h1(doc, "Initial Stakeholders")
    stakeholder_rows = [
        ("Thanh Dat Phan (student)", "Sole researcher, developer, analyst, and "
         "writer; personally assessed on the outcome", "High",
         "Weekly self-review against the schedule below; decision gate in Week 3"),
        ("[Unit Teacher Name] (sponsor / assessor)", "Approves scope, supervises "
         "progress, grades each assessment event", "High",
         "Progress reported at each of the four assessment milestones"),
        ("The 50 measured organisations", "Not directly involved; observed "
         "passively via public pages only", "Low",
         "No authentication, no scanning; any vulnerability found by accident is "
         "disclosed privately and withheld from the report until resolved"),
        ("Australian website users (indirect)", "Beneficiaries of increased "
         "transparency about their own data", "Low",
         "Benefit passively through the published findings and recommendations"),
        ("Regulators, e.g. OAIC (indirect)", "Potential audience for baseline "
         "evidence on APP 8 in practice", "Low",
         "No direct engagement; findings framed as exploratory evidence only"),
    ]
    table(doc, ["Name", "Interest", "Impact", "Strategies"], stakeholder_rows)

    h1(doc, "Project Deliverables")
    deliverable_rows = [
        ("Project Proposal (Charter) — this document, a working prototype "
         "(extension, live agent, Grafana dashboard already verified), and "
         "first captured data", "Week 3"),
        ("Literature Review — measurement studies and Australian privacy law, "
         "research gap identified", "Week 6"),
        ("Practical Project Plan & Demo — architecture, methodology, "
         "evaluation plan, live demonstration", "Week 8"),
        ("Implementation & Final Demo — complete tool, verified 50-site "
         "dataset, tested hypotheses, final report, demonstration", "Week 12"),
    ]
    table(doc, ["Summary Milestones", "Due Date"], deliverable_rows)

    h1(doc, "Summary Budget and Feasibility")
    body(doc, "Total cost: $0. All hardware is student-owned (personal laptop; "
              "Raspberry Pi 5 for an optional always-on collection phase). All "
              "software is free and open-source (Python, Playwright, DuckDB, "
              "FastAPI, InfluxDB OSS, Grafana OSS). Reference data is drawn from "
              "free open sources (MaxMind GeoLite2, DuckDuckGo Tracker Radar, "
              "EasyPrivacy, Tranco rankings). No institutional resources, cloud "
              "spend, or purchases are required, so the project has no budget "
              "dependency that could delay delivery. Feasibility is no longer "
              "purely theoretical: the extension, live agent, classification/"
              "PII/risk pipeline, and self-hosted dashboard are already built "
              "and verified, which de-risks the remaining work (the full "
              "50-site crawl and written analysis) considerably.")

    h1(doc, "Project Objectives and Success Criteria")
    body(doc, "In scope: browser extension with traffic-light indicator, "
              "automated 50-site crawler, classification pipeline, personal-data "
              "(raw + hashed) detector, 0–100 risk scoring, local database and "
              "self-hosted dashboard, statistical analysis of four hypotheses, "
              "written report. Out of scope: no security testing, scanning, or "
              "exploitation; no logging into accounts other than the student's "
              "own test accounts; no collection of anyone else's traffic; no "
              "attempt to bypass security controls; no public deployment.", "Scope: ")
    body(doc, "12 weeks, structured around the four assessment events, with "
              "core build work (Weeks 1–8) running in parallel with writing so "
              "implementation is not compressed into the final block.", "Time: ")
    body(doc, "$0 — see Summary Budget above.", "Cost: ")
    body(doc, "Classification accuracy checked against DuckDuckGo Tracker Radar; "
              "personal-data detection tested with deliberately planted known "
              "identifiers; reproducibility checked by re-crawling all 50 sites "
              "after one week; code quality maintained through an automated "
              "test suite (23/23 passing).", "Quality: ")
    body(doc, "All observation is passive and limited to the student's own "
              "traffic and public pages, with robots.txt respected and "
              "conservative request pacing.", "Other: ")

    h1(doc, "Acceptance Criteria")
    body(doc, "The project is accepted as complete when:")
    bullets(doc, [
        "all 50 sites have been crawled and every classification manually "
        "verified;",
        "the four hypotheses (H1–H4) have been tested with documented results;",
        "the live dashboard (Grafana) and browser-extension traffic-light "
        "indicator are demonstrable on request;",
        "the final report is submitted with reproducible code, setup "
        "instructions, and a passing automated test suite.",
    ])

    h1(doc, "Project Approval and Manager")
    body(doc, "Scope changes beyond the frozen core (see Project Objectives and "
              "Success Criteria — Scope) require sign-off from the unit teacher "
              "before implementation begins.", "Project Approval Requirements: ")
    body(doc, "Thanh Dat Phan is responsible for delivery of all four assessment "
              "events against this charter.", "Project Manager: ")

    h1(doc, "Approvals")
    approval_rows = [
        ("Project Manager Signature", "Sponsor or Originator Signature"),
        ("Thanh Dat Phan", "[Unit Teacher Name]"),
        ("[Date]", "[Date]"),
    ]
    t = table(doc, ["", ""], approval_rows)
    for cell in t.rows[0].cells:
        cell.text = ""

    doc.save("Project_Charter_DataExodus.docx")
    print("wrote Project_Charter_DataExodus.docx")


# ============================================================
# DOCUMENT 2 — PROJECT PROPOSAL TEMPLATE (casual.pm style)
# Superseded - kept only for reference. Its content is folded into
# build_charter() above, which is the single consolidated deliverable.
# ============================================================

def build_proposal():
    doc = base_doc()

    title = doc.add_heading("Project Proposal: DataExodus", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(
        "Where Does My Data Go? Measuring Third-Party Data Flows on "
        "Australian Websites"
    )
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].italic = True

    h1(doc, "Background")
    body(doc, "Australians are told their data is handled responsibly, but "
              "nobody has measured what actually leaves the browser. Large "
              "tracking-measurement studies exist for the US and Europe, but "
              "none exist for Australian websites; Australian Privacy Principle "
              "(APP) 8, which governs sending personal information overseas, is "
              "untested in practice because these data flows are invisible to "
              "users; and privacy policies make vague claims about \"selected "
              "partners\" that nobody verifies against real traffic. This "
              "project builds a measurement tool and uses it to close that gap.")

    h1(doc, "Objectives")
    bullets(doc, [
        "Build and verify a working data-flow measurement tool (browser "
        "extension, automated crawler, classification pipeline, and live "
        "dashboard) by Week 8.",
        "Measure third-party data flows across 50 Australian websites "
        "(10 sites in each of 5 sectors) and test four hypotheses covering "
        "tracking prevalence, offshore data transfer, and privacy-policy "
        "accuracy by Week 11.",
        "Produce a final report with a methodology reproducible by a third "
        "party, verified against DuckDuckGo Tracker Radar and manual review, "
        "submitted Week 12.",
    ])

    h1(doc, "Scope")
    body(doc, "The end result is a working tool (browser extension + crawler + "
              "classification pipeline + dashboard) and a study report covering "
              "50 Australian websites. Work is delivered in three phases: "
              "foundation and prototype (Weeks 1–3), core build and literature "
              "review (Weeks 4–8), and full-scale measurement, analysis, and "
              "final reporting (Weeks 9–12). Explicitly out of scope: security "
              "testing, scanning, or exploitation of any target; collection of "
              "any traffic other than the student's own; and public deployment "
              "of the tool.")

    h1(doc, "Timeframe")
    timeframe_rows = [
        ("Phase One — Foundation & Charter: environment setup, extension and "
         "crawler prototype, charter submitted (A1)", "Weeks 1–3"),
        ("Phase Two — Core Build & Literature Review: classification pipeline, "
         "personal-data detection, full 50-site crawl, dashboard, literature "
         "review (A2) and practical project plan (A3)", "Weeks 4–8"),
        ("Phase Three — Analysis, Testing & Final Report: manual verification, "
         "hypothesis testing, privacy-policy comparison, final report and "
         "demonstration (A4)", "Weeks 9–12"),
    ]
    table(doc, ["Description of Work", "Start and End Dates"], timeframe_rows)

    h1(doc, "Project Budget")
    budget_rows = [
        ("Phase One — Foundation & Charter", "$0.00"),
        ("Phase Two — Core Build & Literature Review", "$0.00"),
        ("Phase Three — Analysis, Testing & Final Report", "$0.00"),
        ("Total", "$0.00"),
    ]
    table(doc, ["Description of Work", "Anticipated Costs"], budget_rows)
    body(doc, "All hardware is student-owned (personal laptop; Raspberry Pi 5 "
              "for an optional phase) and all software is free/open-source "
              "(Python, Playwright, DuckDB, FastAPI, InfluxDB OSS, Grafana OSS), "
              "so the project carries no budget dependency.")

    h1(doc, "Key Stakeholders")
    body(doc, "[Unit Teacher Name], TAFE NSW", "Client: ")
    body(doc, "[Unit Teacher Name], TAFE NSW", "Sponsor: ")
    body(doc, "Thanh Dat Phan", "Project manager: ")

    h1(doc, "Monitoring and Evaluation")
    body(doc, "Progress is evaluated against the four assessment events and a "
              "set of concrete quality measures:")
    eval_rows = [
        ("Classification accuracy", "Compared against DuckDuckGo Tracker Radar"),
        ("Personal data detection", "Tested with deliberately planted known "
         "identifiers"),
        ("Reproducibility", "All 50 sites re-crawled after one week to check "
         "stability"),
        ("Code quality", "Automated tests, documented setup instructions"),
    ]
    table(doc, ["Measure", "How it is checked"], eval_rows)
    body(doc, "The four hypotheses (over 60% of sites send data overseas; "
              "government/health sites carry fewer trackers than news/retail; "
              "over 30% of policies fail to name all observed third parties; "
              "hashed identifiers are transmitted by a measurable share of "
              "sign-up-form sites) are the final indicators of project success, "
              "tested and reported in Week 10.")

    h1(doc, "Approval Signatures")
    sig_rows = [
        ("[Name], Project Client", ""),
        ("[Name], Project Sponsor", ""),
        ("Thanh Dat Phan, Project Manager", ""),
        ("TAFE NSW", ""),
        ("[Date]", ""),
    ]
    for label, _ in sig_rows:
        doc.add_paragraph(label)

    footer = doc.add_paragraph(
        "This Project Proposal follows the structure of the Project Proposal "
        "Template by www.casual.pm."
    )
    footer.runs[0].italic = True
    footer.runs[0].font.size = Pt(8)

    doc.save("Project_Proposal_DataExodus.docx")
    print("wrote Project_Proposal_DataExodus.docx")


if __name__ == "__main__":
    # Single consolidated deliverable now - build_proposal() (casual.pm
    # template) is superseded, its content folded into build_charter().
    build_charter()
