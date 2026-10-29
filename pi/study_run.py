"""Scheduled study run (Raspberry Pi): crawl the frozen site list, process, report.

  python -m pi.study_run [--sector government] [--keep 8]

Each run goes to $DATAEXODUS_STATE/runs/<UTC time>/ with the raw captures, the
DuckDB database, the descriptive report, an audit compared with the previous
run's audit as baseline, and status.json. The same protocol every week gives a
longitudinal record of what each site sent and whether that changed. A changed
capture protocol or reference list makes a comparison inconclusive; the audit
says so rather than reporting an improvement.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def state_dir() -> Path:
    return Path(os.getenv("DATAEXODUS_STATE", ROOT / "data"))


def resolvers(path: Path = Path("/etc/resolv.conf")) -> list[str]:
    """DNS servers in use for this run. Recorded because a filtering resolver
    (some home routers answer tracker names with a local address) changes what
    a crawl can observe, so runs are comparable only with the same resolvers."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.split()[1] for line in lines if line.startswith("nameserver") and len(line.split()) > 1]


def completed_runs(runs: Path) -> list[Path]:
    return sorted(p for p in runs.iterdir() if (p / "status.json").is_file()) if runs.exists() else []


def previous_audit(runs: Path) -> Path | None:
    for run in reversed(completed_runs(runs)):
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        audit = run / "audit" / "audit.json"
        if status.get("ok") and audit.is_file():
            return audit
    return None


def acquire_lock(path: Path) -> bool:
    if path.exists() and time.time() - path.stat().st_mtime > 12 * 3600:
        path.unlink()  # a run that died without cleaning up
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def run(sector: str | None = None, keep: int = 8, python: str = sys.executable) -> dict:
    runs = state_dir() / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    lock = state_dir() / "study.lock"
    if not acquire_lock(lock):
        raise SystemExit("Another study run is in progress")
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
        baseline = previous_audit(runs)
        out = runs / stamp
        out.mkdir()
        raw, db = out / "raw", out / "study.duckdb"
        steps = [
            ("crawl", ["-m", "crawler.crawl", "--output", str(raw)] + (["--sector", sector] if sector else [])),
            ("process", ["-m", "pipeline.process", "--raw", str(raw), "--db", str(db)]),
            ("report", ["-m", "analysis.report", "--db", str(db), "--out", str(out / "report")]),
            ("audit", ["-m", "analysis.audit", "--db", str(db), "--out", str(out / "audit"),
                       "--label", f"Scheduled study run {stamp}"] + (["--baseline", str(baseline)] if baseline else [])),
        ]
        status = {"started": stamp, "sector": sector or "all", "baseline": baseline.parent.parent.name if baseline else None,
                  "host": os.getenv("DATAEXODUS_HOST_LABEL") or socket.gethostname(),
                  "resolvers": resolvers(), "steps": [], "ok": False}
        # Unbuffered, so `tail -f <run>/crawl.log` shows progress while a step runs.
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        for name, args in steps:
            began = time.time()
            with open(out / f"{name}.log", "w", encoding="utf-8") as log:
                code = subprocess.run([python, *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
            status["steps"].append({"name": name, "returncode": code, "seconds": round(time.time() - began, 1)})
            if code != 0:
                break
        status["ok"] = all(s["returncode"] == 0 for s in status["steps"]) and len(status["steps"]) == len(steps)
        status["sessions"] = len(list(raw.glob("*.json"))) if raw.exists() else 0
        status["finished"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        for old in completed_runs(runs)[:-keep] if keep > 0 else []:
            shutil.rmtree(old)
        return status
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sector", default=None, help="Only one sector of data/sites.yaml")
    parser.add_argument("--keep", type=int, default=int(os.getenv("STUDY_KEEP_RUNS", "8")), help="Completed runs to keep")
    args = parser.parse_args()
    status = run(args.sector, args.keep)
    print(json.dumps(status, indent=2))
    raise SystemExit(0 if status["ok"] else 1)


if __name__ == "__main__":
    main()
