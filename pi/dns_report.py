"""Summarise the DNS watch log: which companies your devices contact, and where.

  python -m pi.dns_report --db data/dnswatch.sqlite --hours 168 --out reports/dns-week

Names are labelled with the study's reference lists (python setup_data.py) and
the answered addresses with GeoLite2 when present. Unknown stays unknown. A
lookup is not a transfer of personal information, and an address's country is
an estimate of where a connection would go, not of where data is stored.
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path


def _classifier(blocklists: Path):
    if not blocklists.exists():
        return None
    from pipeline.classify import Classifier
    mmdb = blocklists / "GeoLite2-Country.mmdb"
    return Classifier.load(blocklists, mmdb if mmdb.exists() else None)


def _country(classifier, ips: list[str]) -> str | None:
    if not classifier or not classifier.geoip:
        return None
    for ip in ips:
        try:
            # Block answers (0.0.0.0) and private addresses have no country.
            if not ipaddress.ip_address(ip).is_global:
                continue
            return classifier.geoip.country(ip).country.iso_code
        except Exception:  # noqa: BLE001 - unknown or malformed address
            continue
    return None


def _read(db, flags: str, since: int, device: str | None) -> list[tuple]:
    con = sqlite3.connect(f"{Path(db).resolve().as_uri()}?{flags}", uri=True)
    try:
        tagged = "device" in {row[1] for row in con.execute("PRAGMA table_info(queries)")}
        query = "SELECT ts, client, qname, qtype, rcode, answers, blocked, listed FROM queries WHERE ts >= ?"
        if device:
            if not tagged:
                return []
            return con.execute(query + " AND device = ? ORDER BY ts", (since, device)).fetchall()
        # Hotspot visitors' lookups (tagged with their device) are shown only to
        # that device, on the portal's "My device" page: never in this summary.
        return con.execute(query + (" AND device IS NULL" if tagged else "") + " ORDER BY ts", (since,)).fetchall()
    finally:
        con.close()


def _rows(db, since: int, device: str | None) -> list[tuple]:
    try:
        return _read(db, "mode=ro", since, device)
    except sqlite3.OperationalError:
        # The dashboard's filesystem is read-only; with the DNS watch stopped
        # there is no WAL index to share, so read the file as it stands.
        return _read(db, "mode=ro&immutable=1", since, device)


def summarise(db: str | Path, hours: float = 24, blocklists: str | Path = "data/blocklists", classifier=None,
              device: str | None = None, since: int | None = None, recent: int = 0) -> dict:
    """device: one hotspot device's lookups only (the portal's "My device" page),
    from `since` onwards; recent: also return the latest N lookups, labelled."""
    since = max(int(time.time() - hours * 3600), since or 0)
    if not Path(db).exists():
        return {"available": False, "hours": hours}
    rows = _rows(db, since, device)
    classifier = classifier if classifier is not None else _classifier(Path(blocklists))
    labels: dict[str, dict] = {}
    owners, countries, clients, trackers = Counter(), Counter(), Counter(), Counter()
    blocked = tracker_queries = located = offshore = 0
    latest = []
    for ts, client, qname, qtype, rcode, answers, was_blocked, listed in rows:
        if qname not in labels:
            info = classifier.label(qname) if classifier else {}
            labels[qname] = {"tracker": bool(info.get("is_tracker")) or bool(listed),
                             "owner": info.get("owner"), "category": info.get("category")}
        label = labels[qname]
        clients[client] += 1
        blocked += was_blocked
        if label["tracker"]:
            tracker_queries += 1
            trackers[qname] += 1
        if label["owner"]:
            owners[label["owner"]] += 1
        country = _country(classifier, json.loads(answers)) if qtype in ("A", "AAAA") else None
        if country:
            located += 1
            countries[country] += 1
            offshore += country != "AU"
        if recent and qtype in ("A", "AAAA", "HTTPS"):
            latest.append({"ts": ts, "name": qname, "tracker": label["tracker"], "owner": label["owner"],
                           "country": country, "blocked": bool(was_blocked)})
    extra = {}
    if recent:
        # One row per name (its latest lookup), newest first.
        seen: dict[str, dict] = {}
        for item in latest:
            seen.pop(item["name"], None)
            seen[item["name"]] = item
        extra["recent"] = list(reversed(list(seen.values())))[:recent]
    return {**extra,
        "available": True, "hours": hours, "queries": len(rows), "distinct_names": len(labels),
        "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None,
        "blocked": blocked, "tracker_queries": tracker_queries,
        "reference_lists": bool(classifier and classifier.reference_files),
        "geoip": bool(classifier and classifier.geoip),
        "located_answers": located, "offshore_answers": offshore,
        "clients": clients.most_common(), "owners": owners.most_common(15),
        "countries": countries.most_common(), "top_trackers": trackers.most_common(25),
    }


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def render(summary: dict) -> str:
    e = lambda v: html.escape(str(v))  # noqa: E731
    if not summary.get("available"):
        return "<p>No DNS watch log yet. Point a device's DNS at the Pi and refresh.</p>"

    def table(rows, head):
        body = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in rows) or \
            "<tr><td colspan=2>None observed</td></tr>"
        return f"<table><tr><th>{e(head[0])}</th><th>{e(head[1])}</th></tr>{body}</table>"

    s = summary
    notes = []
    if not s["reference_lists"]:
        notes.append("Tracker lists are not installed: run setup_data.py. Tracker counts are unavailable, not zero.")
    if not s["geoip"]:
        notes.append("GeoLite2 is not installed: countries are unknown.")
    return (
        f"<div class=cards><div class=card><b>{s['queries']:,}</b>lookups in the last {e(s['hours'])} h</div>"
        f"<div class=card><b>{pct(s['tracker_queries'], s['queries'])}</b>to listed tracker / malware names</div>"
        f"<div class=card><b>{s['blocked']:,}</b>answered with 0.0.0.0 (block mode)</div>"
        f"<div class=card><b>{pct(s['offshore_answers'], s['located_answers'])}</b>of located answers outside AU "
        f"({s['located_answers']:,} located)</div></div>"
        + "".join(f"<p class=note>{e(n)}</p>" for n in notes)
        + "<h2>Companies behind the names</h2>" + table(s["owners"], ("Owner", "Lookups"))
        + "<h2>Countries of answered addresses</h2>" + table(s["countries"], ("Country", "Lookups"))
        + "<h2>Most-looked-up tracker names</h2>" + table(s["top_trackers"], ("Name", "Lookups"))
        + "<h2>Devices</h2>" + table(s["clients"], ("Client address", "Lookups"))
        + "<p class=note>A lookup shows that a device was about to connect, not what it sent. The country is a "
          "GeoIP estimate of the answering address, not where data is stored; it does not by itself show an "
          "APP 8 disclosure.</p>"
    )


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DataExodus DNS watch</title><style>body{{font:15px/1.5 system-ui;margin:0;background:#edf4f3;color:#163840}}
main{{max-width:960px;margin:30px auto;padding:24px;background:#fff;border-radius:18px}}h1{{margin:0 0 12px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}.card{{background:#edf5f1;border-radius:12px;padding:14px}}
.card b{{display:block;font-size:26px}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:6px 8px;border-bottom:1px solid #e2ebe7;overflow-wrap:anywhere}}
.note{{color:#557079;font-size:13px}}</style><main><h1>DNS watch</h1>{body}</main></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="data/dnswatch.sqlite")
    parser.add_argument("--hours", type=float, default=168)
    parser.add_argument("--blocklists", default="data/blocklists")
    parser.add_argument("--out", type=Path, default=Path("reports/dns-watch"))
    args = parser.parse_args()
    summary = summarise(args.db, args.hours, args.blocklists)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "dns-watch.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "dns-watch.html").write_text(PAGE.format(body=render(summary)), encoding="utf-8")
    print(f"[dns] {summary.get('queries', 0)} lookups -> {args.out / 'dns-watch.html'}")


if __name__ == "__main__":
    main()
