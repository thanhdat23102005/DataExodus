#!/usr/bin/env python3
"""
DataExodus — Analysis & Reporting
Generates statistics, tests hypotheses, and produces charts.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_data(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path)


def hypothesis_tests(conn: duckdb.DuckDBPyConnection):
    """Test H1–H4 and print results."""
    print("\n" + "=" * 60)
    print("HYPOTHESIS TESTS")
    print("=" * 60)

    # H1: Government sites have fewer trackers than news sites
    h1 = conn.execute("""
        SELECT sector, AVG(CAST(is_tracker AS DOUBLE)) as tracker_rate
        FROM requests GROUP BY sector
    """).fetchdf()
    print("\nH1 — Tracker rate by sector:")
    print(h1.to_string(index=False))

    # H2: Health sites transmit more PII
    h2 = conn.execute("""
        SELECT sector, AVG(CAST(pii_detected AS DOUBLE)) as pii_rate
        FROM requests GROUP BY sector
    """).fetchdf()
    print("\nH2 — PII transmission rate by sector:")
    print(h2.to_string(index=False))

    # H3: Offshore (non-adequate) destinations are common
    h3 = conn.execute("""
        SELECT
            COUNT(DISTINCT domain) as total_domains,
            COUNT(DISTINCT CASE WHEN country_adequacy=FALSE THEN domain END) as offshore_domains
        FROM requests WHERE is_tracker=TRUE
    """).fetchone()
    print(f"\nH3 — Offshore tracker domains: {h3[1]} / {h3[0]} ({h3[1]/max(h3[0],1)*100:.1f}%)")

    # H4: Risk score correlates with sector
    h4 = conn.execute("""
        SELECT sector, AVG(risk_score) as mean_risk, MAX(risk_score) as max_risk
        FROM requests GROUP BY sector ORDER BY mean_risk DESC
    """).fetchdf()
    print("\nH4 — Mean risk score by sector:")
    print(h4.to_string(index=False))


def generate_charts(conn: duckdb.DuckDBPyConnection, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Chart 1: Sankey — You → Site → Owner
    sankey_data = conn.execute("""
        SELECT site, owner, COUNT(*) as n
        FROM requests
        WHERE is_tracker=TRUE AND owner IS NOT NULL
        GROUP BY site, owner
        ORDER BY n DESC
        LIMIT 100
    """).fetchdf()

    if not sankey_data.empty:
        sites = list(sankey_data["site"].unique())
        owners = list(sankey_data["owner"].unique())
        labels = ["You"] + sites + owners
        source = [0] * len(sites) + [1 + sites.index(s) for s in sankey_data["site"]]
        target = [1 + sites.index(s) for s in sankey_data["site"]] + [1 + len(sites) + owners.index(o) for o in sankey_data["owner"]]
        value = list(sankey_data["n"]) * 2  # simplified
        # Actually build properly:
        source, target, value = [], [], []
        for _, row in sankey_data.iterrows():
            s_idx = 1 + sites.index(row["site"])
            o_idx = 1 + len(sites) + owners.index(row["owner"])
            source.extend([0, s_idx])
            target.extend([s_idx, o_idx])
            value.extend([row["n"], row["n"]])

        fig = go.Figure(data=[go.Sankey(
            node=dict(label=labels, pad=15, thickness=20),
            link=dict(source=source, target=target, value=value)
        )])
        fig.update_layout(title_text="Data Flow: You → Site → Tracker Owner", font_size=10)
        fig.write_image(str(out_dir / "sankey.png"), width=1200, height=800, scale=2)
        print(f"[chart] Saved sankey.png")

    # Chart 2: Bar — Trackers per sector
    sector_data = conn.execute("""
        SELECT sector,
            COUNT(*) as total,
            SUM(CAST(is_tracker AS INTEGER)) as trackers
        FROM requests GROUP BY sector
    """).fetchdf()
    fig = go.Figure(data=[
        go.Bar(name="Total requests", x=sector_data["sector"], y=sector_data["total"]),
        go.Bar(name="Tracker requests", x=sector_data["sector"], y=sector_data["trackers"]),
    ])
    fig.update_layout(barmode="group", title="Requests vs Trackers by Sector")
    fig.write_image(str(out_dir / "sector_trackers.png"), width=900, height=500, scale=2)
    print(f"[chart] Saved sector_trackers.png")

    # Chart 3: Map — Countries receiving data
    country_data = conn.execute("""
        SELECT country, COUNT(*) as n
        FROM requests WHERE country IS NOT NULL
        GROUP BY country ORDER BY n DESC LIMIT 20
    """).fetchdf()
    fig = go.Figure(data=go.Choropleth(
        locations=country_data["country"],
        z=country_data["n"],
        locationmode="ISO-3",
        colorscale="Reds",
        colorbar_title="Requests",
    ))
    fig.update_layout(title="Countries Receiving Data")
    fig.write_image(str(out_dir / "world_map.png"), width=1000, height=600, scale=2)
    print(f"[chart] Saved world_map.png")

    # Chart 4: Top owners
    owner_data = conn.execute("""
        SELECT owner, COUNT(*) as n FROM requests
        WHERE owner IS NOT NULL GROUP BY owner ORDER BY n DESC LIMIT 10
    """).fetchdf()
    fig = go.Figure(data=[go.Pie(labels=owner_data["owner"], values=owner_data["n"], hole=0.4)])
    fig.update_layout(title="Top 10 Data Recipients")
    fig.write_image(str(out_dir / "top_owners.png"), width=800, height=600, scale=2)
    print(f"[chart] Saved top_owners.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/dataexodus.duckdb")
    parser.add_argument("--out", default="figures")
    args = parser.parse_args()

    conn = load_data(args.db)
    hypothesis_tests(conn)
    generate_charts(conn, Path(args.out))
    conn.close()
    print("\n[report] Done.")


if __name__ == "__main__":
    main()
