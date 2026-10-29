import requests
from examples.guard_lab import EMAIL, DIGEST, GuardLab


def test_receiver_evidence_counts_only_actual_synthetic_deliveries():
    # Disable proxy inheritance: all test traffic is loopback only.
    with requests.Session() as session, GuardLab(0) as lab:
        session.trust_env = False
        page = session.get(lab.site).text
        assert "__" not in page.split("<script>")[1]  # every placeholder filled
        assert session.get(lab.site + "/receipts").json()["count"] == 0
        assert session.get(lab.collector + "/collect", params={"uid": "not-the-test-identity"}).status_code == 400
        for value in (EMAIL, DIGEST):
            assert session.get(lab.collector + "/collect", params={"uid": value}).status_code == 200
        assert session.get(lab.ads + "/ad").status_code == 200
        receipts = session.get(lab.site + "/receipts").json()
        assert receipts["count"] == 3
        assert receipts["receipts"] == [
            {"kind": "identifier", "representation": "raw", "transport": "url", "receiver": "collector"},
            {"kind": "identifier", "representation": "sha256", "transport": "url", "receiver": "collector"},
            {"kind": "popup_navigation"},
        ]
        assert session.get(lab.site + "/docs").status_code == 200
        assert lab.docs_served == 1


def test_unlisted_receivers_and_same_site_control_accept_only_synthetic_posts():
    with requests.Session() as session, GuardLab(0) as lab:
        session.trust_env = False
        assert session.post(lab.post_collector + "/collect", data={"uid": "not-the-demo"}).status_code == 400
        assert session.post(lab.post_collector + "/collect", data={"uid": EMAIL}).status_code == 200
        assert session.post(lab.site + "/same-site-submit", data={"uid": EMAIL}).status_code == 200
        assert session.get(lab.unlisted + "/collect", params={"uid": EMAIL}).status_code == 200
        receipts = session.get(lab.site + "/receipts").json()["receipts"]
        assert [(r["kind"], r["receiver"]) for r in receipts] == [
            ("identifier", "post_collector"), ("first_party_submit", "site"), ("identifier", "unlisted_url")]
        assert [r["transport"] for r in receipts] == ["body", "body", "url"]


def test_ad_click_redirector_and_advertiser_record_who_learned_the_click():
    with requests.Session() as session, GuardLab(0) as lab:
        session.trust_env = False
        # The user's browser: a click from the lab page carries its Referer.
        landed = session.get(lab.sponsored, headers={"Referer": lab.site + "/"})
        assert landed.url.startswith(lab.advertiser + "/landing?gclid=")
        # A clean visit, as Guard opens it: no click ID, no Referer.
        assert session.get(lab.advertiser + "/landing", params={"utm_source": "lab"}).status_code == 200
        receipts = session.get(lab.site + "/receipts").json()["receipts"]
        assert receipts == [
            {"kind": "ad_click", "from_user_page": True},
            {"kind": "advertiser_visit", "click_id": True, "from_user_page": True},
            {"kind": "advertiser_visit", "click_id": False, "from_user_page": False},
        ]
        # The sponsored link names its advertiser page, so Guard can skip the ad network.
        assert "adurl=" in lab.sponsored
