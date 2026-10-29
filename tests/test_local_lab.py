import httpx

from examples.demo_lab import DIGEST, Lab


def test_loopback_lab_serves_two_pages_and_records_only_the_demo_hash():
    with Lab("before", base_port=0) as lab, httpx.Client(trust_env=False) as client:
        for origin in lab.origins:
            page = client.get(origin)
            assert page.status_code == 200
            assert "crypto.subtle.digest" in page.text
            assert "http://127.0.0.2:" in page.text
        assert client.get(lab.collector_url + "/collect?uid=unrelated").status_code == 400
        response = client.get(lab.collector_url + "/collect?uid=" + DIGEST,
                              headers={"Origin": lab.origins[0]})
        assert response.json()["received"] is True
        assert response.headers["access-control-allow-origin"] == lab.origins[0]
        assert len(lab.received) == 1


def test_after_page_removes_the_identifier_sending_integration():
    with Lab("after", base_port=0) as lab, httpx.Client(trust_env=False) as client:
        page = client.get(lab.origins[0])
        assert "crypto.subtle.digest" not in page.text
        assert "No collector request was made" in page.text
        assert lab.received == []
