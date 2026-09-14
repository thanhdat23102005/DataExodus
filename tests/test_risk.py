from pipeline.risk import level, score_request


def test_score_clean_first_party():
    assert score_request({}, []) == 0
    assert level(0) == "green"


def test_score_tracker_only():
    score = score_request({"is_tracker": True}, [])
    assert score == 30
    assert level(score) == "yellow"


def test_score_tracker_plus_offshore_is_red():
    score = score_request({"is_tracker": True, "offshore": True}, [])
    assert score == 50
    assert level(score) == "red"


def test_score_pii_alone_is_yellow():
    score = score_request({}, [{"kind": "email", "form": "raw"}])
    assert score == 40
    assert level(score) == "yellow"


def test_score_caps_at_100():
    classification = {
        "is_tracker": True,
        "offshore": True,
        "outside_comparable_regime": True,
        "insecure": True,
    }
    findings = [{"kind": "email", "form": "raw"}]
    score = score_request(classification, findings)
    assert score == 100
    assert level(score) == "red"


def test_level_boundaries():
    assert level(19) == "green"
    assert level(20) == "yellow"
    assert level(49) == "yellow"
    assert level(50) == "red"
