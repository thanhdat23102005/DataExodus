import pandas as pd
from sklearn.linear_model import LogisticRegression

from pipeline.ml_classifier import build_pipeline, extract_features


def _sample_df():
    return pd.DataFrame([
        {"url": "https://ads.doubleclick.net/pixel?id=1&x=2",
         "initiator": "https://news.com.au/", "resource_type": "image",
         "domain": "doubleclick.net", "is_tracker": True},
        {"url": "https://www.abc.net.au/logo.png",
         "initiator": "https://www.abc.net.au/", "resource_type": "image",
         "domain": "abc.net.au", "is_tracker": False},
    ])


def test_extract_features_shape_and_columns():
    df = _sample_df()
    feats = extract_features(df)
    assert len(feats) == len(df)
    for col in ["host_length", "num_subdomains", "tracker_keyword_hits",
                "third_party", "insecure", "resource_type"]:
        assert col in feats.columns


def test_tracker_keyword_hits_detects_known_terms():
    df = _sample_df()
    feats = extract_features(df)
    assert feats.loc[0, "tracker_keyword_hits"] >= 1
    assert feats.loc[1, "tracker_keyword_hits"] == 0


def test_third_party_derived_from_initiator():
    df = _sample_df()
    feats = extract_features(df)
    assert feats.loc[0, "third_party"] == True  # noqa: E712 - different host than initiator
    assert feats.loc[1, "third_party"] == False  # noqa: E712 - same host as initiator


def test_extract_features_handles_missing_values():
    df = _sample_df()
    df.loc[0, "initiator"] = None
    df.loc[0, "resource_type"] = None
    feats = extract_features(df)
    assert feats.loc[0, "resource_type"] == "other"
    # No initiator to compare against, but the request host itself is real,
    # so it still counts as third-party.
    assert feats.loc[0, "third_party"] == True  # noqa: E712


def test_pipeline_trains_and_predicts_on_toy_data():
    df = _sample_df()
    X = extract_features(df)
    y = df["is_tracker"].astype(int)
    pipe = build_pipeline(LogisticRegression(max_iter=200))
    pipe.fit(X, y)
    preds = pipe.predict(X)
    assert len(preds) == len(y)
