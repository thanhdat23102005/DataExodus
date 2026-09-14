#!/usr/bin/env python3
"""
DataExodus — Playwright Crawler
Opens each site, records all network requests, detects fingerprinting APIs.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright, Request, Page


def detect_fingerprinting(page: Page) -> list[dict]:
    """
    Inject a script to hook Canvas, WebGL, AudioContext, and Font APIs.
    Returns list of fingerprinting events observed.
    """
    script = """
    () => {
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
    }
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
    session_id = f"{sector}_{int(time.time() * 1000)}"
    requests_log: list[dict] = []
    started_at = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
            ),
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
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            time.sleep(dwell)
        except Exception as e:
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
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel tabs (not implemented, sequential for stability)")
    args = parser.parse_args()

    sites_path = Path("data/sites.yaml")
    sites = yaml.safe_load(sites_path.read_text(encoding="utf-8"))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    for sector, urls in sites["sectors"].items():
        if args.sector and sector != args.sector:
            continue
        for url in urls:
            targets.append((sector, url))

    print(f"[crawl] Starting {len(targets)} sites (dwell={args.dwell}s)")
    for sector, url in targets:
        crawl_site(url, sector, output_dir, dwell=args.dwell)

    print("[crawl] Done.")


if __name__ == "__main__":
    main()
