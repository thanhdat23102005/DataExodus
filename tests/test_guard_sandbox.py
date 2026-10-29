import asyncio

import pytest
from fastapi.testclient import TestClient

from protection import api, sandbox

TOKEN = "local-test-token-not-a-real-key-12345"
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATAEXODUS_GUARD_TOKEN", TOKEN)
    with TestClient(api.app) as client:
        yield client


@pytest.mark.parametrize("url,network", [
    ("https://www.googleadservices.com/pagead/aclk?sa=L&ai=abc", "Google Ads"),
    ("https://ad.doubleclick.net/ddm/clk/123;456", "Google Ads"),
    ("https://www.google.com.au/aclk?sa=l&ai=xyz", "Google Search ad"),
    ("https://www.bing.com/aclick?ld=e8", "Microsoft Ads"),
    ("https://paid.outbrain.com/network/redir?p=1", "Outbrain"),
    ("https://www.google.com/search?q=aclk", None),
    ("https://www.abc.net.au/news", None),
])
def test_ad_click_detection(url, network):
    assert sandbox.match_ad_click(url) == network


def test_clean_url_strips_click_ids_only():
    url = "https://shop.example.com/p/1?id=7&gclid=abc&utm_source=g&fbclid=x&msclkid=y"
    assert sandbox.clean_url(url) == "https://shop.example.com/p/1?id=7"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8010/health", "http://localhost/", "http://192.168.1.1/admin", "http://10.0.0.5/",
    "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "javascript:alert(1)",
])
def test_sandbox_refuses_non_public_addresses(url, monkeypatch):
    monkeypatch.delenv("SANDBOX_ALLOW_HOSTS", raising=False)
    assert sandbox.is_public_url(url) is False


def test_lab_host_allowlist_is_explicit_and_exact(monkeypatch):
    monkeypatch.setenv("SANDBOX_ALLOW_HOSTS", "127.0.0.3")
    assert sandbox.is_public_url("http://127.0.0.3:5000/aclk") is True
    assert sandbox.is_public_url("http://127.0.0.1:8010/health") is False


def test_sample_link_range_is_allowed_only_inside_its_network(monkeypatch):
    monkeypatch.setenv("SANDBOX_ALLOW_HOSTS", "127.0.0.48/28")
    assert sandbox.is_public_url("http://127.0.0.49:8030/x") and sandbox.is_public_url("http://127.0.0.58:8030/x")
    for url in ("http://127.0.0.1:8010/health", "http://127.0.0.64:8030/", "http://10.42.0.23/", "http://[::1]/"):
        assert sandbox.is_public_url(url) is False, url
    assert sandbox.match_ad_click("http://127.0.0.50:8030/aclk?adurl=x") == "Sample ad network (local lab)"
    assert sandbox.match_ad_click("http://127.0.0.51:8030/deal") is None


def test_urlhaus_hosts_are_matched_with_their_subdomains(tmp_path, monkeypatch):
    (tmp_path / "urlhaus_hosts.txt").write_text("# URLhaus\n0.0.0.0 malware.example\nbad.example.net\n")
    monkeypatch.setenv("BLOCKLIST_DIR", str(tmp_path))
    assert sandbox.known_threats({"cdn.malware.example", "bad.example.net", "fine.example", ""}) == [
        "bad.example.net", "cdn.malware.example"]


def test_safe_browse_endpoints_validate_input_and_report_busy(client, monkeypatch):
    calls = []

    async def start(url):
        calls.append(("start", url))
        raise sandbox.SandboxBusy()

    async def act(sid, **action):
        calls.append(("act", sid, action))
        return None if sid.startswith("gone") else {"ok": True, "id": sid}

    async def state(sid):
        return {"ok": True, "id": sid}

    async def close(sid):
        return True

    monkeypatch.setattr(sandbox, "browse_start", start)
    monkeypatch.setattr(sandbox, "browse_act", act)
    monkeypatch.setattr(sandbox, "browse_state", state)
    monkeypatch.setattr(sandbox, "browse_close", close)
    assert client.post("/sandbox/browse", json={"url": "https://example.com/"}).status_code == 401
    assert client.post("/sandbox/browse", json={"url": "https://example.com/"}, headers=HEADERS).status_code == 503
    sid = "abcdefghijklmnopqrst"
    ok = client.post(f"/sandbox/browse/{sid}", json={"action": "tap", "x": 10, "y": 20}, headers=HEADERS)
    assert ok.status_code == 200 and calls[-1] == ("act", sid, {"action": "tap", "x": 10, "y": 20})
    for bad in ({"action": "eval", "text": "1"}, {"action": "tap", "x": -1}, {"action": "key", "key": "F12"},
                {"action": "type", "text": "x" * 201}, {"action": "tap", "x": 1, "extra": 1}):
        assert client.post(f"/sandbox/browse/{sid}", json=bad, headers=HEADERS).status_code == 422, bad
    assert client.post("/sandbox/browse/short", json={"action": "back"}, headers=HEADERS).status_code == 422
    assert client.post("/sandbox/browse/gone-abcdefghijklmnop", json={"action": "back"},
                       headers=HEADERS).status_code == 404
    assert client.get(f"/sandbox/browse/{sid}", headers=HEADERS).json() == {"ok": True, "id": sid}
    assert client.delete(f"/sandbox/browse/{sid}", headers=HEADERS).json() == {"closed": True}


def test_safe_browse_refuses_internal_addresses_before_launching(monkeypatch):
    monkeypatch.delenv("SANDBOX_ALLOW_HOSTS", raising=False)
    result = asyncio.run(sandbox.browse_start("http://192.168.1.1/"))
    assert result["ok"] is False and "public" in result["error"] and sandbox._browse == {}


def test_preview_endpoint_requires_token_and_valid_url(client, monkeypatch):
    calls = []

    async def fake_preview(url):
        calls.append(url)
        return {"ok": True, "final_url": url}

    monkeypatch.setattr(sandbox, "preview", fake_preview)
    assert client.post("/sandbox/preview", json={"url": "https://example.com/"}).status_code == 401
    for bad in ({"url": "file:///etc/passwd"}, {"url": "https://user:pw@example.com/"},
                {"url": "https://example.com/", "extra": 1}):
        assert client.post("/sandbox/preview", json=bad, headers=HEADERS).status_code == 422
    r = client.post("/sandbox/preview", json={"url": "https://example.com/a#secret"}, headers=HEADERS)
    assert r.status_code == 200
    assert calls == ["https://example.com/a"]  # fragment never leaves the browser


def test_preview_refuses_internal_before_launching_browser(monkeypatch):
    monkeypatch.delenv("SANDBOX_ALLOW_HOSTS", raising=False)
    monkeypatch.setenv("DATAEXODUS_HOST_LABEL", "dataexodus-pi")
    result = asyncio.run(sandbox.preview("http://192.168.1.1/"))
    assert result == {"ok": False, "error": "Only public http(s) URLs can be opened in the sandbox.",
                      "sandbox_host": "dataexodus-pi"}


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True), ("100.64.0.1", False), ("::ffff:192.168.1.1", False), ("::ffff:8.8.8.8", True),
    ("fd00::1", False), ("fe80::1", False), ("0.0.0.0", False), ("224.0.0.1", False),
])
def test_public_ip_rules_cover_cgnat_mapped_and_ula(ip, public):
    assert sandbox.is_public_ip(ip) is public


def test_pi_browser_settings_come_from_the_environment(monkeypatch):
    launched = {}

    class Chromium:
        async def launch(self, **options):
            launched.update(options)

    class P:
        chromium = Chromium()

    monkeypatch.setenv("CHROMIUM_PATH", "/usr/bin/chromium")
    monkeypatch.setenv("DATAEXODUS_CHROMIUM_SANDBOX", "1")
    asyncio.run(sandbox._launch(P()))
    assert launched == {"headless": True, "chromium_sandbox": True, "executable_path": "/usr/bin/chromium"}
    monkeypatch.delenv("CHROMIUM_PATH")
    monkeypatch.delenv("DATAEXODUS_CHROMIUM_SANDBOX")
    launched.clear()
    asyncio.run(sandbox._launch(P()))
    assert launched == {"headless": True, "chromium_sandbox": False}
