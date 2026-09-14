"""
DataExodus — PII Detection Layer (Layer 4)
Detects hashed identifiers in network traffic using Aho-Corasick.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import ahocorasick
import yaml


class PIIDetector:
    """
    Pre-computes hashes of your personal identifiers, then scans
    request bodies, URLs, cookies, and headers for matches.
    """

    HASH_ALGOS = ["md5", "sha1", "sha256", "sha512"]

    def __init__(self, identities: dict[str, list[str]]):
        """
        identities: {"email": ["you@example.com"], "phone": ["0412345678"]}
        """
        self.identities = identities
        self.automaton = ahocorasick.Automaton()
        self.hash_to_meta: dict[str, dict] = {}
        self._build_automaton()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PIIDetector":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    def _build_automaton(self):
        """Pre-compute all hash variants and load into Aho-Corasick."""
        for id_type, values in self.identities.items():
            for raw in values:
                raw = str(raw).strip()
                if not raw:
                    continue
                variants = self._normalize(raw, id_type)
                for variant in variants:
                    for algo in self.HASH_ALGOS:
                        h = getattr(hashlib, algo)(variant.encode("utf-8")).hexdigest()
                        self._add_hash(h, id_type, algo, raw)
                        # Also uppercase variant (some systems uppercase hex)
                        self._add_hash(h.upper(), id_type, algo, raw)
        self.automaton.make_automaton()
        print(f"[pii] Loaded {len(self.hash_to_meta)} hash patterns")

    def _add_hash(self, h: str, id_type: str, algo: str, raw: str):
        if h not in self.hash_to_meta:
            self.hash_to_meta[h] = {"type": id_type, "algo": algo, "raw": raw}
            self.automaton.add_word(h, h)

    def _normalize(self, value: str, id_type: str) -> list[str]:
        """Generate normalization variants."""
        variants = [value]
        lower = value.lower()
        if lower != value:
            variants.append(lower)
        trimmed = value.strip()
        if trimmed != value:
            variants.append(trimmed)

        if id_type == "email":
            # Gmail: remove dots, remove +alias
            local, _, domain = value.partition("@")
            if domain.lower() in ("gmail.com", "googlemail.com"):
                no_dots = local.replace(".", "") + "@" + domain
                variants.append(no_dots)
                variants.append(no_dots.lower())
                # Remove +alias
                if "+" in local:
                    base_local = local.split("+")[0]
                    variants.append(base_local + "@" + domain)
                    variants.append(base_local.replace(".", "") + "@" + domain)
        elif id_type == "phone":
            # Strip non-digits
            digits = re.sub(r"\D", "", value)
            if digits:
                variants.append(digits)
                # AU formats: 04xx xxx xxx, +61 4xx xxx xxx
                if digits.startswith("0") and len(digits) == 10:
                    variants.append("+61" + digits[1:])
                    variants.append("61" + digits[1:])
        return list(set(variants))

    def scan(self, text: str | None) -> list[dict]:
        """Scan a string for any hash matches. Returns list of detections."""
        if not text:
            return []
        # Extract hex-like strings (lengths 32, 40, 64, 128)
        found = []
        # Fast path: Aho-Corasick on full text
        for end_pos, matched_hash in self.automaton.iter(text):
            meta = self.hash_to_meta[matched_hash]
            found.append({
                "hash": matched_hash,
                "type": meta["type"],
                "algo": meta["algo"],
                "position": end_pos - len(matched_hash) + 1,
            })
        return found

    def scan_request(self, url: str, body: str | None, cookies: str | None, headers: dict | None) -> list[dict]:
        """Scan all parts of a request."""
        all_text = url or ""
        if body:
            all_text += " " + body
        if cookies:
            all_text += " " + cookies
        if headers:
            for k, v in headers.items():
                all_text += f" {k}={v}"
        return self.scan(all_text)
