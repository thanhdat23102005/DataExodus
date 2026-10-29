import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from pi import box, dns_report, study_run


class FakeGeo:
    def country(self, ip):
        if ip.startswith("10."):
            raise ValueError("private")
        return type("R", (), {"country": type("C", (), {"iso_code": "AU" if ip.startswith("1.") else "US"})()})()


class FakeClassifier:
    reference_files = ["easyprivacy.txt"]
    geoip = FakeGeo()

    def label(self, name):
        tracker = "tracker" in name
        return {"is_tracker": tracker, "owner": "Tracker Co <script>" if tracker else None, "category": None}


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE queries (ts INTEGER, client TEXT, qname TEXT, qtype TEXT, rcode TEXT, answers TEXT, blocked INTEGER, listed TEXT)")
    now = int(time.time())
    con.executemany("INSERT INTO queries VALUES (?,?,?,?,?,?,?,?)",
                    [(now - age, client, name, "A", "NOERROR", json.dumps(ips), blocked, None)
                     for age, client, name, ips, blocked in rows])
    con.commit()
    con.close()


def test_summary_counts_owners_countries_and_keeps_unknown_unknown(tmp_path):
    db = tmp_path / "dns.sqlite"
    make_db(db, [(60, "192.168.1.5", "px.tracker.example", ["8.8.8.8"], 0),
                 (60, "192.168.1.5", "px.tracker.example", ["0.0.0.0"], 1),
                 (60, "192.168.1.9", "news.example.au", ["1.2.3.4"], 0),
                 (60, "192.168.1.9", "intranet.example", ["10.0.0.4"], 0),
                 (90000, "192.168.1.9", "old.tracker.example", ["8.8.8.8"], 0)])
    s = dns_report.summarise(db, hours=24, classifier=FakeClassifier())
    assert s["queries"] == 4 and s["blocked"] == 1 and s["tracker_queries"] == 2
    assert s["owners"] == [("Tracker Co <script>", 2)]
    # 0.0.0.0 (a block answer) and the private address are not located.
    assert s["located_answers"] == 2 and s["offshore_answers"] == 1
    assert dict(s["countries"]) == {"US": 1, "AU": 1}
    html = dns_report.render(s)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert dns_report.summarise(tmp_path / "missing.sqlite") == {"available": False, "hours": 24}


def test_hotspot_visitors_lookups_never_reach_the_owners_summary(tmp_path):
    db = tmp_path / "dns.sqlite"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE queries (ts INTEGER, client TEXT, qname TEXT, qtype TEXT, rcode TEXT, answers TEXT, "
                      "blocked INTEGER, listed TEXT, device TEXT)")
    now = int(time.time())
    con.executemany("INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?)", [
        (now, "192.168.1.5", "owners-phone.example", "A", "NOERROR", "[]", 0, None, None),
        (now, "10.42.0.23", "visitor-private.example", "A", "NOERROR", "[]", 0, None, "mac:aa:bb")])
    con.commit()
    con.close()
    owner = dns_report.summarise(db, classifier=False, recent=10)
    assert owner["queries"] == 1 and [r["name"] for r in owner["recent"]] == ["owners-phone.example"]
    assert "10.42.0.23" not in dict(owner["clients"])
    visitor = dns_report.summarise(db, classifier=False, device="mac:aa:bb", recent=10)
    assert [r["name"] for r in visitor["recent"]] == ["visitor-private.example"]


def test_summary_without_reference_data_says_unavailable_not_zero(tmp_path):
    db = tmp_path / "dns.sqlite"
    make_db(db, [(60, "192.168.1.5", "px.tracker.example", ["8.8.8.8"], 0)])
    s = dns_report.summarise(db, classifier=False)
    assert s["reference_lists"] is False and s["geoip"] is False
    assert "unavailable, not zero" in dns_report.render(s)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAEXODUS_STATE", str(tmp_path))
    monkeypatch.setenv("BLOCKLIST_DIR", str(tmp_path / "blocklists"))
    monkeypatch.setattr(box, "guard_status", lambda: {"running": False})
    run = tmp_path / "runs" / "20261025T0300Z"
    (run / "audit").mkdir(parents=True)
    (run / "raw").mkdir()
    (run / "raw" / "s.json").write_text("{\"secret\": 1}")
    (run / "audit" / "audit.html").write_text("<h1>audit</h1>")
    (run / "status.json").write_text(json.dumps({"ok": True, "sessions": 50, "baseline": None, "steps": []}))
    (tmp_path / "secret.txt").write_text("nope")
    with TestClient(box.app, base_url="http://127.0.0.1:8020") as c:
        yield c


def test_dashboard_is_local_only_and_hardened(client):
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 403
    page = client.get("/")
    assert page.status_code == 200
    assert "20261025T0300Z" in page.text and "50 sites" in page.text and "not running" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert client.get("/dns?hours=100000").status_code == 200
    assert client.get("/api/status").json()["runs"][0]["links"] == ["audit/audit.html"]


def test_dashboard_serves_reports_but_not_raw_captures_or_other_files(client):
    report = client.get("/runs/20261025T0300Z/audit/audit.html")
    assert report.status_code == 200 and "sandbox allow-scripts" in report.headers["content-security-policy"]
    for path in ("/runs/20261025T0300Z/raw/s.json", "/runs/20261025T0300Z/status.json/../../../secret.txt",
                 "/runs/..%2F..%2Fsecret.txt/x", "/runs/20261025T0300Z/../../secret.txt"):
        assert client.get(path).status_code == 404, path


def test_wifi_card_has_join_and_portal_qr_codes_and_status_hides_the_password(client, monkeypatch, tmp_path):
    assert "not set up" in client.get("/card").text
    monkeypatch.setenv("HOTSPOT_SSID", "DataExodus-Box")
    monkeypatch.setenv("HOTSPOT_PSK", "abcd-efgh-<jk>")
    monkeypatch.setenv("HOTSPOT_LEASES", str(tmp_path / "leases"))
    (tmp_path / "leases").write_text("1761500000 aa:bb:cc:00:00:01 10.42.0.23 phone *\n")
    card = client.get("/card")
    assert card.status_code == 200 and card.text.count("src='data:image/svg+xml") == 2
    assert "abcd-efgh-&lt;jk&gt;" in card.text and "http://10.42.0.1" in card.text
    status = client.get("/api/status").json()["hotspot"]
    assert status["ssid"] == "DataExodus-Box" and status["connected"] == 1 and "psk" not in status
    assert "1 connected" in client.get("/").text


def fake_steps(monkeypatch, fail_at=None):
    calls = []

    def run(cmd, cwd, stdout, stderr, env=None):
        assert env is None or env.get("PYTHONUNBUFFERED") == "1"
        module, args = cmd[2], cmd[3:]
        calls.append((module, args))
        if module == "crawler.crawl":
            raw = args[args.index("--output") + 1]
            __import__("pathlib").Path(raw).mkdir(parents=True)
            (__import__("pathlib").Path(raw) / "a.json").write_text("{}")
        if module == "analysis.audit":
            out = __import__("pathlib").Path(args[args.index("--out") + 1])
            out.mkdir(parents=True)
            (out / "audit.json").write_text("{}")
        return type("P", (), {"returncode": 1 if module == fail_at else 0})()

    monkeypatch.setattr(study_run.subprocess, "run", run)
    return calls


def test_study_runs_compare_with_the_previous_good_run_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAEXODUS_STATE", str(tmp_path))
    stamps = iter(["20261001T0300Z", "20261008T0300Z", "20261015T0300Z"])

    class Clock:
        @staticmethod
        def now(tz=None):
            # One run directory name per run; the finish time is not a name.
            return type("D", (), {"strftime": lambda self, fmt: next(stamps, "20261022T0300Z")
                                  if fmt == "%Y%m%dT%H%MZ" else "finished"})()

    monkeypatch.setattr(study_run, "datetime", Clock)
    calls = fake_steps(monkeypatch)
    first = study_run.run(keep=2)
    assert first["ok"] and first["baseline"] is None and first["sessions"] == 1
    second = study_run.run(keep=2)
    audit_args = calls[-1][1]
    assert second["baseline"] == "20261001T0300Z"
    assert audit_args[audit_args.index("--baseline") + 1].endswith("20261001T0300Z\\audit\\audit.json") or \
        audit_args[audit_args.index("--baseline") + 1].endswith("20261001T0300Z/audit/audit.json")
    study_run.run(keep=2)
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == ["20261008T0300Z", "20261015T0300Z"]


def test_each_run_records_the_dns_resolvers_it_used(tmp_path, monkeypatch):
    conf = tmp_path / "resolv.conf"
    conf.write_text("# Generated by NetworkManager\nnameserver 1.1.1.1\nnameserver 1.0.0.1\noptions edns0\n")
    assert study_run.resolvers(conf) == ["1.1.1.1", "1.0.0.1"]
    assert study_run.resolvers(tmp_path / "missing") == []
    monkeypatch.setenv("DATAEXODUS_STATE", str(tmp_path))
    monkeypatch.setattr(study_run, "resolvers", lambda: ["1.1.1.1"])
    fake_steps(monkeypatch)
    assert study_run.run()["resolvers"] == ["1.1.1.1"]


def test_a_failed_step_stops_the_run_and_is_never_used_as_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAEXODUS_STATE", str(tmp_path))
    calls = fake_steps(monkeypatch, fail_at="pipeline.process")
    status = study_run.run()
    assert status["ok"] is False
    assert [c[0] for c in calls] == ["crawler.crawl", "pipeline.process"]
    assert study_run.previous_audit(tmp_path / "runs") is None
    assert not (tmp_path / "study.lock").exists()


def test_overlapping_runs_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAEXODUS_STATE", str(tmp_path))
    (tmp_path / "study.lock").write_text("123")
    with pytest.raises(SystemExit):
        study_run.run()
