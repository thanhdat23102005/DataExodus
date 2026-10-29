import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from pi import portal

PHONE, VISITOR = ("10.42.0.23", 50000), ("10.42.0.77", 50001)
SHOT = "aGVsbG8="  # base64 "hello": stands in for a JPEG


class FakeGuard:
    """The sandbox service on 127.0.0.1:8010, as the portal sees it."""

    def __init__(self):
        self.calls = []
        self.busy = False

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if path == "/sandbox/preview":
            url = kwargs["json"]["url"]
            return Reply(200, {
                "ok": True, "requested_url": url, "final_url": url, "redirect_chain": [url, "https://landing.example/<b>"],
                "clean_url": "https://landing.example/p", "title": "<script>alert(1)</script>",
                "screenshot_jpeg_b64": SHOT, "trackers": [{"domain": "px.tracker.example", "owner": "Tracker <Co>",
                                                          "country": "US"}],
                "third_parties": ["tracker.example"], "signals": ["notification_prompt"], "downloads": [],
                "popups": 0, "dialogs": 0, "classifier_available": True, "sandbox_host": "dataexodus",
                "assessment": {"score": 72, "level": "danger", "label": "Dangerous", "note": "One visit.",
                               "reasons": [{"code": "x", "points": 40, "text": "Did <something> bad"}]}})
        if path == "/sandbox/browse" and method == "POST":
            return Reply(503, {}) if self.busy else Reply(200, self.state("https://start.example/"))
        if path.startswith("/sandbox/browse/"):
            if method == "DELETE":
                return Reply(200, {"closed": True})
            if path.endswith("gone-session-0000000"):
                return Reply(404, {})
            return Reply(200, self.state("https://after.example/"))
        raise AssertionError(path)

    @staticmethod
    def state(url):
        return {"ok": True, "id": "sess-abcdefghijklmnop", "url": url, "title": "t", "screenshot_jpeg_b64": SHOT,
                "width": 360, "height": 640, "signals": ["clipboard_write"], "downloads": ["x.apk"], "popups": 1,
                "dialogs": 0, "third_party_sites": 2, "expires_in": 100, "sandbox_host": "dataexodus"}


class Reply:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, value in {"PORTAL_IP": "10.42.0.1", "PORTAL_PORT": "80", "PORTAL_NET": "10.42.0.0/24",
                       "PORTAL_HOSTNAME": "dataexodus.home.arpa", "PORTAL_DEVICES": str(tmp_path / "devices.json"),
                       "DNSWATCH_DB": str(tmp_path / "dns.sqlite"), "BLOCKLIST_DIR": str(tmp_path / "none"),
                       "DATAEXODUS_STATE": str(tmp_path), "PORTAL_SAMPLES": "1", "PORTAL_RETENTION_HOURS": "24"}.items():
        monkeypatch.setenv(key, value)
    portal._devices.clear()
    portal.JOBS.clear()
    portal.SESSIONS.clear()
    portal.RATE.clear()
    fake = FakeGuard()
    monkeypatch.setattr(portal, "guard", fake)
    # Run link checks inline instead of on the thread pool.
    monkeypatch.setattr(portal, "POOL", type("Inline", (), {"submit": staticmethod(lambda fn, *a: fn(*a))})())
    return fake


def device(client=PHONE, **kwargs):
    return TestClient(portal.app, base_url="http://10.42.0.1", client=client, follow_redirects=False, **kwargs)


def join(c, watch=True, block=False):
    data = {"watch": "1"} if watch else {}
    if block:
        data["block"] = "1"
    r = c.post("/join", data=data, headers={"Origin": "http://10.42.0.1"})
    assert r.status_code == 303
    return r


def test_only_hotspot_devices_and_the_portals_own_names(env):
    assert TestClient(portal.app, base_url="http://10.42.0.1", client=("192.168.1.5", 1)).get("/").status_code == 403
    with device() as c:
        assert c.get("/").status_code == 200
        assert c.get("/", headers={"Host": "dataexodus.home.arpa"}).status_code == 200
        assert c.get("/", headers={"Host": "attacker.example"}).status_code == 403  # DNS rebinding
        page = c.get("/")
        csp = page.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "script-src" not in csp and "form-action 'self'" in csp
        assert "<script" not in page.text and page.headers["x-frame-options"] == "DENY"
        # "no-referrer" would make browsers send Origin: null on the portal's own forms.
        assert page.headers["referrer-policy"] == "same-origin"


def test_cross_site_form_posts_are_refused(env):
    with device() as c:
        assert c.post("/join", data={"watch": "1"}, headers={"Origin": "http://evil.example"}).status_code == 403
        assert c.post("/join", data={"watch": "1"}, headers={"Origin": "null"}).status_code == 403
        assert c.post("/join", data={"watch": "1"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert portal.devices().all() == {}
        join(c)
        assert list(portal.devices().all()) == ["ip:10.42.0.23"]


def test_captive_portal_probes_redirect_until_the_visitor_chooses(env):
    with device() as c:
        probe = c.get("/generate_204", headers={"Host": "connectivitycheck.gstatic.com"})
        assert probe.status_code == 302 and probe.headers["location"] == "http://10.42.0.1/"
        apple = c.get("/hotspot-detect.html", headers={"Host": "captive.apple.com"})
        assert apple.status_code == 302
        welcome = c.get("/")
        assert "Welcome to the DataExodus Wi-Fi" in welcome.text and "Join and continue" in welcome.text
        join(c, watch=False)
        assert c.get("/generate_204", headers={"Host": "connectivitycheck.gstatic.com"}).status_code == 204
        assert "Success" in c.get("/hotspot-detect.html", headers={"Host": "captive.apple.com"}).text
        assert c.get("/connecttest.txt", headers={"Host": "www.msftconnecttest.com"}).text == "Microsoft Connect Test"
        assert "You're online" in c.get("/").text
    with device(VISITOR) as other:  # another phone has not chosen yet
        assert other.get("/generate_204", headers={"Host": "connectivitycheck.gstatic.com"}).status_code == 302


def test_link_check_is_private_to_the_device_and_escapes_everything(env):
    with device() as c:
        assert c.get("/check").status_code == 303  # choose on the welcome page first
        join(c)
        sms = "Your parcel is held. Pay the fee at https://parcel-help.example/pay?id=7 within 24 hours."
        r = c.post("/check", data={"text": sms}, headers={"Origin": "http://10.42.0.1"})
        assert r.status_code == 303
        result_url = r.headers["location"]
        assert env.calls[-1] == ("POST", "/sandbox/preview", {"url": "https://parcel-help.example/pay?id=7"})
        page = c.get(result_url).text
        assert "Dangerous" in page and "Score 72 / 100" in page and "+40" in page
        assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
        assert "Did &lt;something&gt; bad" in page and "Tracker &lt;Co&gt;" in page
        assert f"data:image/jpeg;base64,{SHOT}" in page
        assert "Open clean link" not in page  # never offered for a dangerous result
        assert "Asked to send notifications" in page
    with device(VISITOR) as other:
        join(other)
        assert other.get(result_url).headers["location"] == "/check?error=gone"


def test_clean_link_button_only_for_low_risk_public_sites(env, monkeypatch):
    def low(method, path, **kwargs):
        url = kwargs["json"]["url"]
        return Reply(200, {"ok": True, "requested_url": url, "final_url": url, "redirect_chain": [url],
                           "clean_url": url, "assessment": {"score": 0, "level": "low", "label": "Low risk",
                                                            "reasons": [], "note": "n"}})
    monkeypatch.setattr(portal, "guard", low)
    with device() as c:
        join(c)
        public = c.get(c.post("/check", data={"text": "https://news.example/a"}).headers["location"]).text
        assert "Open clean link</a>" in public and "rel='noopener noreferrer'" in public
        lab = c.get(c.post("/check", data={"text": "http://127.0.0.49:8030/2026/x"}).headers["location"]).text
        assert "Open clean link</a>" not in lab and "exist only inside the Pi" in lab


def test_pasted_text_without_a_link_and_rate_limits(env):
    with device() as c:
        join(c)
        assert c.post("/check", data={"text": "hello there"}).headers["location"] == "/check?error=url"
        assert c.post("/check", data={"text": "file:///etc/passwd"}).headers["location"] == "/check?error=url"
        assert c.post("/check", data={"text": "example.org/path"}).status_code == 303
        assert env.calls[-1][2] == {"url": "https://example.org/path"}
        for _ in range(11):
            c.post("/check", data={"text": "https://example.org/"})
        assert c.post("/check", data={"text": "https://example.org/"}).headers["location"] == "/check?error=busy"


def test_samples_are_listed_with_their_local_lab_links(env):
    with device() as c:
        join(c)
        page = c.get("/check").text
        assert "Try a sample" in page and "http://127.0.0.56:8030" not in page  # the bank sits behind the short link
        assert "http://127.0.0.55:8030/s/kb7Q" in page and "http://127.0.0.58:8030/verify" in page


def test_safe_browse_taps_scrolls_types_and_ends(env):
    with device() as c:
        join(c)
        start = c.post("/browse", data={"text": "https://start.example/"})
        assert start.headers["location"] == "/browse/sess-abcdefghijklmnop"
        page = c.get(start.headers["location"]).text
        assert "type=image name=tap width=360 height=640" in page
        assert "Wrote to the clipboard" in page and "x.apk" in page
        c.post("/browse/sess-abcdefghijklmnop", data={"tap.x": "9999", "tap.y": "-5"})
        assert env.calls[-1] == ("POST", "/sandbox/browse/sess-abcdefghijklmnop", {"action": "tap", "x": 359, "y": 0})
        c.post("/browse/sess-abcdefghijklmnop", data={"do": "down"})
        assert env.calls[-1][2] == {"action": "scroll", "dy": 450}
        c.post("/browse/sess-abcdefghijklmnop", data={"do": "type", "text": "hello"})
        assert env.calls[-1][2] == {"action": "type", "text": "hello"}
        c.post("/browse/sess-abcdefghijklmnop", data={"do": "refresh"})
        assert env.calls[-1][:2] == ("GET", "/sandbox/browse/sess-abcdefghijklmnop")
        assert "after.example" in c.get("/browse/sess-abcdefghijklmnop").text
    with device(VISITOR) as other:  # someone else's session is not reachable
        join(other)
        assert other.get("/browse/sess-abcdefghijklmnop").headers["location"] == "/check?error=gone"
        assert other.post("/browse/sess-abcdefghijklmnop", data={"do": "end"}).headers["location"] == "/check?error=gone"
    with device() as c:
        assert c.post("/browse/sess-abcdefghijklmnop", data={"do": "end"}).headers["location"] == "/check"
        assert env.calls[-1][:2] == ("DELETE", "/sandbox/browse/sess-abcdefghijklmnop")
        env.busy = True
        assert c.post("/browse", data={"text": "https://x.example/"}).headers["location"] == "/check?error=browse"


def make_dns(path, rows):
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE queries (ts INTEGER, client TEXT, qname TEXT, qtype TEXT, rcode TEXT, "
                      "answers TEXT, blocked INTEGER, listed TEXT, device TEXT)")
    con.executemany("INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_my_device_shows_only_this_devices_lookups_and_forget_deletes_them(env, tmp_path):
    with device() as c:
        join(c, watch=True, block=True)
        now = int(time.time())
        make_dns(tmp_path / "dns.sqlite", [
            (now, PHONE[0], "api.<b>app</b>.example", "A", "NOERROR", json.dumps(["8.8.8.8"]), 0, None, "ip:10.42.0.23"),
            (now + 1, PHONE[0], "px.tracker.example", "A", "NOERROR", "[]", 1, "tracker.example", "ip:10.42.0.23"),
            (now + 1, VISITOR[0], "someone-else.example", "A", "NOERROR", "[]", 0, None, "ip:10.42.0.77"),
            # Before monitoring was switched on for this device: not shown.
            (now - 60, PHONE[0], "too-old.example", "A", "NOERROR", "[]", 0, None, "ip:10.42.0.23"),
        ])
        page = c.get("/me").text
        assert "api.&lt;b&gt;app&lt;/b&gt;.example" in page and "px.tracker.example" in page
        assert "someone-else.example" not in page and "too-old.example" not in page
        assert "badge blocked" in page and "http-equiv=refresh" in page
        assert "http-equiv=refresh" not in c.get("/me?live=0").text
        c.post("/me", data={})  # switch both off
        assert portal.devices().all()["ip:10.42.0.23"]["watch"] is False
        assert "nothing is recorded" in c.get("/me").text
        assert c.post("/forget").headers["location"] == "/"
        left = sqlite3.connect(tmp_path / "dns.sqlite").execute("SELECT qname FROM queries").fetchall()
        assert left == [("someone-else.example",)]
        assert portal.devices().all() == {}
        assert "Join and continue" in c.get("/").text


def test_danger_buttons_keep_white_text():
    # .danger (banners) sets red text; on a red button that made "End" and
    # "Forget this device" invisible in the real-browser screenshots.
    # button.danger is more specific than .danger, so its colour wins.
    assert "button.danger{background:var(--danger);color:#fff}" in portal.CSS


def test_about_page_lists_every_scoring_rule(env):
    from protection.verdict import RULES
    with device() as c:
        page = c.get("/about").text
        assert all(text.split("(")[0][:40].replace('"', "&quot;") in page for _, text in RULES.values())
