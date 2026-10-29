import requests

from examples.sample_links import CLIPBOARD_TEXT, SampleLinks, samples


def get(session, url, **kwargs):
    return session.get(url, allow_redirects=False, timeout=5, **kwargs)


def test_samples_cross_real_origins_and_stay_harmless():
    with requests.Session() as session, SampleLinks(0) as lab:
        session.trust_env = False  # loopback only, never a proxy
        by_id = {s["id"]: s for s in lab.samples()}
        assert set(by_id) == {"news", "deal", "bank", "captcha"}
        news = get(session, by_id["news"]["url"])
        assert news.status_code == 200 and "Harbour City Times" in news.text and "http://" not in news.text.split("<main>")[1]
        ad = get(session, by_id["deal"]["url"])
        assert ad.status_code == 302 and ad.headers["Location"].startswith(lab.origin["shop"] + "/deal/headphones?gclid=")
        assert get(session, lab.origin["ads"] + "/aclk?adurl=http://example.com/").status_code == 404  # no open redirect
        deal = get(session, ad.headers["Location"])
        assert lab.origin["pixel"] in deal.text and "Notification.requestPermission" in deal.text
        short = get(session, by_id["bank"]["url"])
        assert short.status_code == 302 and short.headers["Location"].startswith(lab.origin["bank"])
        bank = get(session, short.headers["Location"])
        assert f"action='{lab.origin['collector']}/collect'" in bank.text and "type=password" in bank.text
        assert "Fictional brand" in bank.text
        posted = session.post(lab.origin["collector"] + "/collect", data={"password": "hunter2"}, timeout=5)
        assert posted.status_code == 200 and "hunter2" not in posted.text and lab.form_posts == 1
        captcha = get(session, by_id["captcha"]["url"])
        assert "navigator.clipboard.writeText" in captcha.text and CLIPBOARD_TEXT.startswith("echo ")
        download = get(session, lab.origin["captcha"] + "/download/browser_update.exe")
        assert download.headers["Content-Disposition"].startswith("attachment") and b"not a program" in download.content


def test_the_portal_list_uses_the_fixed_service_port():
    urls = [s["url"] for s in samples(port=8030)]
    assert urls[0].startswith("http://127.0.0.49:8030/") and urls[2] == "http://127.0.0.55:8030/s/kb7Q"
    assert [s["expect"] for s in samples()] == ["low", "caution", "danger", "danger"]
