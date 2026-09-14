"""
DataExodus — Test Suite
Run with: python -m pytest tests/ -v
"""
import hashlib
import tempfile
from pathlib import Path

import pytest
import yaml

from pipeline.classify import Classifier
from pipeline.pii import PIIDetector
from pipeline.risk import score_request, score_site


# --- Fixtures ---

@pytest.fixture
def classifier():
    # Minimal classifier without external files
    return Classifier(
        tracker_domains={"google-analytics.com", "doubleclick.net", "facebook.com"},
        entity_map={
            "google-analytics.com": {"owner": "Google", "category": "analytics"},
            "doubleclick.net": {"owner": "Google", "category": "advertising"},
        },
        geoip_reader=None,
    )


@pytest.fixture
def pii_detector(tmp_path):
    ident = {"email": ["test@gmail.com"], "phone": ["0412 345 678"]}
    p = tmp_path / "ident.yaml"
    p.write_text(yaml.safe_dump(ident))
    return PIIDetector.from_yaml(p)


# --- Classification Tests ---

def test_classify_tracker(classifier):
    r = classifier.classify("https://google-analytics.com/collect", "news.com.au", "script")
    assert r["is_tracker"] is True
    assert r["owner"] == "Google"


def test_classify_non_tracker(classifier):
    r = classifier.classify("https://news.com.au/article.jpg", "news.com.au", "image")
    assert r["is_tracker"] is False


def test_classify_guess_owner(classifier):
    r = classifier.classify("https://fonts.googleapis.com/css", "example.com", "stylesheet")
    assert r["owner"] == "Google"


# --- PII Detection Tests ---

def test_pii_hash_email(pii_detector):
    email = "test@gmail.com"
    h = hashlib.md5(email.encode()).hexdigest()
    hits = pii_detector.scan(h)
    assert len(hits) == 1
    assert hits[0]["type"] == "email"
    assert hits[0]["algo"] == "md5"


def test_pii_gmail_no_dots(pii_detector):
    # Gmail without dots: test@gmail.com → t e s t @gmail.com
    email_no_dots = "test@gmail.com"  # same in this case
    h = hashlib.sha256(email_no_dots.encode()).hexdigest()
    hits = pii_detector.scan(h)
    assert len(hits) >= 1


def test_pii_phone_variants(pii_detector):
    digits = "0412345678"
    h = hashlib.sha1(digits.encode()).hexdigest()
    hits = pii_detector.scan(h)
    assert len(hits) >= 1
    assert hits[0]["type"] == "phone"


def test_pii_no_false_positive(pii_detector):
    random_str = "abcdef1234567890abcdef1234567890"
    hits = pii_detector.scan(random_str)
    assert len(hits) == 0


def test_pii_scan_request(pii_detector):
    email = "test@gmail.com"
    h = hashlib.sha256(email.encode()).hexdigest()
    hits = pii_detector.scan_request(
        url=f"https://tracker.example.com/pixel?uid={h}",
        body=None,
        cookies=None,
        headers={},
    )
    assert len(hits) >= 1


# --- Risk Scoring Tests ---

def test_risk_tracker_only():
    cls = {"is_tracker": True, "country_adequacy": True, "url": "https://x.com"}
    assert score_request(cls, []) == 25


def test_risk_offshore_pii():
    cls = {"is_tracker": True, "country_adequacy": False, "url": "https://x.com"}
    assert score_request(cls, [{"type": "email"}]) == 80


def test_risk_max_cap():
    cls = {
        "is_tracker": True,
        "country_adequacy": False,
        "url": "http://insecure.example.com",
        "fingerprinting": True,
    }
    assert score_request(cls, [{"type": "email"}]) == 100


def test_score_site_empty():
    assert score_site([])["score"] == 0


def test_score_site_aggregate():
    reqs = [
        {"risk_score": 25, "is_tracker": True, "country_adequacy": True, "pii_detected": False},
        {"risk_score": 80, "is_tracker": True, "country_adequacy": False, "pii_detected": True},
    ]
    s = score_site(reqs)
    assert s["max"] == 80
    assert s["mean"] == 52.5
    assert s["trackers"] == 2
    assert s["offshore"] == 1
    assert s["pii"] == 1
