"""Static checks on the Raspberry Pi deployment files (no Pi needed)."""
import ast
import configparser
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PI = ROOT / "pi"
UNITS = sorted((PI / "systemd").glob("dataexodus-*.*"))


def unit(path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(path.read_text(encoding="utf-8"))
    return parser


def test_unit_set_is_complete_and_installer_ships_every_file():
    assert {p.name for p in UNITS} == {"dataexodus-firewall.service", "dataexodus-guard.service",
                                       "dataexodus-dnswatch.service", "dataexodus-box.service",
                                       "dataexodus-study.service", "dataexodus-study.timer",
                                       "dataexodus-portal.service", "dataexodus-samples.service"}
    script = (PI / "install.sh").read_text(encoding="utf-8")
    for needed in ("requirements-pi.txt", "pi/dataexodus.env.example", "pi/nftables-dataexodus.nft", "pi/systemd/",
                   "pi/hotspot.sh"):
        assert needed in script
        assert (ROOT / needed).exists()


def test_research_crawl_is_opt_in_and_the_hotspot_is_one_flag():
    script = (PI / "install.sh").read_text(encoding="utf-8")
    assert "--study) WITH_STUDY=1" in script and "--hotspot) WITH_HOTSPOT=1" in script
    enable_line = next(line for line in script.splitlines() if line.startswith("systemctl enable dataexodus-guard"))
    assert "study" not in enable_line
    assert 'if [[ $WITH_STUDY -eq 1 ]]; then\n  systemctl enable --now dataexodus-study.timer' in script


@pytest.mark.parametrize("path", [p for p in UNITS if p.suffix == ".service" and "firewall" not in p.name],
                         ids=lambda p: p.name)
def test_services_run_unprivileged_and_hardened(path):
    service = unit(path)["Service"]
    assert service["User"] == "dataexodus" and service["Group"] == "dataexodus"
    for key in ("NoNewPrivileges", "ProtectHome", "PrivateTmp", "ProtectKernelModules", "RestrictSUIDSGID"):
        assert service[key] == "yes", key
    assert service["ProtectSystem"] == "strict"
    assert service["EnvironmentFile"] == "/etc/dataexodus/dataexodus.env"
    assert "MemoryMax" in service


@pytest.mark.parametrize("name", ["dataexodus-guard.service", "dataexodus-box.service"])
def test_web_services_listen_on_loopback_only(name):
    command = unit(PI / "systemd" / name)["Service"]["ExecStart"]
    assert "--host 127.0.0.1" in command and "0.0.0.0" not in command


@pytest.mark.parametrize("name", ["dataexodus-guard.service", "dataexodus-study.service"])
def test_untrusted_pages_are_only_opened_behind_the_firewall(name):
    assert "dataexodus-firewall.service" in unit(PI / "systemd" / name)["Unit"]["Requires"]


def test_only_the_dns_watch_and_the_portal_may_bind_a_privileged_port():
    privileged = {"dataexodus-dnswatch.service", "dataexodus-portal.service"}
    for path in UNITS:
        service = unit(path)["Service"] if path.suffix == ".service" else {}
        caps = service.get("AmbientCapabilities", "")
        assert caps == ("CAP_NET_BIND_SERVICE" if path.name in privileged else ""), path.name
        if path.name in privileged:
            assert service["CapabilityBoundingSet"] == "CAP_NET_BIND_SERVICE"


def test_portal_listens_on_the_hotspot_address_and_samples_on_loopback():
    portal = unit(PI / "systemd" / "dataexodus-portal.service")
    assert portal["Service"]["ExecStart"].endswith("-m pi.portal") and portal["Service"]["Restart"] == "always"
    source = (PI / "portal.py").read_text(encoding="utf-8")
    assert 'host=portal_ip()' in source and '"0.0.0.0"' not in source
    samples = unit(PI / "systemd" / "dataexodus-samples.service")["Service"]["ExecStart"]
    assert "examples.sample_links" in samples
    lab = (ROOT / "examples" / "sample_links.py").read_text(encoding="utf-8")
    assert all(host.startswith("127.0.0.") for host in re.findall(r'\("(\d+\.\d+\.\d+\.\d+)", "', lab))


def test_chromium_keeps_namespaces_and_jit():
    service = unit(PI / "systemd" / "dataexodus-guard.service")["Service"]
    assert "RestrictNamespaces" not in service and "MemoryDenyWriteExecute" not in service


def test_firewall_drops_lan_and_loopback_for_the_service_account_only():
    rules = (PI / "nftables-dataexodus.nft").read_text(encoding="utf-8")
    assert "meta skuid != @UID@ accept" in rules
    assert rules.index("ct state established,related accept") < rules.index("counter drop")
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16", "100.64.0.0/10",
                "fc00::/7", "fe80::/10", "::ffff:0:0/96"):
        assert net in rules, net
    # Re-loadable: the table is declared, deleted and recreated in one file.
    assert rules.index("delete table inet dataexodus") < rules.index("table inet dataexodus {")
    # The only loopback exceptions: the Guard API and the sample links, before the drop rules.
    accepts = [line.strip() for line in rules.splitlines() if "127.0.0." in line and line.strip().endswith("accept")]
    assert accepts == ["ip daddr 127.0.0.1 tcp dport 8010 accept", "ip daddr 127.0.0.48/28 tcp dport 8030 accept"]
    assert all(rules.index(a) < rules.index("counter drop") for a in accepts)


def test_installer_is_strict_bash_with_unix_line_endings():
    raw = (PI / "install.sh").read_bytes()
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert text.startswith("#!/usr/bin/env bash\n") and "set -euo pipefail" in text
    assert "nft -c -f" in text  # the rule set is syntax-checked before it is enabled
    assert 'rm -rf "${APP:?}/' in text  # never an empty-variable rm -rf /
    for path in [PI / "nftables-dataexodus.nft", PI / "dataexodus.env.example", PI / "hotspot.sh", *UNITS]:
        assert b"\r" not in path.read_bytes(), path.name


def test_hotspot_script_is_safe_to_run_and_isolates_visitors():
    text = (PI / "hotspot.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n") and "set -euo pipefail" in text
    assert 'case "$MODE" in ""|--prepare|--on|--home|--off) ;;' in text
    # Preparing never takes the Pi off its current Wi-Fi: the profile is created switched off.
    assert 'con-name "$CON" autoconnect no' in text
    prepare_body = text[text.index("prepare() {"):text.index("ap_up() {")]
    assert "nmcli connection up" not in prepare_body and "detach" not in prepare_body
    # Demo mode survives reboots; --home switches it off again.
    assert "connection.autoconnect yes connection.autoconnect-priority 100" in text
    assert 'nmcli connection modify "$CON" connection.autoconnect no' in text
    # A mode switch over an SSH session on the same radio finishes detached instead of half-way.
    assert "( sport = :22 )" in text and "HOTSPOT_DETACHED=1 setsid nohup bash" in text
    for mode in ("--on)      detach_if_needed", "--home)    detach_if_needed", "--off)     detach_if_needed"):
        assert mode in text, mode
    for option in ("802-11-wireless.mode ap", "802-11-wireless.ap-isolation yes", "wifi-sec.key-mgmt wpa-psk",
                   "wifi-sec.proto rsn", "ipv4.method shared", "ipv6.method disabled"):
        assert option in text, option
    # NetworkManager's dnsmasq does DHCP only; the DNS watch answers DNS.
    assert "port=0" in text and "dhcp-option=option:dns-server,$PORTAL_IP" in text
    assert "(( ${#psk} >= 8 ))" in text and "secrets.choice" in text
    assert "systemctl disable --now dataexodus-portal.service" in text


def test_settings_template_has_placeholders_and_no_secrets():
    text = (PI / "dataexodus.env.example").read_text(encoding="utf-8")
    for placeholder in ("__TOKEN__", "__CHROMIUM__", "__ALLOW__", "__HOST__"):
        assert placeholder in text
    for key in ("GEMINI_API_KEY", "WEBRISK_API_KEY", "HOTSPOT_PSK"):
        assert re.search(rf"^#{key}=$", text, re.M), key
    assert "DATAEXODUS_CHROMIUM_SANDBOX=1" in text and "DNSWATCH_MODE=observe" in text
    assert "DNSWATCH_UPSTREAM=auto" in text and "SANDBOX_BROWSE_SESSIONS=1" in text


def test_windows_tunnel_binds_laptop_loopback_only():
    script = (PI / "connect-pi.ps1").read_text(encoding="utf-8")
    assert "-L 127.0.0.1:8010:127.0.0.1:8010" in script and "-L 127.0.0.1:8020:127.0.0.1:8020" in script
    assert "ExitOnForwardFailure=yes" in script


def _imports(paths):
    found = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


def test_pi_requirements_cover_everything_the_pi_services_import():
    modules = [*PI.glob("*.py"), *(ROOT / "protection").glob("*.py"), ROOT / "crawler" / "crawl.py",
               ROOT / "setup_data.py", *(ROOT / "pipeline" / n for n in ("process.py", "classify.py", "pii.py", "risk.py")),
               *(ROOT / "analysis" / n for n in ("audit.py", "report.py", "export_sheet.py"))]
    local = {"pi", "protection", "pipeline", "analysis", "crawler", "examples"}
    third_party = _imports(modules) - set(sys.stdlib_module_names) - local
    modules.append(ROOT / "examples" / "sample_links.py")
    package = {"yaml": "pyyaml", "ahocorasick": "pyahocorasick", "dnslib": "dnslib"}
    wanted = {package.get(m, m) for m in third_party}
    listed = {re.split(r"[<>=\[]", line)[0].strip().lower()
              for line in (ROOT / "requirements-pi.txt").read_text().splitlines() if line and not line.startswith("#")}
    assert wanted <= listed, wanted - listed
