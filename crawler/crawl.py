#!/usr/bin/env python3
"""
DataExodus — Playwright Crawler
Opens each site, records all network requests, detects fingerprinting APIs.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright, Request, Page


def detect_fingerprinting(page: Page) -> list[dict]:
    """
    Inject a script to hook Canvas, WebGL, AudioContext, and Font APIs.
    Returns list of fingerprinting events observed.
    """
    script = """
    (() => {
        window.__fp_events = [];
        const log = (type, detail) => window.__fp_events.push({type, detail, ts: Date.now()});

        // Canvas
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(...args) {
            log('canvas', {method: 'toDataURL'});
            return origToDataURL.apply(this, args);
        };
        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function(...args) {
            log('canvas', {method: 'getImageData'});
            return origGetImageData.apply(this, args);
        };

        // WebGL
        const origGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(pname) {
            const fp_params = [37445, 37446, 7937, 7936, 33901, 33902, 34047, 34076];
            if (fp_params.includes(pname)) log('webgl', {parameter: pname});
            return origGetParameter.call(this, pname);
        };

        // AudioContext
        const origCreateAnalyser = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = function(...args) {
            log('audio', {method: 'createAnalyser'});
            return origCreateAnalyser.apply(this, args);
        };

        // Fonts
        const origMeasureText = CanvasRenderingContext2D.prototype.measureText;
        CanvasRenderingContext2D.prototype.measureText = function(text) {
            if (text && text.length < 50) log('fonts', {text_sample: text.slice(0,20)});
            return origMeasureText.call(this, text);
        };
    })();
    """
    page.add_init_script(script)
    return []


def crawl_site(
    url: str,
    sector: str,
    output_dir: Path,
    dwell: int = 8,
    timeout: int = 30,
) -> dict:
    """Crawl a single site and return session data."""
    session_id = f"{sector}_{uuid.uuid4().hex}"
    requests_log: list[dict] = []
    started_at = time.time()
    error = None
    http_status = None
    crawl_status = "ok"
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # CHROMIUM_PATH: the OS browser, e.g. /usr/bin/chromium on Raspberry Pi OS
        # when Playwright's own build is unavailable for the platform.
        browser = p.chromium.launch(headless=True, executable_path=os.getenv("CHROMIUM_PATH") or None)
        browser_version = browser.version
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # Hook fingerprinting before navigation
        detect_fingerprinting(page)

        def handle_request(req: Request):
            try:
                post_data = None
                try:
                    post_data = req.post_data
                except Exception:
                    pass
                requests_log.append({
                    "timestamp": time.time(),
                    "url": req.url,
                    "method": req.method,
                    "type": req.resource_type,
                    "initiator": page.url if page.url != "about:blank" else url,
                    "headers": dict(req.headers),
                    "body": post_data,
                })
            except Exception:
                pass

        page.on("request", handle_request)

        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            http_status = response.status if response else None
            page.wait_for_timeout(dwell * 1000)
            if http_status is None or http_status >= 400:
                crawl_status = "failed"
        except Exception as e:
            crawl_status = "partial" if requests_log else "failed"
            error = str(e)
            print(f"  [warn] {url}: {e}")

        # Collect fingerprinting events from page
        fp_events = []
        try:
            fp_events = page.evaluate("() => window.__fp_events || []")
        except Exception:
            pass

        browser.close()

    ended_at = time.time()
    data = {
        "session_id": session_id,
        "site": url,
        "sector": sector,
        "started_at": started_at,
        "ended_at": ended_at,
        "http_status": http_status,
        "crawl_status": crawl_status,
        "error": error,
        "provenance": "observed_capture",
        "protocol": {"dwell_seconds": dwell, "timeout_seconds": timeout,
                     "consent_state": "no_interaction", "fresh_context": True,
                     "browser_version": browser_version, "headless": True},
        "requests": requests_log,
        "fingerprinting_events": fp_events,
    }

    out_path = output_dir / f"{session_id}.json"
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"  [crawl] {url}: {len(requests_log)} requests, {len(fp_events)} fp events → {out_path.name}")
    return data


def main():
    parser = argparse.ArgumentParser(description="DataExodus Crawler")
    parser.add_argument("--sector", default=None, help="Only crawl one sector")
    parser.add_argument("--output", default="data/raw", help="Output directory")
    parser.add_argument("--dwell", type=int, default=8, help="Seconds to dwell on page")
    parser.add_argument("--url", help="Single authorised URL (manual sector); ignores the site list")
    parser.add_argument("--sites", default="data/sites.yaml", help="Site list YAML")
    parser.add_argument("--timeout", type=int, default=30, help="Navigation timeout in seconds")
    args = parser.parse_args()

    if args.dwell < 0 or args.timeout < 1:
        parser.error("dwell must be >= 0; timeout must be >= 1")
    sites = yaml.safe_load(Path(args.sites).read_text(encoding="utf-8")) if not args.url else {"sectors": {}}
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    if args.url:
        targets.append((args.sector or "manual", args.url))
    for sector, urls in sites["sectors"].items():
        if args.sector and sector != args.sector:
            continue
        for url in urls:
            targets.append((sector, url))

    print(f"[crawl] Starting {len(targets)} sites (dwell={args.dwell}s)")
    for sector, url in targets:
        crawl_site(url, sector, output_dir, dwell=args.dwell, timeout=args.timeout)

    print("[crawl] Done.")


if __name__ == "__main__":
    main()
