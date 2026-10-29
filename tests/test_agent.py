import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pipeline import agent


def test_live_ingestion_validation_and_exact_site_scope(tmp_path, monkeypatch):
    blocklists = tmp_path / "lists"
    blocklists.mkdir()
    (blocklists / "easyprivacy.txt").write_text("||telemetry.example.net^\n")
    (blocklists / "tracker_radar.json").write_text(json.dumps({"telemetry.example.net": {"owner": "Example Analytics", "category": "analytics"}}))
    identities = tmp_path / "identities.yaml"
    identities.write_text("email: [student.demo@example.com]\nphone: []\n")
    monkeypatch.setattr(agent, "DB_PATH", tmp_path / "live.duckdb")
    monkeypatch.setenv("BLOCKLIST_DIR", str(blocklists))
    monkeypatch.setenv("GEOIP_MMDB", str(tmp_path / "missing.mmdb"))
    monkeypatch.setenv("IDENTITIES_PATH", str(identities))
    digest = hashlib.sha256(b"student.demo@example.com").hexdigest()
    with TestClient(agent.app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/").status_code == 200
        assert client.post("/ingest", json={"events": [{"url": None}]}).status_code == 422
        assert client.post("/ingest", json={"events": [{"url": "file:///tmp/a"}]}).status_code == 422
        response = client.post("/ingest", json={"events": [{
            "url": "https://telemetry.example.net/pixel?uid=" + digest,
            "initiator": "https://shop.example.com", "type": "image", "ts": 1792627200000,
        }]})
        assert response.json()["queued"] == 1
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            summary = client.get("/summary").json()
            if summary["total_requests"] == 1:
                break
            time.sleep(0.02)
        assert summary["tracker_requests"] == 1
        assert summary["pii_requests"] == 1
        assert summary["offshore_requests"] == 0
        assert summary["unknown_country_requests"] == 1
        assert client.get("/recent").json()[0]["ts"] == 1792627200
        assert client.get("/site/shop.example.com").json()["requests"] == 1
        assert client.get("/site/example.com").json()["requests"] == 0
        assert client.get("/recent?limit=-1").status_code == 422


def test_other_websites_cannot_read_history_or_listen_live(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "DB_PATH", tmp_path / "live.duckdb")
    monkeypatch.setenv("BLOCKLIST_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("IDENTITIES_PATH", str(tmp_path / "none.yaml"))
    with TestClient(agent.app, base_url="http://127.0.0.1:8000") as client:
        # Any page you visit could otherwise fetch these from localhost.
        assert client.get("/recent", headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get("/summary", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"}).status_code == 403
        # DNS rebinding: evil.example resolving to 127.0.0.1 still sends its own Host.
        assert client.get("/recent", headers={"Host": "evil.example:8000"}).status_code == 403
        # The extension, the agent's own dashboard and non-browser tools still work.
        assert client.get("/summary", headers={"Origin": "chrome-extension://abcdefghijklmnop"}).status_code == 200
        assert client.get("/summary", headers={"Origin": "http://127.0.0.1:8000"}).status_code == 200
        assert client.get("/summary").status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://127.0.0.1:8000/live", headers={"Origin": "https://evil.example"}) as ws:
                ws.receive_text()
        with client.websocket_connect("ws://127.0.0.1:8000/live", headers={"Origin": "http://127.0.0.1:8000"}):
            pass