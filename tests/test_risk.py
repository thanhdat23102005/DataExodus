import pytest

from pipeline.risk import level, score_request, score_site


@pytest.mark.parametrize("score,expected", [(0,"green"),(19,"green"),(20,"yellow"),(49,"yellow"),(50,"red"),(100,"red")])
def test_level_boundaries(score, expected):
    assert level(score) == expected


def test_documented_risk_weights():
    assert score_request({}, []) == 0
    assert score_request({"is_tracker": True}, []) == 25
    assert score_request({"offshore": True}, []) == 25
    assert score_request({}, [{"type": "email"}]) == 30
    assert score_request({"fingerprinting": True}, []) == 15
    assert score_request({"url": "http://example.com"}, []) == 5


def test_unknown_geography_never_becomes_offshore():
    assert score_request({"offshore": None, "country_adequacy": None}, []) == 0
    assert score_site([{"offshore": None, "country_adequacy": None}])["offshore"] == 0


def test_combined_risk_caps_at_100():
    assert score_request({"is_tracker": True, "offshore": True, "fingerprinting": True,
                          "url": "http://example.com"}, [{"type": "email"}]) == 100
