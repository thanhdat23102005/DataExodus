#!/usr/bin/env python3
"""
DataExodus Setup — download reference datasets.
Run once before first crawl.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import requests

BASE = Path(__file__).parent / "data" / "blocklists"
BASE.mkdir(parents=True, exist_ok=True)


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
    ~50k individual per-domain JSON files under domains/<letter>/. A sparse
    git clone pulls only that directory, then each file's nested
    owner.displayName / categories[0] is flattened to plain strings, which
    is the shape classify.py's Layer 2 lookup already parses.
    """
    out = BASE / "tracker_radar.json"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return
    print("[down] Tracker Radar (sparse clone of domains/) ...")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--filter=blob:none",
                 "--sparse", "https://github.com/duckduckgo/tracker-radar.git", tmp],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "sparse-checkout", "set", "domains"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"[warn] Tracker Radar clone failed ({exc}), continuing...")
            return

        flat: dict[str, dict] = {}
        for path in Path(tmp, "domains").rglob("*.json"):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            domain = entry.get("domain")
            if not domain:
                continue
            owner = (entry.get("owner") or {}).get("displayName")
            categories = entry.get("categories") or []
            flat[domain.lower()] = {
                "owner": owner,
                "category": categories[0] if categories else None,
            }

    out.write_text(json.dumps(flat), encoding="utf-8")
    print(f"[done] {out.name} ({len(flat):,} domains)")


def download_geolite2(key: str | None):
    """Download GeoLite2-Country from MaxMind (requires free license key)."""
    out_mmdb = BASE / "GeoLite2-Country.mmdb"
    if out_mmdb.exists():
        print(f"[skip] {out_mmdb.name} already exists")
        return
    if not key:
        print("[warn] No --geoip-key provided. GeoIP lookups will be unavailable.")
        print("       Get a free key at: https://www.maxmind.com/en/geolite2/signup")
        return
    url = (
        f"https://download.maxmind.com/app/geoip_download?"
        f"edition_id=GeoLite2-Country&license_key={key}&suffix=tar.gz"
    )
    print(f"[down] GeoLite2-Country ...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
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
    args = parser.parse_args()

    download_easyprivacy()
    download_tracker_radar()
    download_geolite2(args.geoip_key)
    print("\n[ok] Setup complete.")


if __name__ == "__main__":
    main()
