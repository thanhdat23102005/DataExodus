import hashlib

from pipeline.pii import IdentityIndex, normalise_email, normalise_phone, scan


def test_normalise_email_variants():
    variants = normalise_email("First.Last+news@gmail.com")
    assert "first.last+news@gmail.com" in variants
    assert "firstlast@gmail.com" in variants  # dots stripped
    assert "first.last@gmail.com" in variants  # +tag stripped


def test_normalise_phone_variants():
    variants = normalise_phone("0412345678")
    assert "0412345678" in variants
    assert "61412345678" in variants
    assert "+61412345678" in variants


def test_scan_finds_raw_email():
    index = IdentityIndex.from_dict({"email": ["person@example.com"]})
    findings = scan("beacon?u=person@example.com", index)
    kinds = {(f["kind"], f["form"]) for f in findings}
    assert ("email", "raw") in kinds


def test_scan_finds_hashed_email():
    index = IdentityIndex.from_dict({"email": ["person@example.com"]})
    digest = hashlib.sha256(b"person@example.com").hexdigest()
    findings = scan(f"https://tracker.example/match?id={digest}", index)
    hits = [f for f in findings if f["form"] == "hashed"]
    assert len(hits) == 1
    assert hits[0]["kind"] == "email"
    assert hits[0]["algorithm"] == "sha256"


def test_scan_no_match_on_unrelated_hash():
    index = IdentityIndex.from_dict({"email": ["person@example.com"]})
    unrelated = hashlib.sha256(b"nobody@nowhere.com").hexdigest()
    findings = scan(f"https://tracker.example/x?id={unrelated}", index)
    assert not any(f["form"] == "hashed" for f in findings)


def test_scan_generic_pattern_for_unindexed_email():
    index = IdentityIndex()
    findings = scan("contact=someone.else@example.com", index)
    assert any(f["form"] == "pattern" and f["kind"] == "email" for f in findings)


def test_scan_empty_text():
    assert scan("", IdentityIndex()) == []
