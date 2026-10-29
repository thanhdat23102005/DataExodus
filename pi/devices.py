"""Hotspot devices: what each device on the DataExodus Wi-Fi agreed to.

The captive portal (pi/portal.py) writes one record when a device's user
chooses on the welcome page; the DNS watch (pi/dnswatch.py) reads the same
file to decide whether to log that device's lookups and whether to block
trackers for it. Nothing is logged for a device without a record.

A device is identified by the MAC address the Pi sees for its IP address (the
kernel neighbour table), so a phone that gets a new address keeps its choice,
and a new phone that is given an old address does not inherit someone else's.
Modern phones use a random MAC per Wi-Fi network, so the key does not follow a
phone to other networks. It is still a device identifier: records are deleted
with "Forget this device", and lookups expire after PORTAL_RETENTION_HOURS.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

ARP = Path("/proc/net/arp")
MAX_DEVICES = 256


def neighbours(path: Path = ARP) -> dict[str, str]:
    """IPv4 address -> MAC from the kernel neighbour table (Linux)."""
    found = {}
    try:
        lines = path.read_text(encoding="ascii", errors="replace").splitlines()[1:]
    except OSError:
        return found
    for line in lines:
        parts = line.split()
        # IP address, HW type, Flags, HW address, Mask, Device. Flags 0x0 = incomplete.
        if len(parts) >= 4 and parts[2] != "0x0" and parts[3] != "00:00:00:00:00:00":
            found[parts[0]] = parts[3].lower()
    return found


class Devices:
    def __init__(self, path: str | Path, arp: Path = ARP, refresh: float = 2.0):
        self.path = Path(path)
        self.arp = arp
        self.refresh = refresh
        self.lock = threading.Lock()
        self._records: dict[str, dict] = {}
        self._mtime = None
        self._checked = 0.0
        self._neigh: dict[str, str] = {}
        self._neigh_at = 0.0

    def key(self, ip: str) -> str:
        now = time.monotonic()
        if now - self._neigh_at > self.refresh or ip not in self._neigh:
            self._neigh, self._neigh_at = neighbours(self.arp), now
        mac = self._neigh.get(ip)
        return "mac:" + mac if mac else "ip:" + ip

    def _load(self) -> dict[str, dict]:
        now = time.monotonic()
        if now - self._checked < self.refresh and self._mtime is not None:
            return self._records
        self._checked = now
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            self._records, self._mtime = {}, None
            return self._records
        if mtime != self._mtime:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._records = {k: v for k, v in (data.get("devices") or {}).items() if isinstance(v, dict)}
            except (OSError, ValueError, AttributeError):
                self._records = {}
            self._mtime = mtime
        return self._records

    def get(self, ip: str) -> dict | None:
        key = self.key(ip)
        record = self._load().get(key)
        return {**record, "key": key} if record else None

    def _write(self, records: dict[str, dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "devices": records}, indent=1), encoding="utf-8")
        try:
            os.chmod(tmp, 0o640)
        except OSError:
            pass
        os.replace(tmp, self.path)  # readers see the old or the new file, never half of one
        self._checked, self._mtime = 0.0, None

    def set(self, ip: str, watch: bool, block: bool) -> dict:
        with self.lock:
            self._checked = 0.0
            records = dict(self._load())
            key = self.key(ip)
            now = int(time.time())
            old = records.get(key, {})
            records[key] = {"watch": bool(watch), "block": bool(block), "joined": old.get("joined", now),
                            # Lookups are shown from the moment monitoring was last switched on.
                            "watch_since": old.get("watch_since", now) if watch and old.get("watch") else now,
                            "updated": now}
            if len(records) > MAX_DEVICES:
                for stale in sorted(records, key=lambda k: records[k].get("updated", 0))[:len(records) - MAX_DEVICES]:
                    records.pop(stale)
            self._write(records)
            return {**records[key], "key": key}

    def forget(self, ip: str) -> str:
        with self.lock:
            self._checked = 0.0
            records = dict(self._load())
            key = self.key(ip)
            records.pop(key, None)
            self._write(records)
            return key

    def all(self) -> dict[str, dict]:
        self._checked = 0.0
        return dict(self._load())
