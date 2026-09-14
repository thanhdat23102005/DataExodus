from pipeline.classify import Classifier, registrable_domain


def test_registrable_domain_com_au():
    assert registrable_domain("www.abc.net.au") == "abc.net.au"


def test_registrable_domain_gtld():
    assert registrable_domain("sub.example.com") == "example.com"


def test_registrable_domain_short_host():
    assert registrable_domain("localhost") == "localhost"


def _classifier(**kwargs):
    defaults = dict(tracker_domains=set(), entity_map={}, category_map={})
    defaults.update(kwargs)
    return Classifier(**defaults)


def test_is_tracker_exact_match():
    c = _classifier(tracker_domains={"doubleclick.net"})
    assert c.is_tracker("doubleclick.net")


def test_is_tracker_subdomain_match():
    c = _classifier(tracker_domains={"doubleclick.net"})
    assert c.is_tracker("stats.g.doubleclick.net")


def test_is_tracker_no_match():
    c = _classifier(tracker_domains={"doubleclick.net"})
    assert not c.is_tracker("example.com")


def test_classify_first_party_not_flagged():
    c = _classifier(tracker_domains={"doubleclick.net"})
    result = c.classify("https://www.abc.net.au/logo.png", "www.abc.net.au", "image")
    assert result["third_party"] is False
    assert result["is_tracker"] is False
    assert result["country"] is None


def test_classify_third_party_tracker():
    c = _classifier(
        tracker_domains={"doubleclick.net"},
        entity_map={"doubleclick.net": "Google LLC"},
        category_map={"doubleclick.net": "Advertising"},
    )
    result = c.classify(
        "https://stats.g.doubleclick.net/pixel", "www.abc.net.au", "image"
    )
    assert result["third_party"] is True
    assert result["is_tracker"] is True
    assert result["owner"] == "Google LLC"
    assert result["category"] == "Advertising"
    assert result["resource_note"] == "possible tracking pixel"


def test_classify_insecure_flagged():
    c = _classifier()
    result = c.classify("http://www.abc.net.au/x", "www.abc.net.au")
    assert result["insecure"] is True


def test_classify_secure_not_flagged():
    c = _classifier()
    result = c.classify("https://www.abc.net.au/x", "www.abc.net.au")
    assert result["insecure"] is False
