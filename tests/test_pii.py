import hashlib

import pytest

from pipeline.pii import PIIDetector, normalise_email, normalise_phone


def test_normalise_email_gmail_combined_alias_variants():
    variants = normalise_email("First.Last+news@gmail.com")
    assert {"first.last+news@gmail.com", "firstlast@gmail.com", "first.last@gmail.com"} <= set(variants)


def test_phone_formats_both_directions():
    expected = {"0412345678", "61412345678", "+61412345678"}
    assert expected <= set(normalise_phone("0412345678"))
    assert expected <= set(normalise_phone("+61 412 345 678"))


@pytest.mark.parametrize("value", ["0", "123", "04XXXXXXXX", "000", "1" * 16])
def test_short_or_invalid_phone_rejected(value):
    with pytest.raises(ValueError):
        PIIDetector({"phone": [value]})


@pytest.mark.parametrize("algorithm", PIIDetector.HASH_ALGOS)
def test_hash_match_is_exact_and_reports_algorithm(algorithm):
    detector = PIIDetector({"email": ["person@example.com"]})
    digest = hashlib.new(algorithm, b"person@example.com").hexdigest()
    hits = detector.scan(f"uid={digest.upper()}&v=1")
    assert len(hits) == 1
    assert hits[0]["form"] == "hashed"
    assert hits[0]["algo"] == algorithm
    assert detector.scan("f" + digest + "a") == []


def test_raw_match_does_not_include_actual_value():
    detector = PIIDetector({"email": ["person@example.com"]})
    hits = detector.scan_request("https://tracker.example", "email=person%40example.com")
    assert hits[0]["form"] == "raw"
    assert hits[0]["surface"] == "body"
    assert hits[0]["encoding"] == "percent-decoded"
    assert "person@example.com" not in str(hits)


def test_unrelated_email_or_hash_does_not_count_as_visitor_pii():
    detector = PIIDetector({"email": ["person@example.com"]})
    unrelated = hashlib.sha256(b"nobody@example.com").hexdigest()
    assert detector.scan("contact=support@example.com&uid=" + unrelated) == []
    assert detector.scan("otherperson@example.com") == []
    assert detector.scan("person@example.com.evil") == []


def test_empty_config_is_safe(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    assert PIIDetector.from_yaml(path).scan("anything") == []
    assert PIIDetector({}).scan_request("https://example.com") == []


def test_bad_config_rejected():
    with pytest.raises(ValueError):
        PIIDetector({"email": "person@example.com"})
    with pytest.raises(ValueError):
        PIIDetector({"phone": [412345678]})
