from types import SimpleNamespace

import pytest

from pipeline.classify import Classifier, registrable_domain, third_party_status


@pytest.mark.parametrize("host,expected", [
    ("www.abc.net.au", "abc.net.au"), ("sub.example.com", "example.com"),
    ("localhost", "localhost"), ("127.0.0.1", "127.0.0.1"),
    ("https://WWW.ABC.NET.AU./news", "abc.net.au"),
    ("first.github.io", "first.github.io"), ("[::1]", "::1"),
])
def test_registrable_domain(host, expected):
    assert registrable_domain(host) == expected


@pytest.mark.parametrize("request_url,page,expected", [
    ("https://static.abc.net.au/a", "www.abc.net.au", False),
    ("https://doubleclick.net/pixel", "https://www.abc.net.au", True),
    ("https://example.com", None, None),
    ("https://first.github.io", "https://second.github.io", True),
])
def test_party_status(request_url, page, expected):
    assert third_party_status(request_url, page) is expected


def test_tracker_and_owner_subdomain_match():
    c = Classifier({"doubleclick.net"}, {"doubleclick.net": {"owner": "Google", "category": "advertising"}})
    result = c.classify("https://stats.g.doubleclick.net/pixel", "www.abc.net.au", "image")
    assert result["third_party"] is True
    assert result["is_tracker"] is True
    assert result["owner"] == "Google"
    assert result["tracker_source"] == "easyprivacy:doubleclick.net"


def test_keywords_alone_do_not_establish_tracking():
    result = Classifier(set(), {}).classify("https://tracking-a-school-project.example.com")
    assert result["is_tracker"] is False
    assert result["tracker_hint"] is True


def test_owner_mapping_has_domain_boundaries():
    c = Classifier(set(), {})
    assert c.classify("https://evilgoogle.com")["owner"] is None
    assert c.classify("https://x.com.attacker.com")["owner"] is None
    assert c.classify("https://fonts.googleapis.com/css")["owner"] == "Google"


def test_geoip_unknown_is_not_assumed_domestic_or_adequate():
    result = Classifier(set(), {}).classify("http://www.abc.net.au/x", "www.abc.net.au")
    assert result["insecure"] is True
    assert result["country"] is None
    assert result["offshore"] is None
    assert result["country_adequacy"] is None


@pytest.mark.parametrize("country,offshore", [("AU", False), ("NZ", True), ("US", True)])
def test_offshore_is_non_au_not_a_legal_whitelist(country, offshore, monkeypatch):
    c = Classifier(set(), {}, geoip_reader=object())
    monkeypatch.setattr(c, "_geoip_lookup", lambda _: country)
    result = c.classify("https://example.com")
    assert result["offshore"] is offshore
    assert result["country_adequacy"] is None


def test_only_supported_easyprivacy_rules_are_loaded(tmp_path):
    (tmp_path / "easyprivacy.txt").write_text("||tracking.example.com^\n@@||allowed.example.com^\n/analytics.js\n||conditional.example.net^$third-party\n")
    c = Classifier.load(tmp_path)
    assert c.tracker_domains == {"tracking.example.com"}
