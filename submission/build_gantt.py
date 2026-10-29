"""
Render the DataExodus 12-week Gantt chart (matplotlib horizontal bars).
Tasks are the leaf items of the WBS, grouped and colour-coded by the same
9 phases as build_wbs.py. Status as of Week 8 (this Practical Project Plan
submission, dated 18/09/2026): Weeks 1-7 work is complete, Week 8 is in
progress, Weeks 9-12 are planned. A dashed "Today" line marks the Week 8
mid-point.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

PHASE_COLOR = {
    1: "#1f3a5f", 2: "#0d47a1", 3: "#00695c", 4: "#6a1b9a",
    5: "#2e7d32", 6: "#e65100", 7: "#b3261e", 8: "#5d4037", 9: "#37474f",
}

# (wbs id, label, phase, start_week, duration_weeks, status)
TASKS = [
    ("1.1", "Topic selection & scoping", 1, 1, 1, "done"),
    ("1.2", "Project Charter (A1)", 1, 1, 3, "done"),
    ("1.3", "Environment setup (RHEL VM, venv)", 1, 2, 2, "done"),
    ("2.1", "Site list & sector config", 2, 2, 1, "done"),
    ("2.2", "Web crawler (Playwright)", 2, 2, 2, "done"),
    ("2.3", "Classification engine", 2, 3, 2, "done"),
    ("2.4", "PII detector (raw + hashed)", 2, 4, 1, "done"),
    ("2.5", "Risk scoring engine (0-100)", 2, 4, 2, "done"),
    ("2.6", "Automated test suite", 2, 3, 3, "done"),
    ("3.1", "Chrome extension (Manifest V3)", 3, 4, 2, "done"),
    ("3.2", "FastAPI local agent", 3, 5, 1, "done"),
    ("3.3", "InfluxDB + Grafana dashboard", 3, 5, 2, "done"),
    ("4.1", "Source research & synthesis", 4, 5, 2, "done"),
    ("4.2", "Literature Review submission (A2)", 4, 6, 1, "done"),
    ("5.1", "Tracker/blocklist reference data", 5, 6, 1, "done"),
    ("5.2", "MaxMind GeoLite2 integration", 5, 8, 1, "done"),
    ("5.3", "Personal identity index config", 5, 8, 1, "done"),
    ("6.1", "WBS / schedule / cost / risk docs", 6, 8, 1, "progress"),
    ("6.2", "Practical Project Plan submission (A3)", 6, 8, 1, "progress"),
    ("7.1", "Full 50-site crawl", 7, 9, 1, "planned"),
    ("7.2", "Manual verification of classifications", 7, 9, 2, "planned"),
    ("8.1", "Hypothesis testing (H1-H4)", 8, 10, 1, "planned"),
    ("8.2", "Charts & visualisations", 8, 10, 2, "planned"),
    ("8.3", "Optional ML extension", 8, 10, 1, "planned"),
    ("9.1", "Draft & refine final report", 9, 11, 1, "planned"),
    ("9.2", "Rehearse live demo", 9, 11, 2, "planned"),
    ("9.3", "Final submission & demo (A4)", 9, 12, 1, "planned"),
]

fig, ax = plt.subplots(figsize=(11, 9))

for i, (wbs, label, phase, start, dur, status) in enumerate(reversed(TASKS)):
    y = i
    color = PHASE_COLOR[phase]
    if status == "done":
        ax.barh(y, dur, left=start - 1, height=0.6, color=color, alpha=0.9)
    elif status == "progress":
        ax.barh(y, dur, left=start - 1, height=0.6, color=color, alpha=0.9,
                hatch="//", edgecolor="white")
    else:
        ax.barh(y, dur, left=start - 1, height=0.6, color=color, alpha=0.25,
                edgecolor=color, linewidth=1.2)
    ax.text(start - 1 - 0.15, y, f"{wbs}", ha="right", va="center",
            fontsize=7.5, color="#37474f", fontweight="bold")

ax.set_yticks(range(len(TASKS)))
ax.set_yticklabels([t[1] for t in reversed(TASKS)], fontsize=8)
ax.set_xticks(range(0, 13))
ax.set_xticklabels([str(w) for w in range(0, 13)], fontsize=9)
ax.set_xlim(-2.6, 12)
ax.set_xlabel("Week", fontsize=10)
ax.set_title("DataExodus — Project Schedule (Gantt Chart)\n"
              "As at Week 8 / 18-09-2026 — Assessment A3",
              fontsize=13, color="#1f3a5f", fontweight="bold")
ax.grid(axis="x", color="#e0e0e0", linewidth=0.8, zorder=0)
ax.set_axisbelow(True)

# "Today" marker at end of week 8
ax.axvline(8, color="#b3261e", linestyle="--", linewidth=1.4)
ax.text(8.1, len(TASKS) - 0.3, "Today\n(Wk 8)", color="#b3261e", fontsize=8,
        fontweight="bold", va="top")

legend_elems = [
    Patch(facecolor="#607d8b", alpha=0.9, label="Complete"),
    Patch(facecolor="#607d8b", alpha=0.9, hatch="//", edgecolor="white",
          label="In progress"),
    Patch(facecolor="#607d8b", alpha=0.25, edgecolor="#607d8b", label="Planned"),
]
ax.legend(handles=legend_elems, loc="lower right", fontsize=8, frameon=True)

for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)

plt.tight_layout()
plt.savefig("assets/gantt_chart.png", dpi=200)
print("wrote assets/gantt_chart.png")
