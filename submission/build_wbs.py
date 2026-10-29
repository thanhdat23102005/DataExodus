"""
Render the DataExodus Work Breakdown Structure as a top-down tree
(graphviz): root project, 9 top-level phases, coloured by status as of
Week 8 (this Practical Project Plan submission). Leaf-level task detail
lives in the WBS table in the Word document, not in this diagram --
9 phase nodes stays readable; ~25 leaf nodes would not.
"""

import graphviz

STATUS_COLOR = {
    "done": "#c8e6c9",      # green
    "progress": "#ffe0b2",  # amber
    "planned": "#eceff1",   # grey
}
STATUS_BORDER = {
    "done": "#2e7d32",
    "progress": "#e65100",
    "planned": "#607d8b",
}

PHASES = [
    ("1.0", "Project Initiation\n& Planning", "done"),
    ("2.0", "Core Pipeline\nDevelopment", "done"),
    ("3.0", "Live Monitoring\nSystem", "done"),
    ("4.0", "Literature\nReview (A2)", "done"),
    ("5.0", "Reference Data\n& Config", "done"),
    ("6.0", "Practical Project\nPlan (A3)", "progress"),
    ("7.0", "Study Execution\n(50-site crawl)", "planned"),
    ("8.0", "Analysis &\nReporting", "planned"),
    ("9.0", "Final Report &\nDemonstration (A4)", "planned"),
]

g = graphviz.Digraph("wbs", format="png")
g.attr(rankdir="TB", bgcolor="white", fontname="Helvetica", fontsize="12",
       labelloc="t", label="DataExodus — Work Breakdown Structure (Level 1-2)",
       fontcolor="#1f3a5f", nodesep="0.35", ranksep="0.6")
g.attr("node", fontname="Helvetica", fontsize="10", shape="box",
       style="rounded,filled", margin="0.18,0.1")
g.attr("edge", color="#90a4ae", arrowsize="0.7")

g.node("root", "1.0 DataExodus\nProject", fillcolor="#bbdefb", color="#0d47a1",
       fontsize="11", style="rounded,filled,bold")

with g.subgraph() as s:
    s.attr(rank="same")
    for code, label, status in PHASES:
        s.node(code, f"{code}\n{label}", fillcolor=STATUS_COLOR[status],
               color=STATUS_BORDER[status])
        g.edge("root", code)

# legend
with g.subgraph(name="cluster_legend") as lg:
    lg.attr(label="Status", fontsize="9", fontcolor="#37474f", style="rounded",
             color="#cfd8dc")
    lg.node("lg_done", "Complete", fillcolor=STATUS_COLOR["done"],
             color=STATUS_BORDER["done"], fontsize="8", shape="box")
    lg.node("lg_prog", "In progress", fillcolor=STATUS_COLOR["progress"],
             color=STATUS_BORDER["progress"], fontsize="8", shape="box")
    lg.node("lg_plan", "Planned", fillcolor=STATUS_COLOR["planned"],
             color=STATUS_BORDER["planned"], fontsize="8", shape="box")

g.render("assets/wbs_tree", cleanup=True)
print("wrote assets/wbs_tree.png")
