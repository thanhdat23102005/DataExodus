"""Real Chromium acceptance test: loads guard/ unpacked and drives the lab.

No request routing/mocking substitutes for the loaded extension: every count
below comes from the lab's own receivers. Two phases, each against a fresh lab
process so receipts start at zero:

  baseline   protection off           -> everything reaches its receiver
  protected  protection + lab rules   -> identifiers stop (URL rules before send, a
                                         learned rule after the first POST body), the
                                         popup is blocked, overlay and ad links go to
                                         quarantine, the ad click is previewed in the
                                         sandbox and opened clean

The DataExodus service (protection.api) is started on 127.0.0.1:8010 for the
sandbox preview when that port is free (as it is on a laptop whose service runs
on the Raspberry Pi, once the SSH tunnel is closed). Otherwise the run uses the
"open advertiser page directly" path and records that the preview was skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from analysis.guard_report import build_report
from examples.guard_lab import GuardLab

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PORT = 8010
EXPECTED = {
    "baseline": {"identifier_deliveries": 4, "post_collector_deliveries": 2, "first_party_submits": 1,
                 "ad_navigations": 3, "ad_clicks_from_user": 1, "advertiser_click_ids_from_user": 1,
                 "advertiser_clean_visits": 0},
    "protected": {"identifier_deliveries": 0, "post_collector_deliveries": 1, "first_party_submits": 1,
                  "ad_navigations": 0, "ad_clicks_from_user": 0, "advertiser_click_ids_from_user": 0,
                  "advertiser_clean_visits": 1},
}


def wait_until(page, expression: str, timeout_s: float = 10):
    """Poll with page.evaluate. Playwright's wait_for_function evaluates a
    string with eval(), which the extension pages' CSP (script-src 'self') refuses."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if page.evaluate(expression):
            return
        page.wait_for_timeout(100)
    raise TimeoutError(f"Timed out waiting for: {expression}")


def tab_urls(options) -> list[str]:
    """Every tab Chrome has open, asked from the extension's own page."""
    return options.evaluate("chrome.tabs.query({}).then(ts=>ts.map(t=>t.url||t.pendingUrl||''))")


def start_service(token: str):
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", SERVICE_PORT)) == 0:
            return None  # something else already listens; preview checks are skipped
    env = {**os.environ, "DATAEXODUS_GUARD_TOKEN": token, "SANDBOX_ALLOW_HOSTS": "127.0.0.3,127.0.0.6"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "protection.api:app", "--host", "127.0.0.1",
                             "--port", str(SERVICE_PORT), "--no-access-log"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", SERVICE_PORT)) == 0:
                return proc
        time.sleep(0.1)
    proc.terminate()
    return None


def apply_settings(options, *, enabled, token):
    for box, on in (("#enabled", enabled), ("#labMode", True), ("#popupGuard", True), ("#quarantineAds", True),
                    ("#preventCollection", True), ("#learnCollection", True)):
        options.locator(box).set_checked(on)
    options.locator("#testEmail").fill("student.demo@example.com")
    options.locator("#apiToken").fill(token)
    options.locator("button[type=submit]").click()
    options.get_by_role("status").filter(has_text="Rules applied").wait_for()
    # Clear evidence through the trusted extension UI context.
    options.evaluate("chrome.runtime.sendMessage({type:'clear'})")


def click_and_wait(page, button: str, result: str, attempt: int):
    page.locator(button).click()
    wait_until(page, f"document.getElementById('{result}').dataset.completed==='{attempt}'")


def run_phase(context, options, extension_id, phase, enabled, service):
    quarantine = f"chrome-extension://{extension_id}/quarantine.html"
    with GuardLab(0) as lab:
        page = context.new_page()
        page.goto(lab.site)
        page.wait_for_timeout(300)  # isolated-world policy handshake
        checks = {}
        for attempt, button in enumerate(("#raw", "#hash", "#body"), 1):
            click_and_wait(page, button, "dataResult", attempt)
        click_and_wait(page, "#unknownURL", "unknownResult", 1)
        click_and_wait(page, "#post", "postResult", 1)
        if enabled:
            # The first body went out; Guard saw it and scoped a rule to this pair.
            wait_until(options, "chrome.declarativeNetRequest.getSessionRules().then(rs=>rs.some(r=>"
                                "(r.condition.requestDomains||[]).includes('127.0.0.5')))")
            checks["learned_rule_installed"] = True
        click_and_wait(page, "#post", "postResult", 2)
        click_and_wait(page, "#firstParty", "firstPartyResult", 1)
        # Guard opens at most one quarantine tab per page every 1.5 s (a page
        # cannot flood the browser with tabs), so the clicks are spaced out.
        page.locator("#play").click()
        page.get_by_text("Primary Play action completed.").wait_for()
        page.wait_for_timeout(1700)
        page.bring_to_front()
        page.locator("#overlay").click()
        page.wait_for_timeout(1700)
        page.bring_to_front()
        page.locator("#directAd").click()
        # Negative control, judged on the receiver like everything else. (Playwright
        # does not always attach to a new headless tab, so the server log is the evidence.)
        page.bring_to_front()
        page.locator("#docs").click()
        deadline = time.time() + 10
        while time.time() < deadline and lab.docs_served == 0:
            page.wait_for_timeout(100)
        if lab.docs_served == 0:
            raise RuntimeError(f"{phase}: legitimate documentation was never requested; open tabs: {tab_urls(options)}")
        checks["legitimate_document_opened"] = True
        page.wait_for_timeout(1500)
        if enabled:
            # The overlay (opened by Guard after the click) and the direct ad
            # link (redirected by Chrome, verified against policy) each wait in
            # their own quarantine tab; the Play popup nobody asked for is only
            # blocked. Without the "tabs" permission Chrome hides extension tab
            # URLs, so Guard's own records are read.
            held = options.evaluate("chrome.storage.session.get('quarantines').then(r=>"
                                    "Object.values(r.quarantines||{}).map(e=>e.reason+(e.verified?'':':unverified')))")
            checks["quarantine_tabs_for_overlay_and_direct_ad"] = (
                {"transparent_overlay:unverified", "network_rule"} <= set(held)
                and not any(h.startswith("popup_without_link") for h in held))
            if not checks["quarantine_tabs_for_overlay_and_direct_ad"]:
                print(f"quarantine records: {held}", file=sys.stderr)
        # Last action: the sponsored link navigates this tab.
        page.bring_to_front()
        page.locator("#sponsored").click()
        if enabled:
            page.wait_for_url(quarantine + "**")
            page.locator("#reason").filter(has_text="Lab ad").wait_for()
            checks["ad_click_held_in_quarantine"] = True
            checks["click_url_removed_from_address_bar"] = "aclk" not in page.url
            if service:
                page.locator("#sandboxPreview").click()
                page.locator("#verdict").filter(has_text="landing page").wait_for(timeout=60000)
                clean = page.text_content("#clean") or ""
                chain = page.text_content("#chain") or ""
                checks["sandbox_followed_redirect_chain"] = "/aclk" in chain and "/landing" in chain
                checks["sandbox_removed_click_ids"] = clean.endswith("/landing") and "gclid" not in clean
                checks["sandbox_screenshot_shown"] = page.locator("#shot img").count() == 1
                page.locator("#openClean").click()
            else:
                page.locator("#direct").click()
            page.wait_for_url("http://127.0.0.6:*/landing**")
            checks["advertiser_page_opened_clean"] = "gclid" not in page.url
        else:
            page.wait_for_url("http://127.0.0.6:*/landing?gclid=**")
            checks["ad_click_landed_with_click_id"] = True
        page.wait_for_timeout(300)

        with lab.lock:
            receipts = list(lab.receipts)
        kind = lambda k: [r for r in receipts if r["kind"] == k]  # noqa: E731
        counts = {
            "identifier_deliveries": sum(r["receiver"] in ("collector", "unlisted_url") for r in kind("identifier")),
            "post_collector_deliveries": sum(r["receiver"] == "post_collector" for r in kind("identifier")),
            "first_party_submits": len(kind("first_party_submit")),
            "ad_navigations": len(kind("popup_navigation")),
            # The sandbox's own visit carries no Referer and is not the user's browser.
            "ad_clicks_from_user": sum(r["from_user_page"] for r in kind("ad_click")),
            "advertiser_click_ids_from_user": sum(r["click_id"] and r["from_user_page"] for r in kind("advertiser_visit")),
            "advertiser_clean_visits": sum(not r["click_id"] for r in kind("advertiser_visit")),
        }
        if enabled and service:
            checks["sandbox_visit_reached_advertiser_anonymously"] = any(
                r["click_id"] and not r["from_user_page"] for r in kind("advertiser_visit"))
        state = options.evaluate("chrome.runtime.sendMessage({type:'state'}).then(r=>r.data)")
        if enabled:
            enforcement = {e["enforcement"] for e in state["events"]}
            checks["chrome_rule_matches_recorded"] = {"network_blocked", "navigation_quarantined"} <= enforcement
            checks["identifier_never_in_evidence"] = "student.demo" not in json.dumps(state["events"])
        expected = EXPECTED[phase]
        passed = counts == expected and all(v is True for v in checks.values())
        for tab in context.pages:
            if tab != options:
                tab.close()
        return {"phase": phase, **counts, "expected": expected, "checks": checks, "passed": passed,
                "receipts": receipts, "events": state["events"]}


def run(out: Path, headed=False):
    if out.exists():
        raise ValueError("Choose a fresh output directory to preserve previous evidence")
    out.mkdir(parents=True)
    guard = str(ROOT / "guard")
    token = secrets.token_urlsafe(32)
    service = start_service(token)
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="dataexodus-guard-") as profile, sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    profile, channel="chromium", headless=not headed,
                    args=[f"--disable-extensions-except={guard}", f"--load-extension={guard}"],
                )
            except Exception:
                (out / "acceptance.json").write_text(json.dumps({
                    "status": "not_completed", "reason": "browser_launch_failed", "results": [],
                    "instruction": "Install Playwright Chromium and inspect the launch error."}, indent=2))
                raise
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
                extension_id = worker.url.split("/")[2]
                options = context.new_page()
                options.goto(f"chrome-extension://{extension_id}/options.html")
                # Worker initialization must finish before manipulating settings.
                wait_until(options, "document.getElementById('blockedDomains').value.includes('doubleclick.net')")
                for phase, enabled in (("baseline", False), ("protected", True)):
                    apply_settings(options, enabled=enabled, token=token)
                    result = run_phase(context, options, extension_id, phase, enabled, service is not None)
                    phase_dir = out / phase
                    phase_dir.mkdir()
                    (phase_dir / "collector_receipts.json").write_text(json.dumps(result.pop("receipts"), indent=2))
                    export = {"schema": "dataexodus.guard.v1", "exported_at": datetime.now(timezone.utc).isoformat(),
                              "limits": "Controlled loopback browser run; bounded recent events.",
                              "events": result.pop("events")}
                    events = phase_dir / "events.json"
                    events.write_text(json.dumps(export, indent=2))
                    build_report(events, phase_dir)
                    results.append(result)
                summary = {"provenance": "real_chromium_extension_loopback",
                           "sandbox_service": "started" if service else "skipped_port_in_use",
                           "browser_version": context.browser.version if context.browser else "unknown",
                           "results": results}
                (out / "acceptance.json").write_text(json.dumps(summary, indent=2))
                print(json.dumps(summary, indent=2))
                if not all(r["passed"] for r in results):
                    raise RuntimeError(f"Acceptance failed; inspect {out / 'acceptance.json'}")
            finally:
                context.close()
    finally:
        if service:
            service.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("reports/guard-browser-run1"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    run(args.out, args.headed)


if __name__ == "__main__":
    main()
