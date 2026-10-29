"""
Render the DataExodus risk register (R1-R7, from the Project Charter) as a
3x3 probability/impact matrix (matplotlib). Reuses the exact risk
statements and Probability/Impact ratings from Project_Charter_DataExodus
so the two documents never disagree.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LEVELS = {"Low": 0, "Medium": 1, "High": 2}

# (id, probability, impact, status)  -- must match the charter's risk table
RISKS = [
    ("R1", "High", "High", "Open"),
    ("R2", "High", "Medium", "Open"),
    ("R3", "Medium", "Medium", "Mitigated"),
    ("R4", "High", "Low", "Open"),
    ("R5", "Medium", "Medium", "Open"),
    ("R6", "Low", "High", "Mitigated"),
    ("R7", "Low", "High", "Open"),
]

CELL_COLOR = {
    (0, 0): "#c8e6c9", (0, 1): "#dcedc8", (0, 2): "#fff9c4",
    (1, 0): "#dcedc8", (1, 1): "#fff9c4", (1, 2): "#ffe0b2",
    (2, 0): "#fff9c4", (2, 1): "#ffe0b2", (2, 2): "#ffcdd2",
}

fig, ax = plt.subplots(figsize=(6.5, 6))

for (impact_i, prob_i), color in CELL_COLOR.items():
    ax.add_patch(plt.Rectangle((impact_i, prob_i), 1, 1, facecolor=color,
                                edgecolor="white", linewidth=2))

# jitter overlapping points slightly so labels don't collide
seen = {}
for rid, prob, impact, status in RISKS:
    px, py = LEVELS[impact], LEVELS[prob]
    key = (px, py)
    n = seen.get(key, 0)
    seen[key] = n + 1
    dx = 0.5 + (n * 0.0)
    dy = 0.68 - (n * 0.22)
    marker = "o" if status == "Open" else "s"
    edge = "#b3261e" if status == "Open" else "#2e7d32"
    ax.scatter(px + dx, py + dy, s=380, facecolor="white", edgecolor=edge,
               linewidth=2, marker=marker, zorder=3)
    ax.text(px + dx, py + dy, rid, ha="center", va="center", fontsize=9,
            fontweight="bold", color=edge, zorder=4)

ax.set_xlim(0, 3)
ax.set_ylim(0, 3)
ax.set_xticks([0.5, 1.5, 2.5])
ax.set_xticklabels(["Low", "Medium", "High"], fontsize=10)
ax.set_yticks([0.5, 1.5, 2.5])
ax.set_yticklabels(["Low", "Medium", "High"], fontsize=10)
ax.set_xlabel("Impact", fontsize=11, color="#1f3a5f", fontweight="bold")
ax.set_ylabel("Probability", fontsize=11, color="#1f3a5f", fontweight="bold")
ax.set_title("DataExodus — Risk Probability / Impact Matrix",
              fontsize=12, color="#1f3a5f", fontweight="bold")

from matplotlib.lines import Line2D
legend_elems = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
           markeredgecolor="#b3261e", markeredgewidth=2, markersize=12,
           label="Open"),
    Line2D([0], [0], marker="s", color="w", markerfacecolor="white",
           markeredgecolor="#2e7d32", markeredgewidth=2, markersize=11,
           label="Mitigated"),
]
ax.legend(handles=legend_elems, loc="upper left", fontsize=9, frameon=True)

for spine in ax.spines.values():
    spine.set_visible(False)
ax.tick_params(length=0)

plt.tight_layout()
plt.savefig("assets/risk_matrix.png", dpi=200)
print("wrote assets/risk_matrix.png")
