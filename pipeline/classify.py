"""Explainable classification. Country is an IP-location estimate, not a legal verdict."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import geoip2.database
import geoip2.errors
import tldextract

# Bundled PSL snapshot: no hidden download during a scan.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None,
                               include_psl_private_domains=True)


def hostname(value: str | None) -> str:
    if not value or value == "null":
        return ""
    try:
        parsed = urlparse(value if "://" in value or value.startswith("//") else "//" + value)
        return (parsed.hostname or "").lower().rstrip(".").encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        return ""


def registrable_domain(value: str | None) -> str:
    host = hostname(value)
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        result = _extract(host)
        return result.top_domain_under_public_suffix or host


def third_party_status(url: str, initiator: str | None) -> bool | None:
    request_domain, page_domain = registrable_domain(url), registrable_domain(initiator)
    if not request_domain or not page_domain:
        return None
    return request_domain != page_domain


def _suffixes(domain: str):
    parts = domain.split(".")
    for i in range(max(1, len(parts) - 1)):
        yield ".".join(parts[i:])


class Classifier:
    def __init__(self, tracker_domains: set[str], entity_map: dict[str, dict],
                 geoip_reader: geoip2.database.Reader | None = None):
        self.tracker_domains = {d.lower().rstrip(".") for d in tracker_domains}
        self.entity_map = {d.lower().rstrip("."): info for d, info in entity_map.items()}
        self.geoip = geoip_reader
        self.reference_files: list[str] = []

    @classmethod
    def load(cls, blocklist_dir: str | Path, geoip_mmdb: str | Path | None = None):
        root = Path(blocklist_dir)
        domains: set[str] = set()
        loaded = []
        ep = root / "easyprivacy.txt"
        if ep.exists():
            # Only unconditional domain-wide ABP rules are supported.
            # Path rules, options and exceptions are not guessed.
            for line in ep.read_text(encoding="utf-8").splitlines():
                match = re.fullmatch(r"\|\|([a-zA-Z0-9.-]+)\^", line.strip())
                if match:
                    domains.add(match[1].lower())
            loaded.append(ep.name)
        entities = {}
        radar = root / "tracker_radar.json"
        if radar.exists():
            entities = json.loads(radar.read_text(encoding="utf-8"))
            loaded.append(radar.name)
        reader = None
        if geoip_mmdb and Path(geoip_mmdb).is_file():
            reader = geoip2.database.Reader(str(geoip_mmdb))
        result = cls(domains, entities, reader)
        result.reference_files = loaded
        if not loaded:
            print("[classify] No reference lists: tracker labels are unavailable, not a clean bill of health.")
        print(f"[classify] {len(domains)} domain rules, {len(entities)} entity records; GeoIP={'on' if reader else 'unavailable'}")
        return result

    def _entity(self, domain: str) -> tuple[str | None, dict]:
        for candidate in _suffixes(domain):
            info = self.entity_map.get(candidate)
            if isinstance(info, dict):
                return candidate, info
        return None, {}

    def _tracker_source(self, domain: str) -> str | None:
        for candidate in _suffixes(domain):
            if candidate in self.tracker_domains:
                return "easyprivacy:" + candidate
        matched, info = self._entity(domain)
        categories = info.get("categories") or [info.get("category")]
        if any(str(c).lower() in {"advertising", "analytics", "audience measurement",
                                 "social network", "social - share"} for c in categories):
            return "tracker_radar:" + str(matched)
        return None

    def _is_tracker(self, domain: str) -> bool:
        return self._tracker_source(hostname(domain)) is not None

    def classify(self, url: str, initiator: str | None = None, resource_type: str = "") -> dict:
        domain = hostname(url)
        matched, info = self._entity(domain)
        owner = info.get("owner") or info.get("entity") or info.get("organization")
        if isinstance(owner, dict):
            owner = owner.get("displayName") or owner.get("name")
        owner_source = "tracker_radar:" + matched if owner and matched else None
        if not owner:
            owner = self._guess_owner(domain)
            owner_source = "domain_mapping" if owner else None
        categories = info.get("categories") or []
        category = info.get("category") or (categories[0] if categories else None)
        source = self._tracker_source(domain)
        country = self._geoip_lookup(domain) if self.geoip and domain else None
        return {
            "domain": domain, "third_party": third_party_status(url, initiator),
            "is_tracker": bool(source), "tracker_source": source,
            "tracker_hint": any(k in domain for k in ("analytics", "pixel", "telemetry", "track")),
            "category": category, "owner": owner, "owner_source": owner_source,
            "country": country, "offshore": country != "AU" if country else None,
            # Deprecated compatibility column: no invented APP 8 whitelist.
            "country_adequacy": None,
            "insecure": urlparse(url).scheme.lower() == "http",
            "initiator": initiator, "resource_type": resource_type,
        }

    def label(self, name: str) -> dict:
        """Tracker / owner / category for a host name with no network lookup
        (classify() also resolves the name for GeoIP). Used by the DNS watch
        report, which already has the answered addresses."""
        domain = hostname(name)
        _, info = self._entity(domain)
        owner = info.get("owner") or info.get("entity") or info.get("organization")
        if isinstance(owner, dict):
            owner = owner.get("displayName") or owner.get("name")
        categories = info.get("categories") or []
        return {"domain": domain, "is_tracker": self._tracker_source(domain) is not None,
                "owner": owner or self._guess_owner(domain),
                "category": info.get("category") or (categories[0] if categories else None)}

    @staticmethod
    def _guess_owner(domain: str) -> str | None:
        owners = {
            "google.com": "Google", "googleapis.com": "Google", "gstatic.com": "Google",
            "google-analytics.com": "Google", "googletagmanager.com": "Google",
            "doubleclick.net": "Google", "youtube.com": "Google",
            "facebook.com": "Meta", "facebook.net": "Meta", "fbcdn.net": "Meta",
            "instagram.com": "Meta", "twitter.com": "X Corp", "x.com": "X Corp",
            "microsoft.com": "Microsoft", "bing.com": "Microsoft", "linkedin.com": "Microsoft",
            "adobe.com": "Adobe", "demdex.net": "Adobe", "amazon.com": "Amazon",
        }
        return next((owners[d] for d in _suffixes(domain) if d in owners), None)

    @lru_cache(maxsize=4096)
    def _geoip_lookup(self, domain: str) -> str | None:
        try:
            ip = socket.gethostbyname(domain)
            response = self.geoip.country(ip)
            return response.country.iso_code
        except (socket.gaierror, geoip2.errors.AddressNotFoundError, ValueError):
            return None

    def close(self):
        if self.geoip:
            self.geoip.close()
