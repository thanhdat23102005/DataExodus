"""Static checks on guard/manifest.json that browser-free JS tests cannot see."""
import json
import re
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "guard"
MANIFEST = json.loads((GUARD / "manifest.json").read_text(encoding="utf-8-sig"))
CORE = (GUARD / "core.js").read_text(encoding="utf-8")


def test_no_file_shared_between_content_script_entries():
    # Chrome injects each file once per frame; a file listed for both the
    # MAIN and isolated worlds only runs in whichever entry comes first.
    seen = {}
    for i, entry in enumerate(MANIFEST["content_scripts"]):
        for name in entry["js"]:
            assert name not in seen, f"{name} is listed in content_scripts[{seen[name]}] and [{i}]"
            seen[name] = i


def test_main_world_core_is_identical_copy():
    assert (GUARD / "core-main.js").read_bytes() == (GUARD / "core.js").read_bytes()


def test_every_world_gets_guard_core_first():
    for entry in MANIFEST["content_scripts"]:
        assert entry["js"][0] in ("core.js", "core-main.js")


def test_xray_and_bridge_run_only_in_the_isolated_world():
    main = next(e for e in MANIFEST["content_scripts"] if e.get("world") == "MAIN")
    assert "xray.js" not in main["js"] and "content.js" not in main["js"]


def test_ad_click_patterns_match_python_sandbox():
    # One list, two languages: DNR redirects (core.js) and the sandbox's
    # "did we leave the ad network" check (protection/sandbox.py).
    from protection.sandbox import AD_CLICK_PATTERNS
    block = re.search(r"const AD_CLICK = \{(.*?)\};", CORE, re.S).group(1)
    js = {name: json.loads(f'"{pattern}"') for name, pattern in re.findall(r'"([^"]+)": "([^"]+)"', block)}
    assert js == AD_CLICK_PATTERNS


def test_tracking_params_match_python_sandbox():
    from protection.sandbox import TRACKING_PARAMS
    block = re.search(r"const TRACKING_PARAMS = new Set\(\[(.*?)\]\);", CORE, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', block)) == TRACKING_PARAMS


def test_quarantine_page_is_the_only_web_accessible_resource():
    exposed = [r for entry in MANIFEST["web_accessible_resources"] for r in entry["resources"]]
    assert exposed == ["quarantine.html"]


def test_quarantine_page_cannot_connect_or_load_remote_images():
    html = (GUARD / "quarantine.html").read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "connect-src 'none'" in csp and "img-src data:" in csp and "default-src 'none'" in csp
