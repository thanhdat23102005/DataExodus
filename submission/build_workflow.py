"""
Render the actual DataExodus system architecture (as built) with graphviz:
two pipelines - the batch Study crawl and the Live monitoring agent -
sharing the same classification/PII/risk-scoring core.
"""

import graphviz

g = graphviz.Digraph("workflow", format="png")
g.attr(rankdir="LR", bgcolor="white", fontname="Helvetica",
       fontsize="11", labelloc="t", label="DataExodus — System Architecture (as built)",
       fontcolor="#1f3a5f")
g.attr("node", fontname="Helvetica", fontsize="10", shape="box",
       style="rounded,filled", margin="0.15,0.08")
g.attr("edge", fontname="Helvetica", fontsize="9", color="#607d8b",
       fontcolor="#37474f")

# ---- Study mode (batch) ----
with g.subgraph(name="cluster_study") as c:
    c.attr(label="STUDY MODE — batch crawl of 50 sites", fontsize="11",
           fontcolor="#0d47a1", style="rounded", color="#0d47a1", bgcolor="#e3ecfa")
    c.node("sites", "data/sites.yaml\n50 Australian sites", fillcolor="#bbdefb", color="#0d47a1")
    c.node("crawler", "crawler/crawl.py\nPlaywright headless browser", fillcolor="#bbdefb", color="#0d47a1")
    c.node("raw", "data/raw/*.json\nraw captured requests", fillcolor="#bbdefb", color="#0d47a1")
    c.node("process", "pipeline/process.py", fillcolor="#90caf9", color="#0d47a1")
    c.node("duckdb", "DuckDB\ndata/dataexodus.duckdb", fillcolor="#bbdefb", color="#0d47a1")
    c.node("report", "analysis/report.py\nanalysis/export_sheet.py", fillcolor="#bbdefb", color="#0d47a1")
    c.node("outputs", "report.md • per_site.csv\nper_site_report.xlsx (+chart)", fillcolor="#e3ecfa", color="#0d47a1")
    c.edge("sites", "crawler")
    c.edge("crawler", "raw")
    c.edge("raw", "process")
    c.edge("process", "duckdb")
    c.edge("duckdb", "report")
    c.edge("report", "outputs")

# ---- Live mode ----
with g.subgraph(name="cluster_live") as c:
    c.attr(label="LIVE MODE — real-time sensor", fontsize="11",
           fontcolor="#b3261e", style="rounded", color="#b3261e", bgcolor="#fbe9e7")
    c.node("browser", "Student's browsing\n(Chrome)", fillcolor="#ffccbc", color="#b3261e")
    c.node("extension", "extension/\nManifest V3 sensor\n(webRequest capture)", fillcolor="#ffab91", color="#b3261e")
    c.node("agent", "pipeline/agent.py\nFastAPI local agent\n127.0.0.1:8000", fillcolor="#ff8a65", color="#b3261e")
    c.node("badge", "Toolbar badge + popup\ngreen / amber / red", fillcolor="#ffccbc", color="#b3261e")
    c.node("influx", "InfluxDB\nlive_requests bucket", fillcolor="#ffccbc", color="#b3261e")
    c.node("grafana", "Grafana dashboard\ndataexodus-live", fillcolor="#ffccbc", color="#b3261e")

    c.edge("browser", "extension", label="outbound\nrequests")
    c.edge("extension", "agent", label="batched\nPOST /ingest")
    c.edge("agent", "badge", label="GET /site/{domain}")
    c.edge("agent", "influx", label="write point")
    c.edge("influx", "grafana", label="Flux query")

# ---- Shared core ----
g.node("classify", "pipeline/classify.py\ntracker • owner • country",
       fillcolor="#c8e6c9", color="#2e7d32", shape="box3d")
g.node("pii", "pipeline/pii.py\nraw + hashed PII match",
       fillcolor="#c8e6c9", color="#2e7d32", shape="box3d")
g.node("risk", "pipeline/risk.py\n0-100 score, green/amber/red",
       fillcolor="#c8e6c9", color="#2e7d32", shape="box3d")

g.edge("process", "classify", style="dashed", color="#2e7d32", constraint="false")
g.edge("process", "pii", style="dashed", color="#2e7d32", constraint="false")
g.edge("process", "risk", style="dashed", color="#2e7d32", constraint="false")
g.edge("agent", "classify", style="dashed", color="#2e7d32", constraint="false")
g.edge("agent", "pii", style="dashed", color="#2e7d32", constraint="false")
g.edge("agent", "risk", style="dashed", color="#2e7d32", constraint="false")

g.render("assets/workflow", cleanup=True)
print("wrote assets/workflow.png")
