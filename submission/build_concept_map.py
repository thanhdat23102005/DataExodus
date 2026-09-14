"""
Recreate the DataExodus concept map at high resolution.

The source (DataExodus_Concept_Map.pptx) stores it as native PowerPoint
shapes relying on PowerPoint's auto-shrink-to-fit text, and its only
embedded bitmap is a 256x144 preview thumbnail - too low-res for a report
and the absolute coordinates don't translate cleanly to a renderer that
doesn't auto-shrink text. This rebuilds the same content and regions on an
explicit non-overlapping grid (matplotlib GridSpec) so every label is
guaranteed to stay inside its own box.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.gridspec import GridSpecFromSubplotSpec

COLORS = {
    "why": "#2e7d32",
    "what": "#6a1b9a",
    "who": "#1f3a5f",
    "benefits": "#c65a00",
    "how": "#b3261e",
    "hyp": "#00695c",
    "map": "#0d47a1",
    "footer": "#37474f",
}


def panel(fig, spec, color, alpha=0.10):
    ax = fig.add_subplot(spec)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch(
        (0.01, 0.01), 0.98, 0.98,
        boxstyle="round,pad=0.01,rounding_size=0.04",
        linewidth=1.3, edgecolor=color, facecolor=color, alpha=alpha,
        transform=ax.transAxes, clip_on=False,
    ))
    return ax


def title_body(fig, spec, heading, body, color, heading_size=12, body_size=9,
               alpha=0.10, align="center"):
    ax = panel(fig, spec, color, alpha)
    ha = align
    x = 0.5 if align == "center" else 0.06
    ax.text(x, 0.90, heading, color=color, fontsize=heading_size, weight="bold",
            ha=ha, va="top", transform=ax.transAxes, wrap=True)
    ax.text(x, 0.72, body, color=color, fontsize=body_size,
            ha=ha, va="top", transform=ax.transAxes, wrap=True, linespacing=1.6)
    return ax


def main():
    fig = plt.figure(figsize=(14, 9), dpi=200)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(
        nrows=13, ncols=6,
        left=0.02, right=0.98, top=0.97, bottom=0.02,
        hspace=1.0, wspace=0.35,
    )

    # Title
    ax = fig.add_subplot(gs[0, :])
    ax.axis("off")
    ax.text(0.5, 0.7, "DATAEXODUS — CONCEPT MAP", fontsize=24, weight="bold",
            color=COLORS["map"], ha="center", va="center", transform=ax.transAxes)
    ax.text(0.5, 0.05, "Where Does My Data Go? Measuring Third-Party Data "
            "Flows on Australian Websites", fontsize=12.5, color=COLORS["map"],
            ha="center", va="center", transform=ax.transAxes)

    # Assessment events banner
    ax = panel(fig, gs[1, 1:5], COLORS["map"], alpha=0.10)
    ax.text(0.5, 0.5, "ASSESSMENT EVENTS:  A1 Charter (W3)  •  A2 Literature "
            "Review (W6)  •  A3 Practical Plan (W8)  •  A4 Final Demo (W12)",
            fontsize=11.5, weight="bold", color=COLORS["map"], ha="center",
            va="center", transform=ax.transAxes)

    # Row 2: WHY | DataExodus centre | WHAT
    title_body(fig, gs[2:5, 0:2], "WHY",
               "•  No large measurement study of\n    Australian websites\n"
               "•  APP 8 overseas data flows are\n    rarely visible\n"
               "•  Privacy policies are rarely\n    checked against real behaviour",
               COLORS["why"], heading_size=14, body_size=9.5, alpha=0.08, align="left")

    ax = panel(fig, gs[2:5, 2:4], COLORS["who"], alpha=0.13)
    ax.text(0.5, 0.72, "DataExodus", fontsize=15, weight="bold",
            color=COLORS["who"], ha="center", va="center", transform=ax.transAxes)
    ax.text(0.5, 0.42, "Build a tool to make hidden third-party\nconnections "
            "visible, then measure 50\nAustralian websites — and prove that\n"
            "hashing is not anonymisation.",
            fontsize=10, color=COLORS["who"], ha="center", va="center",
            transform=ax.transAxes, linespacing=1.6)

    title_body(fig, gs[2:5, 4:6], "WHAT",
               "A TOOL\nChrome extension + crawler +\nclassification pipeline + "
               "live risk-\nscored dashboard (Grafana/InfluxDB)\n\n"
               "A STUDY\n50 Australian websites • 4 hypotheses\nreport + recommendations",
               COLORS["what"], heading_size=14, body_size=9, alpha=0.08)

    # Row 3: WHO/WHERE | HOW steps | WHO BENEFITS
    title_body(fig, gs[5:9, 0:2], "WHO / WHERE",
               "WHO: Student as researcher,\ndeveloper, analyst and writer.\n\n"
               "WHERE: Student-owned laptop +\noptional Raspberry Pi 5.\n\n"
               "TARGET: Public Australian websites;\nall data stays local.",
               COLORS["who"], heading_size=13, body_size=9, alpha=0.06, align="left")

    how_spec = gs[5:9, 2:4]
    how_gs = GridSpecFromSubplotSpec(3, 3, subplot_spec=how_spec,
                                      hspace=0.5, wspace=0.25)
    ax = fig.add_subplot(how_gs[0, :])
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.01, 0.05), 0.98, 0.9,
                 boxstyle="round,pad=0.01,rounding_size=0.06",
                 linewidth=1.3, edgecolor=COLORS["how"], facecolor=COLORS["how"],
                 alpha=0.12, transform=ax.transAxes, clip_on=False))
    ax.text(0.5, 0.5, "HOW — RESEARCH & BUILD PROCESS", fontsize=11.5,
            weight="bold", color=COLORS["how"], ha="center", va="center",
            transform=ax.transAxes)

    steps = [
        "1. CAPTURE\nExtension + Playwright",
        "2. CLASSIFY\nTracker • owner • country",
        "3. DETECT\nPII, raw + hashed",
        "4. STORE\nDuckDB / InfluxDB",
        "5. VERIFY\nManual checks + tests",
        "6. ANALYSE\nStats + Grafana dashboard",
    ]
    for i, step in enumerate(steps):
        r, c = 1 + i // 3, i % 3
        ax = fig.add_subplot(how_gs[r, c])
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.03, 0.05), 0.94, 0.9,
                     boxstyle="round,pad=0.01,rounding_size=0.08",
                     linewidth=1.0, edgecolor=COLORS["how"], facecolor=COLORS["how"],
                     alpha=0.10, transform=ax.transAxes, clip_on=False))
        ax.text(0.5, 0.5, step, fontsize=7.6, color=COLORS["how"],
                ha="center", va="center", transform=ax.transAxes, linespacing=1.5)

    title_body(fig, gs[5:9, 4:6], "WHO BENEFITS",
               "Users → visibility into their\nown data\n\n"
               "Organisations → an audit\nmethod\n\n"
               "Regulators → baseline\nevidence about APP 8 in\npractice",
               COLORS["benefits"], heading_size=13, body_size=9, alpha=0.08)

    # Row 4: hypotheses banner
    title_body(fig, gs[9:11, 1:5], "4 HYPOTHESES (to be tested)",
               "H1: over 60% of sites send data overseas          "
               "H2: govt/health sites track less than news/retail\n"
               "H3: over 30% of policies omit an observed third party     "
               "H4: hashed identifiers occur on sign-up sites",
               COLORS["hyp"], heading_size=12, body_size=9.3, alpha=0.10)

    # Footer row
    ax = fig.add_subplot(gs[11, 0:3])
    ax.axis("off")
    ax.text(0.02, 0.5, "SAMPLE: 50 sites — 10 each: News • Retail • Health • "
            "Government • Finance", fontsize=9.5, weight="bold",
            color=COLORS["footer"], ha="left", va="center", transform=ax.transAxes)
    ax = fig.add_subplot(gs[11, 3:6])
    ax.axis("off")
    ax.text(0.98, 0.5, "OUTCOME: Evidence about third-party data flows + APP 8",
            fontsize=9.5, weight="bold", color=COLORS["footer"], ha="right",
            va="center", transform=ax.transAxes)

    ax = fig.add_subplot(gs[12, :])
    ax.axis("off")
    ax.text(0.5, 0.5, "Scope: passive observation only  •  own traffic/test "
            "identifiers  •  no exploitation  •  no other people's traffic",
            fontsize=9, color=COLORS["footer"], ha="center", va="center",
            transform=ax.transAxes, style="italic")

    fig.savefig("assets/concept_map.png", bbox_inches="tight", pad_inches=0.2,
                facecolor="white")
    print("wrote assets/concept_map.png")


if __name__ == "__main__":
    main()
