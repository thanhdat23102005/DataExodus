import pytest

from protection.verdict import RULES, assess, lookalike, scam_phrases


def result(**overrides):
    base = {"ok": True, "requested_url": "https://news.example.com/a", "final_url": "https://news.example.com/a",
            "redirect_chain": ["https://news.example.com/a"], "trackers": [], "third_parties": [],
            "third_party_countries": {}, "signals": [], "downloads": [], "popups": 0, "dialogs": 0,
            "forms": {"password": 0, "card": 0, "actions": []}, "scam_phrases": [], "known_threat_hosts": [],
            "ad_network": None}
    base.update(overrides)
    return base


def codes(assessment):
    return [r["code"] for r in assessment["reasons"]]


def test_an_ordinary_https_page_scores_zero_and_says_that_is_not_a_guarantee():
    a = assess(result())
    assert a["score"] == 0 and a["level"] == "low" and a["label"] == "Low risk" and a["reasons"] == []
    assert "not proof" in a["note"]


def test_every_point_has_a_named_reason_and_reasons_are_sorted_by_weight():
    a = assess(result(signals=["clipboard_write", "notification_prompt"], downloads=["setup.exe"],
                      scam_phrases=["verify you are human"]))
    assert codes(a) == ["clipboard_write", "download_executable", "notification_prompt", "scam_wording"]
    assert a["score"] == sum(r["points"] for r in a["reasons"]) == 100
    assert a["level"] == "danger"
    assert all(r["text"].startswith(RULES[r["code"]][1]) for r in a["reasons"])


def test_credential_form_sending_to_another_site_is_the_phishing_signal():
    phish = assess(result(forms={"password": 1, "card": 2, "actions": ["https://collect.example.net/x"]}))
    assert codes(phish)[:2] == ["credential_form_cross_site", "card_form"]
    assert "(sends to example.net)" in phish["reasons"][0]["text"]
    same_site = assess(result(forms={"password": 1, "card": 0, "actions": ["https://login.example.com/session"]}))
    assert codes(same_site) == ["password_form"]  # a normal sign-in page is only noted
    http_login = assess(result(final_url="http://news.example.com/login", redirect_chain=["http://news.example.com/login"],
                               forms={"password": 1, "card": 0, "actions": []}))
    assert codes(http_login) == ["password_insecure", "insecure_page"]


@pytest.mark.parametrize("host,brand", [
    ("paypal.com.account-check.xyz", "paypal"), ("secure-paypal.com", "paypal"), ("paypa1.com", "paypal"),
    ("rnicrosoft.com", "microsoft"), ("mygov-refund.info", "mygov"), ("auspost.parcel-redelivery.top", "auspost"),
    ("commbanknetbank-login.com", "commbank"),
])
def test_lookalike_domains(host, brand):
    assert lookalike(host) == brand


@pytest.mark.parametrize("host", [
    "www.paypal.com", "accounts.google.com", "www.google.com.au", "login.microsoftonline.com", "outlook.live.com",
    "my.gov.au", "auspost.com.au", "www.amazon.com.au", "s3.amazonaws.com", "outlookindia.com", "steamboat.com",
    "medicareplans.example", "news.example.com", "203.0.113.5",
])
def test_brands_own_sites_and_ordinary_words_are_not_lookalikes(host):
    assert lookalike(host) is None


def test_redirects_click_ids_trackers_and_offshore_servers_add_small_amounts():
    a = assess(result(
        requested_url="https://www.googleadservices.com/pagead/aclk?x=1", ad_network="Google Ads",
        redirect_chain=["https://www.googleadservices.com/pagead/aclk?x=1", "https://ad.doubleclick.net/c",
                        "https://shop.example.org/p?gclid=abc&utm_source=g"],
        final_url="https://shop.example.org/p?gclid=abc&utm_source=g",
        trackers=[{"domain": "px.tracker.example", "owner": "Tracker Co"}], third_parties=["a.com", "b.com", "c.com"],
        third_party_countries={"a.com": "US", "b.com": "AU", "c.com": "SG"}))
    by_code = {r["code"]: r for r in a["reasons"]}
    assert by_code["cross_site_redirects"]["points"] == 10  # two extra sites
    assert set(by_code) == {"cross_site_redirects", "trackers", "third_parties", "offshore", "ad_click", "click_ids"}
    assert "SG, US" in by_code["offshore"]["text"] and "gclid" in by_code["click_ids"]["text"]
    assert a["score"] == 35 and a["level"] == "caution"


def test_known_threats_ip_hosts_and_punycode():
    a = assess(result(requested_url="http://203.0.113.9/x", final_url="http://xn--pypal-4ve.com/",
                      redirect_chain=["http://203.0.113.9/x", "http://xn--pypal-4ve.com/"],
                      known_threat_hosts=["203.0.113.9"]))
    assert {"known_threat", "ip_host", "punycode", "insecure_page"} <= set(codes(a))
    assert a["level"] == "danger"


def test_lab_sample_hosts_are_not_penalised_for_bare_ips_or_plain_http():
    lab = assess(result(requested_url="http://127.0.0.49:8030/a", final_url="http://127.0.0.49:8030/a",
                        redirect_chain=["http://127.0.0.49:8030/a"]), lab_hosts={"127.0.0.49"})
    assert lab["score"] == 0
    outside = assess(result(requested_url="http://127.0.0.49:8030/a", final_url="http://127.0.0.49:8030/a",
                            redirect_chain=["http://127.0.0.49:8030/a"]))
    assert {"ip_host", "insecure_page"} <= set(codes(outside))


def test_failed_visit_is_not_assessed_and_the_score_is_capped():
    assert assess({"ok": False, "error": "x"})["level"] == "unknown"
    everything = result(signals=["clipboard_write", "notification_prompt", "device_prompt", "fingerprinting"],
                        downloads=["a.apk"], known_threat_hosts=["evil.example"], dialogs=3, popups=2,
                        forms={"password": 1, "card": 1, "actions": ["https://other.example/x"]})
    assert assess(everything)["score"] == 100


def test_one_everyday_phrase_is_not_scam_wording_but_a_strong_one_is():
    # Found on legitimate sites in the 50-site study: "gift card" (retailers), "act now" (government).
    assert "scam_wording" not in codes(assess(result(scam_phrases=["gift card"])))
    assert "scam_wording" not in codes(assess(result(scam_phrases=["act now"])))
    assert "scam_wording" in codes(assess(result(scam_phrases=["gift card", "within 24 hours"])))
    assert "scam_wording" in codes(assess(result(scam_phrases=["verify you are human"])))
    assert "scam_wording" in codes(assess(result(scam_phrases=["unusual activity", "verify your account"])))


def test_scam_wording_is_case_and_space_insensitive():
    assert scam_phrases("Your ACCOUNT will be\n suspended within 24  hours. Verify your account.") == [
        "verify your account", "account will be suspended", "within 24 hours"]
    assert scam_phrases("Opening hours for the library") == []
