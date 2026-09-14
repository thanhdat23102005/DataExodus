"""
DataExodus — Request Classification Layer
Tầng 1–3: Tracker detection, Entity resolution, GeoIP
"""
from __future__ import annotations

import ipaddress
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import geoip2.database
import geoip2.errors


class Classifier:
    """
    Classifies a network request into:
      - is_tracker: bool
      - category: str | None  (advertising, analytics, social, etc.)
      - owner: str | None     (Google, Meta, etc.)
      - country: str | None   (ISO country code)
      - country_adequacy: bool  # APP 8 adequacy (simplified)
    """

    ADEQUATE_COUNTRIES = {
        "AU", "NZ", "GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT",
        "SE", "NO", "DK", "FI", "CH", "IE", "PT", "LU", "IS", "LI",
        "CA", "JP", "KR", "SG", "IL", "UY", "AR", "BR", "MX", "CL",
        "CO", "PE", "ZA", "IN", "MY", "PH", "TH", "VN", "ID", "TW",
        "HK", "MO",
    }

    def __init__(
        self,
        tracker_domains: set[str],
        entity_map: dict[str, dict],
        geoip_reader: geoip2.database.Reader | None = None,
    ):
        self.tracker_domains = tracker_domains
        self.entity_map = entity_map
        self.geoip = geoip_reader

    @classmethod
    def load(
        cls,
        blocklist_dir: str | Path,
        geoip_mmdb: str | Path | None = None,
    ) -> "Classifier":
        blocklist_dir = Path(blocklist_dir)

        # 1. EasyPrivacy → domain set
        tracker_domains = set()
        ep = blocklist_dir / "easyprivacy.txt"
        if ep.exists():
            for line in ep.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("!") or line.startswith("["):
                    continue
                # Extract domain-ish parts
                m = re.search(r"[|/]*([a-z0-9\-]+\.(?:com|net|org|io|co\.[a-z]{2}|[a-z]+))", line, re.I)
                if m:
                    tracker_domains.add(m.group(1).lower())
                else:
                    # Fallback: any word with a dot
                    for token in re.findall(r"[a-z0-9\-]+\.[a-z0-9\-\.]+[a-z]", line, re.I):
                        tracker_domains.add(token.lower())
            print(f"[classify] Loaded {len(tracker_domains):,} tracker domains from EasyPrivacy")
        else:
            print(f"[classify] Warning: {ep} not found")

        # 2. Tracker Radar → entity map
        entity_map: dict[str, dict] = {}
        tr = blocklist_dir / "tracker_radar.json"
        if tr.exists():
            data = json.loads(tr.read_text(encoding="utf-8"))
            # Tracker Radar structure varies; handle common shapes
            domains = data if isinstance(data, dict) else {}
            for domain, info in domains.items():
                if isinstance(info, dict):
                    entity_map[domain.lower()] = info
            print(f"[classify] Loaded {len(entity_map):,} Tracker Radar entries")
        else:
            print(f"[classify] Warning: {tr} not found")

        # 3. GeoIP
        geoip_reader = None
        if geoip_mmdb and Path(geoip_mmdb).exists():
            geoip_reader = geoip2.database.Reader(str(geoip_mmdb))
            print(f"[classify] GeoIP loaded")

        return cls(tracker_domains, entity_map, geoip_reader)

    def classify(
        self,
        url: str,
        initiator: str | None = None,
        resource_type: str = "",
    ) -> dict:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        domain = hostname.lower()

        # --- Layer 1: Is it a tracker? ---
        is_tracker = self._is_tracker(domain)
        category = None
        owner = None

        # --- Layer 2: Entity resolution ---
        # Attempted for every domain, not gated behind is_tracker - a CDN/
        # font host (e.g. fonts.googleapis.com) is worth attributing to its
        # owner for the "who receives data" goal of this project even when
        # it isn't itself behaving like a tracker. category is only guessed
        # once an owner is actually known, so unrelated domains don't get a
        # meaningless "unknown" category.
        info = self.entity_map.get(domain, {})
        if isinstance(info, dict):
            owner = info.get("owner", info.get("entity", info.get("organization")))
            category = info.get("category", info.get("type"))
        if not owner:
            owner = self._guess_owner(domain)
        if owner and not category:
            category = self._guess_category(domain)

        # --- Layer 3: GeoIP ---
        country = None
        country_adequacy = True  # default assume adequate until proven otherwise
        if self.geoip:
            country = self._geoip_lookup(domain)
            if country:
                country_adequacy = country in self.ADEQUATE_COUNTRIES

        return {
            "domain": domain,
            "is_tracker": is_tracker,
            "category": category,
            "owner": owner,
            "country": country,
            "country_adequacy": country_adequacy,
            "initiator": initiator,
            "resource_type": resource_type,
        }

    def _is_tracker(self, domain: str) -> bool:
        # Exact match
        if domain in self.tracker_domains:
            return True
        # Suffix match (e.g., google-analytics.com)
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            suffix = ".".join(parts[i:])
            if suffix in self.tracker_domains:
                return True
        # Known tracker keywords
        tracker_keywords = [
            "analytics", "metric", "track", "pixel", "beacon", "telemetry",
            "adsystem", "adserver", "advertising", "doubleclick", "facebook",
            "google-analytics", "googletagmanager", "gtm", "segment", "mixpanel",
            "hotjar", "chartbeat", "outbrain", "taboola", "scorecardresearch",
        ]
        return any(kw in domain for kw in tracker_keywords)

    def _guess_owner(self, domain: str) -> str | None:
        """Fallback owner inference from domain name."""
        mapping = {
            "google": "Google",
            "doubleclick": "Google",
            "googletagmanager": "Google",
            "google-analytics": "Google",
            "youtube": "Google",
            "facebook": "Meta",
            "fbcdn": "Meta",
            "instagram": "Meta",
            "twitter": "X Corp",
            "x.com": "X Corp",
            "amazon": "Amazon",
            "microsoft": "Microsoft",
            "bing": "Microsoft",
            "linkedin": "Microsoft",
            "adobe": "Adobe",
            "oracle": "Oracle",
            "outbrain": "Outbrain",
            "taboola": "Taboola",
            "scorecardresearch": "Comscore",
            "quantserve": "Quantcast",
            "appsflyer": "AppsFlyer",
        }
        for key, owner in mapping.items():
            if key in domain:
                return owner
        return None

    def _guess_category(self, domain: str) -> str | None:
        if any(k in domain for k in ["analytics", "metric", "segment", "mixpanel", "hotjar", "chartbeat"]):
            return "analytics"
        if any(k in domain for k in ["ads", "adserver", "doubleclick", "outbrain", "taboola"]):
            return "advertising"
        if any(k in domain for k in ["facebook", "twitter", "linkedin", "instagram", "pinterest", "reddit"]):
            return "social"
        return "unknown"

    @lru_cache(maxsize=4096)
    def _geoip_lookup(self, domain: str) -> str | None:
        if not self.geoip:
            return None
        try:
            import socket
            ip = socket.gethostbyname(domain)
            response = self.geoip.country(ip)
            return response.country.iso_code
        except (socket.gaierror, geoip2.errors.AddressNotFoundError, ValueError):
            return None
