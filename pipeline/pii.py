"""Match configured identifiers in raw and deterministic hex-hash form locally."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote

import ahocorasick
import yaml


def normalise_email(value: str) -> list[str]:
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Email identifiers must be valid email-shaped strings")
    variants = {value}
    local, domain = value.rsplit("@", 1)
    if domain in {"gmail.com", "googlemail.com"}:
        base = local.split("+", 1)[0]
        variants.update({base + "@" + domain, base.replace(".", "") + "@" + domain,
                         local.replace(".", "") + "@" + domain})
    return sorted(variants)


def normalise_phone(value: str) -> list[str]:
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15 or re.search(r"[a-zA-Z]", value):
        raise ValueError("Phone identifiers need 7–15 digits; short placeholders cause false positives")
    variants = {value.strip(), digits}
    if value.strip().startswith("+"):
        variants.add("+" + digits)
    if len(digits) == 10 and digits.startswith("0"):
        variants.update({"61" + digits[1:], "+61" + digits[1:]})
    elif len(digits) == 11 and digits.startswith("61"):
        variants.update({"0" + digits[2:], "+" + digits})
    return sorted(variants)


class PIIDetector:
    HASH_ALGOS = ("md5", "sha1", "sha256", "sha512")

    def __init__(self, identities: dict[str, list[str]] | None = None):
        if identities is not None and not isinstance(identities, dict):
            raise ValueError("Identity YAML must contain email/phone lists")
        self.automaton = ahocorasick.Automaton()
        self.patterns: dict[str, dict] = {}
        self.identity_count = 0
        for kind, values in (identities or {}).items():
            if kind not in {"email", "phone"} or not isinstance(values, list):
                raise ValueError("Use only email: [] and phone: [] lists; quote phone numbers")
            for value in values:
                if not isinstance(value, str):
                    raise ValueError("Identifiers must be strings; quote phone numbers")
                if not value.strip():
                    continue
                variants = normalise_email(value) if kind == "email" else normalise_phone(value)
                self.identity_count += 1
                for variant in sorted(set(variants + [value.strip()])):
                    self.patterns[variant.lower()] = {"type": kind, "form": "raw", "algo": None}
                    for algorithm in self.HASH_ALGOS:
                        digest = hashlib.new(algorithm, variant.encode("utf-8")).hexdigest()
                        self.patterns[digest] = {"type": kind, "form": "hashed", "algo": algorithm}
        for pattern in self.patterns:
            self.automaton.add_word(pattern, pattern)
        if self.patterns:
            self.automaton.make_automaton()
        self.hash_to_meta = {p: m for p, m in self.patterns.items() if m["form"] == "hashed"}

    @classmethod
    def from_yaml(cls, path: str | Path):
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    def scan(self, text: str | None) -> list[dict]:
        if not text or not self.patterns:
            return []
        text = text.lower()
        hits = []
        for end, pattern in self.automaton.iter(text):
            meta = self.patterns[pattern]
            start = end - len(pattern) + 1
            before, after = text[start - 1:start] if start else "", text[end + 1:end + 2]
            if meta["form"] == "hashed":
                if (before and before in "0123456789abcdef") or (after and after in "0123456789abcdef"):
                    continue
            elif meta["type"] == "email":
                if (before and re.match(r"[\w.+@-]", before)) or (after and re.match(r"[\w.@-]", after)):
                    continue
            elif (before and before.isdigit()) or (after and after.isdigit()):
                continue
            hit = {**meta, "position": start}
            if meta["form"] == "hashed":
                hit["hash"] = pattern
            hits.append(hit)
        return hits

    def scan_request(self, url: str, body: str | None = None, cookies: str | None = None,
                     headers: dict | None = None) -> list[dict]:
        surfaces = {"url": url, "body": body, "cookies": cookies}
        for name, value in (headers or {}).items():
            if value is not None:
                surfaces["header:" + name.lower()] = str(value)
        findings = []
        for surface, text in surfaces.items():
            if not text:
                continue
            decoded = unquote(text)
            found = self.scan(decoded)
            encoding = "percent-decoded" if decoded != text else "literal"
            findings.extend({**hit, "surface": surface, "encoding": encoding} for hit in found)
        return findings
