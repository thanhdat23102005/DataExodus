"""
DataExodus — Risk Scorer (0–100)
Aggregates flags into a single risk score per site / per request.
"""
from __future__ import annotations


def level(score: int) -> str:
    return "red" if score >= 50 else "yellow" if score >= 20 else "green"


def is_offshore(classification: dict) -> bool:
    if "offshore" in classification:
        return classification["offshore"] is True
    # Compatibility with old events; not a legal adequacy assessment.
    return classification.get("country_adequacy") is False


def score_request(classification: dict, pii_hits: list) -> int:
    """
    Score a single request 0–100 based on:
      - tracker presence
      - estimated non-Australian destination (unknown contributes no points)
      - PII transmitted
      - insecure protocol
      - fingerprinting detected
    """
    score = 0
    if classification.get("is_tracker"):
        score += 25
    if is_offshore(classification):
        score += 25
    if pii_hits:
        score += 30
    if classification.get("fingerprinting"):
        score += 15
    # Insecure transport
    url = classification.get("url", "")
    if url.lower().startswith("http://"):
        score += 5
    return min(score, 100)


def score_site(requests: list[dict]) -> dict:
    """Aggregate score for a site from its requests."""
    if not requests:
        return {"score": 0, "max": 0, "mean": 0, "trackers": 0, "offshore": 0, "pii": 0}

    scores = [r.get("risk_score", 0) for r in requests]
    trackers = sum(1 for r in requests if r.get("is_tracker"))
    offshore = sum(1 for r in requests if is_offshore(r))
    pii = sum(1 for r in requests if r.get("pii_detected"))

    return {
        "score": max(scores),
        "max": max(scores),
        "mean": round(sum(scores) / len(scores), 1),
        "trackers": trackers,
        "offshore": offshore,
        "pii": pii,
        "total_requests": len(requests),
    }
