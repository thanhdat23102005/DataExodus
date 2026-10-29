#!/usr/bin/env python3
"""
DataExodus Setup — download reference datasets.
Run once before first crawl.
"""
import argparse
import json
import os
import tarfile
from pathlib import Path

import requests

BASE = Path(__file__).parent / "data" / "blocklists"
BASE.mkdir(parents=True, exist_ok=True)

REGION_RANK = {"AU": 0, "US": 1}  # Tracker Radar crawl regions, most relevant first


def download_easyprivacy():
    """Download EasyPrivacy filter list (~200k rules)."""
    url = "https://easylist.to/easylist/easyprivacy.txt"
    out = BASE / "easyprivacy.txt"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return
    print(f"[down] {url} ...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out.write_text(r.text, encoding="utf-8")
    print(f"[done] {out.name} ({len(r.text):,} chars)")


def download_tracker_radar():
    """
    Download DuckDuckGo Tracker Radar and flatten it into the single
    {domain: {"owner": ..., "category": ...}} file pipeline/classify.py
    expects.

    There is no single "tracker_radar.json" file in the real repo (that
    domains/US/tracker_radar.json path doesn't exist) - the dataset is
    ~50k individual per-domain JSON files under domains/<region>/. The repo
    tarball (~100MB) is streamed and those files are read straight out of
    it, never written to disk: a git checkout fails on Windows because some
    files are named after reserved devices (domains/US/com3.edgekey.net.json).
    Each file's nested owner.displayName / categories[0] is flattened to
    plain strings, which is the shape classify.py's Layer 2 lookup parses.
    """
    out = BASE / "tracker_radar.json"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return
    url = "https://codeload.github.com/duckduckgo/tracker-radar/tar.gz/refs/heads/main"
    print(f"[down] Tracker Radar ({url}, ~100MB) ...")
    flat: dict[str, dict] = {}
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            r.raw.decode_content = True
            with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
                for member in tar:
                    parts = member.name.split("/")
                    if not member.isfile() or len(parts) != 4 or parts[1] != "domains" \
                            or not parts[3].endswith(".json"):
                        continue
                    try:
                        entry = json.load(tar.extractfile(member))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    domain = (entry.get("domain") or "").lower()
                    # Same domain is measured from several regions; this is an
                    # AU study, so AU wins, then US, then whichever came first.
                    rank = REGION_RANK.get(parts[2], len(REGION_RANK))
                    if not domain or (domain in flat and rank >= flat[domain]["_rank"]):
                        continue
                    owner = (entry.get("owner") or {}).get("displayName")
                    categories = entry.get("categories") or []
                    flat[domain] = {
                        "owner": owner,
                        "category": categories[0] if categories else None,
                        "region": parts[2],
                        "_rank": rank,
                    }
    except (requests.RequestException, tarfile.TarError) as exc:
        print(f"[warn] Tracker Radar download failed ({exc}), continuing...")
        return

    for info in flat.values():
        info.pop("_rank")
    out.write_text(json.dumps(flat), encoding="utf-8")
    from_au = sum(1 for info in flat.values() if info["region"] == "AU")
    print(f"[done] {out.name} ({len(flat):,} domains, {from_au:,} from the AU crawl)")


def download_urlhaus(refresh: bool = False):
    """
    URLhaus (abuse.ch) malware hosts, as the daily hosts-format mirror
    published by the malware-filter project (abuse.ch's own downloads now
    need an Auth-Key and the old hostfile URL returns 410 Gone).
    Used by the Raspberry Pi DNS watch (pi/dnswatch.py) to answer those
    names with 0.0.0.0 in block mode. Changes daily, so --refresh-threats
    re-downloads it (the Pi's weekly study timer does this).
    """
    url = "https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-hosts.txt"
    out = BASE / "urlhaus_hosts.txt"
    if out.exists() and not refresh:
        print(f"[skip] {out.name} already exists (use --refresh-threats to update)")
        return
    print(f"[down] {url} ...")
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"[warn] URLhaus download failed ({exc}); malware blocking stays off, continuing...")
        return
    out.write_text(r.text, encoding="utf-8")
    hosts = sum(1 for line in r.text.splitlines() if line and not line.startswith("#"))
    print(f"[done] {out.name} ({hosts:,} hosts)")


def download_geolite2(key: str | None, account: str | None = None):
    """
    Download GeoLite2-Country from MaxMind (requires free license key).
    With --geoip-account, uses MaxMind's current endpoint (HTTP basic auth,
    account ID + key); without it, the legacy key-in-URL endpoint.
    """
    out_mmdb = BASE / "GeoLite2-Country.mmdb"
    if out_mmdb.exists():
        print(f"[skip] {out_mmdb.name} already exists")
        return
    if not key:
        print("[warn] No --geoip-key provided. GeoIP lookups will be unavailable.")
        print("       Get a free key at: https://www.maxmind.com/en/geolite2/signup")
        return
    print(f"[down] GeoLite2-Country ...")
    if account:
        r = requests.get(
            "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz",
            auth=(account, key), timeout=120,
        )
    else:
        r = requests.get(
            "https://download.maxmind.com/app/geoip_download",
            params={"edition_id": "GeoLite2-Country", "license_key": key, "suffix": "tar.gz"},
            timeout=120,
        )
    if r.status_code != 200:
        # Never echo the URL: the legacy endpoint carries the key in it.
        print(f"[warn] MaxMind refused the download (HTTP {r.status_code}). Check that the key is "
              "active (new keys can take a few minutes) and, if you have it, pass your "
              "Account ID with --geoip-account. GeoIP lookups will be unavailable.")
        return
    archive = BASE / "GeoLite2-Country.tar.gz"
    archive.write_bytes(r.content)
    # extract
    import tarfile
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith(".mmdb"):
                member.name = os.path.basename(member.name)
                tar.extract(member, BASE)
                break
    archive.unlink()
    print(f"[done] {out_mmdb.name}")


def main():
    parser = argparse.ArgumentParser(description="Download DataExodus reference data")
    parser.add_argument("--geoip-key", default=None, help="MaxMind GeoLite2 license key")
    parser.add_argument("--geoip-account", default=None, help="MaxMind Account ID (shown on the license key page)")
    parser.add_argument("--refresh-threats", action="store_true", help="Re-download the URLhaus malware host list")
    args = parser.parse_args()

    download_easyprivacy()
    download_tracker_radar()
    download_urlhaus(args.refresh_threats)
    download_geolite2(args.geoip_key, args.geoip_account)
    print("\n[ok] Setup complete.")


if __name__ == "__main__":
    main()
