from analysis import score_sites


def fake_result(url):
    if "bad" in url:
        return {"ok": True, "assessment": {"level": "danger", "score": 70,
                                           "reasons": [{"code": "credential_form_cross_site"}, {"code": "card_form"}]},
                "redirect_chain": [url], "trackers": [], "third_parties": [], "third_party_countries": {}}
    if "ads" in url:
        return {"ok": True, "assessment": {"level": "caution", "score": 30,
                                           "reasons": [{"code": "trackers"}, {"code": "offshore"}, {"code": "trackers"}]},
                "redirect_chain": [url, url + "/home"], "trackers": [{"domain": "t.example", "owner": "Google"}],
                "third_parties": ["t.example", "u.example", "v.example"], "third_party_countries": {"t.example": "US",
                                                                                                    "u.example": "AU"}}
    if "down" in url:
        raise ConnectionError("unreachable")
    return {"ok": True, "assessment": {"level": "low", "score": 0, "reasons": []}, "redirect_chain": [url],
            "trackers": [], "third_parties": [], "third_party_countries": {}, "screenshot_jpeg_b64": "QUJD"}


def test_rows_summary_and_report_count_false_alarms_and_failures(tmp_path):
    (tmp_path / "sites.yaml").write_text("sectors:\n  government:\n    - https://gov.example\n    - https://bad.example\n"
                                         "  news_media:\n    - https://ads.example  # popular\n    - https://down.example\n")
    sites = score_sites.load_sites(tmp_path / "sites.yaml")
    assert sites[2] == ("news_media", "https://ads.example")
    assert score_sites.load_sites(tmp_path / "sites.yaml", "news_media") == sites[2:]
    seen = []
    rows = score_sites.run(sites, fake_result, pause=0, progress=seen.append)
    assert len(seen) == 4 and "danger" in seen[1]
    assert rows[2]["hops"] == 1 and rows[2]["countries"] == ["AU", "US"] and rows[2]["offshore"] is True
    assert rows[3]["level"] == "unknown" and "ConnectionError" in rows[3]["error"]
    assert "screenshot_jpeg_b64" not in rows[0]  # pictures are never kept
    s = score_sites.summarise(rows)
    assert s["levels"] == {"low": 1, "caution": 1, "danger": 1, "unknown": 1}
    assert s["false_alarms"] == [{"url": "https://bad.example", "score": 70,
                                  "reasons": ["credential_form_cross_site", "card_form"]}]
    assert s["by_sector"]["government"]["danger"] == 1 and s["by_sector"]["news_media"]["offshore_sites"] == 1
    assert dict(s["reason_sites"])["trackers"] == 1  # counted once per site
    assert s["offshore_countries"] == [("US", 1)] and s["tracker_owners"] == [("Google", 1)]
    text = score_sites.render(s, {"finished": "2026-10-28 01:00 UTC", "sandbox_host": "Lab", "resolvers": ["1.1.1.1"]})
    assert "False alarms (Dangerous): **1**" in text and "| Dangerous | 1 | 25% |" in text
    assert "https://down.example: ConnectionError" in text and "DNS: 1.1.1.1" in text
