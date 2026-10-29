"""Score the frozen site list with the DataExodus Box link checker (product evaluation).

Every entry in data/sites.yaml is a legitimate organisation's home page, so a
run shows how the 0-100 score behaves on ordinary websites: how many are rated
"Dangerous" (false alarms), "Be careful" (usually heavy tracking or advertising)
or "Low risk", and which rules drive the scores. It complements the crawl study,
which measures the same sites' trackers and destinations in more detail.

  python -m analysis.score_sites --out reports/site-scores

Needs the sandbox service (protection/api.py) at --api, default
http://127.0.0.1:8010 (on the Pi, or through the SSH tunnel), and its token in
DATAEXODUS_GUARD_TOKEN. Screenshots are not kept. Each site is opened once.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

LEVELS = ("low", "caution", "danger", "unknown")
LABELS = {"low": "Low risk", "caution": "Be careful", "danger": "Dangerous", "unknown": "Not assessed"}


def load_sites(path: str | Path, sector: str | None = None) -> list[tuple[str, str]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [(name, url) for name, urls in data["sectors"].items() if not sector or name == sector for url in urls]


def row(sector: str, url: str, result: dict, seconds: float) -> dict:
    a = result.get("assessment") or {}
    countries = sorted({c for c in (result.get("third_party_countries") or {}).values() if c})
    owners = list(dict.fromkeys(t.get("owner") or t.get("domain") for t in result.get("trackers") or []))
    return {
        "sector": sector, "url": url, "ok": bool(result.get("ok")), "error": result.get("error") or "",
        "level": a.get("level") or "unknown", "score": a.get("score"),
        "reasons": [r.get("code") for r in a.get("reasons") or []],
        "scam_phrases": list(result.get("scam_phrases") or []),
        "trackers": len(result.get("trackers") or []), "tracker_owners": owners[:8],
        "third_parties": len(result.get("third_parties") or []), "countries": countries,
        "offshore": any(c != "AU" for c in countries), "hops": max(0, len(result.get("redirect_chain") or []) - 1),
        "final_url": result.get("final_url") or "", "refused_internal": len(result.get("refused_internal") or []),
        "seconds": round(seconds, 1),
    }


def run(sites: list[tuple[str, str]], check: Callable[[str], dict], pause: float = 1.0,
        progress: Callable[[str], None] = print) -> list[dict]:
    rows = []
    for i, (sector, url) in enumerate(sites, 1):
        started = time.time()
        try:
            result = check(url)
        except Exception as exc:  # noqa: BLE001 - one unreachable site must not stop the run
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
        rows.append(row(sector, url, result, time.time() - started))
        last = rows[-1]
        progress(f"[{i}/{len(sites)}] {sector:11} {last['level']:8} {last['score']!s:>4}  {url}")
        if pause and i < len(sites):
            time.sleep(pause)
    return rows


def summarise(rows: list[dict]) -> dict:
    assessed = [r for r in rows if r["score"] is not None]
    by_sector = {}
    for sector in dict.fromkeys(r["sector"] for r in rows):
        mine = [r for r in rows if r["sector"] == sector]
        scores = [r["score"] for r in mine if r["score"] is not None]
        by_sector[sector] = {"sites": len(mine), **{lv: sum(r["level"] == lv for r in mine) for lv in LEVELS},
                             "median_score": statistics.median(scores) if scores else None,
                             "mean_trackers": round(statistics.mean(r["trackers"] for r in mine), 1) if mine else None,
                             "offshore_sites": sum(r["offshore"] for r in mine)}
    reasons = Counter(code for r in assessed for code in set(r["reasons"]))
    countries = Counter(c for r in assessed for c in r["countries"] if c != "AU")
    owners = Counter(o for r in assessed for o in r["tracker_owners"])
    return {
        "sites": len(rows), "assessed": len(assessed),
        "levels": {lv: sum(r["level"] == lv for r in rows) for lv in LEVELS},
        "false_alarms": [{"url": r["url"], "score": r["score"], "reasons": r["reasons"]} for r in rows if r["level"] == "danger"],
        "median_score": statistics.median([r["score"] for r in assessed]) if assessed else None,
        "by_sector": by_sector, "reason_sites": reasons.most_common(),
        "offshore_sites": sum(r["offshore"] for r in assessed), "offshore_countries": countries.most_common(10),
        "tracker_owners": owners.most_common(10),
        "not_assessed": [{"url": r["url"], "error": r["error"]} for r in rows if r["score"] is None],
    }


def render(summary: dict, protocol: dict) -> str:
    s = summary
    pct = lambda n, d: f"{100 * n / d:.0f}%" if d else "n/a"  # noqa: E731
    lines = [
        "# Link checker on the frozen site list", "",
        f"Run {protocol['finished']} on `{protocol.get('sandbox_host') or 'the sandbox service'}`; "
        f"{s['assessed']} of {s['sites']} sites assessed. DNS: {', '.join(protocol.get('resolvers') or []) or 'not recorded'}.",
        "Every site is a legitimate organisation's home page: a \"Dangerous\" rating is a false alarm. "
        "\"Be careful\" on these sites reflects tracking and advertising signals, not malicious behaviour.", "",
        "| Rating | Sites | Share |", "| --- | ---: | ---: |",
        *[f"| {LABELS[lv]} | {s['levels'][lv]} | {pct(s['levels'][lv], s['sites'])} |" for lv in LEVELS],
        "", f"Median score: {s['median_score']}. False alarms (Dangerous): **{len(s['false_alarms'])}**.", "",
        "## By sector", "", "| Sector | Sites | Low | Careful | Dangerous | Not assessed | Median score | Mean trackers | Sites with servers outside AU |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        *[f"| {name} | {v['sites']} | {v['low']} | {v['caution']} | {v['danger']} | {v['unknown']} | {v['median_score']} | "
          f"{v['mean_trackers']} | {v['offshore_sites']} |" for name, v in s["by_sector"].items()],
        "", "## What drove the scores (sites with each rule)", "",
        *[f"- `{code}`: {n}" for code, n in s["reason_sites"]],
        "", f"## Servers outside Australia: {s['offshore_sites']} of {s['assessed']} sites", "",
        *[f"- {country}: {n} sites" for country, n in s["offshore_countries"]],
        "", "## Most common tracker owners", "", *[f"- {owner}: {n} sites" for owner, n in s["tracker_owners"]],
    ]
    if s["false_alarms"]:
        lines += ["", "## False alarms", "", *[f"- {f['url']} ({f['score']}): {', '.join(f['reasons'])}" for f in s["false_alarms"]]]
    if s["not_assessed"]:
        lines += ["", "## Not assessed", "", *[f"- {n['url']}: {n['error']}" for n in s["not_assessed"]]]
    lines += ["", "## Limits", "",
              "- One anonymous visit per site, home page only, no consent banner interaction.",
              "- Country is a GeoLite2 estimate of the server address, not where data is stored (APP 8 needs more than this).",
              "- Tracker labels come from EasyPrivacy and Tracker Radar; unknown stays unknown.",
              "- This measures false alarms on legitimate sites only. Detection of real scams needs a labelled set of "
              "phishing links, which this run does not include.", ""]
    return "\n".join(lines)


def resolvers(path: Path = Path("/etc/resolv.conf")) -> list[str]:
    try:
        return [l.split()[1] for l in path.read_text(encoding="utf-8").splitlines()
                if l.startswith("nameserver") and len(l.split()) > 1]
    except OSError:
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sites", default="data/sites.yaml")
    parser.add_argument("--sector", default=None)
    parser.add_argument("--api", default=os.getenv("DATAEXODUS_API", "http://127.0.0.1:8010"))
    parser.add_argument("--out", type=Path, default=Path("reports/site-scores"))
    parser.add_argument("--pause", type=float, default=1.0, help="Seconds between sites")
    args = parser.parse_args()
    import requests

    token = os.getenv("DATAEXODUS_GUARD_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("Set DATAEXODUS_GUARD_TOKEN to the sandbox service token")
    session = requests.Session()
    session.trust_env = False  # loopback service: never through a proxy
    headers = {"Authorization": "Bearer " + token}
    host = session.get(args.api + "/health", headers=headers, timeout=10).json().get("sandbox_host")

    def check(url: str) -> dict:
        response = session.post(args.api + "/sandbox/preview", json={"url": url}, headers=headers, timeout=180)
        response.raise_for_status()
        return response.json()

    sites = load_sites(args.sites, args.sector)
    rows = run(sites, check, args.pause)
    summary = summarise(rows)
    protocol = {"finished": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "sandbox_host": host,
                "resolvers": resolvers(), "sites_file": args.sites, "sector": args.sector or "all"}
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "scores.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ";".join(v) if isinstance(v, list) else v for k, v in r.items()})
    (args.out / "results.json").write_text(json.dumps({"protocol": protocol, "summary": summary, "sites": rows},
                                                      indent=2), encoding="utf-8")
    (args.out / "summary.md").write_text(render(summary, protocol), encoding="utf-8")
    print(f"\n{summary['assessed']}/{summary['sites']} assessed; levels {summary['levels']}; "
          f"false alarms {len(summary['false_alarms'])} -> {args.out / 'summary.md'}")


if __name__ == "__main__":
    main()
