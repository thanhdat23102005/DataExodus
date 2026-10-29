"""DataExodus DNS watch: a small DNS forwarder for your own lab devices.

Point a phone, smart TV or laptop at the Raspberry Pi for DNS and every name
it looks up is logged: which device asked, which name, which addresses came
back. pi/dns_report.py then labels the names with the study's tracker lists
and GeoIP database, so you can see which companies your devices contact and
in which countries the answering servers are, for every app, not only the
browser. Block mode answers listed tracker and malware names with 0.0.0.0 / ::.

Safety and privacy:
  * only clients inside --allow (CIDRs) are answered; anyone else gets REFUSED
    and is not logged, so the Pi is never an open resolver;
  * the log stays on the Pi (SQLite) and is pruned after --retention-days;
  * monitor only devices you own or have permission to monitor: other people's
    lookups are their personal information.

A DNS name and the country of the address it resolves to are estimates of
where a connection would go, not proof of where data is stored (APP 8).

On the DataExodus Wi-Fi (pi/hotspot.sh, PORTAL_NET) the rules are stricter:
  * a hotspot device's lookups are logged only after its user switched
    "Show my device's connections" on in the portal (pi/devices.py), are
    tagged with that device, and expire after PORTAL_RETENTION_HOURS;
  * "Block trackers on my device" sinkholes listed names for that device only;
  * the operating systems' connectivity-check names and the portal's own name
    are answered with the portal's address, so a phone that joins opens the
    welcome page by itself (captive portal). They are never logged.

Run (development, unprivileged port):
  python -m pi.dnswatch --port 5353 --db data/dnswatch.sqlite --allow 127.0.0.0/8
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import sqlite3
import struct
import time
from pathlib import Path

from dnslib import AAAA, QTYPE, RCODE, RR, A, DNSRecord

from pi.devices import Devices

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
  ts INTEGER NOT NULL, client TEXT NOT NULL, qname TEXT NOT NULL, qtype TEXT NOT NULL,
  rcode TEXT NOT NULL, answers TEXT NOT NULL, blocked INTEGER NOT NULL, listed TEXT, device TEXT
);
CREATE INDEX IF NOT EXISTS queries_ts ON queries(ts);
"""
# Names that phones, tablets and laptops fetch over plain HTTP to decide
# whether a Wi-Fi network needs a sign-in page. Probe hosts only: answering
# them with the portal's address breaks nothing else.
CAPTIVE_NAMES = {
    "connectivitycheck.gstatic.com", "connectivitycheck.android.com", "clients3.google.com",
    "captive.apple.com", "www.msftconnecttest.com", "www.msftncsi.com", "detectportal.firefox.com",
    "nmcheck.gnome.org", "network-test.debian.org", "connectivity-check.ubuntu.com",
}
RESOLV_CONF = Path("/etc/resolv.conf")


def system_resolver(path: Path = RESOLV_CONF, avoid: set[str] | None = None) -> tuple[str, int] | None:
    """The uplink's resolver as NetworkManager wrote it, so DNS keeps working
    when the Pi moves between networks (home router, TAFE, phone tethering)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver" and "%" not in parts[1]:
            try:
                ip = ipaddress.ip_address(parts[1])
            except ValueError:
                continue
            if not (ip.is_loopback or ip.is_unspecified or ip.is_link_local) and str(ip) not in (avoid or set()):
                return str(ip), 53
    return None


def load_blocklist(paths: list[str | Path]) -> set[str]:
    """Domains from EasyPrivacy (||domain^ rules only), hosts files (URLhaus
    mirror: '0.0.0.0 domain') or plain one-domain-per-line lists."""
    domains: set[str] = set()
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip().lower()
            if not line or line.startswith("!") or line.startswith("["):
                continue
            if line.startswith("||"):
                if line.endswith("^") and all(c.isalnum() or c in ".-" for c in line[2:-1]):
                    domains.add(line[2:-1])
                continue
            parts = line.split()
            name = parts[1] if len(parts) == 2 and parts[0] in ("0.0.0.0", "127.0.0.1", "::") else parts[0]
            if len(parts) <= 2 and "." in name and all(c.isalnum() or c in ".-_" for c in name):
                domains.add(name.rstrip("."))
    domains.discard("localhost")
    return domains


def listed_suffix(name: str, domains: set[str]) -> str | None:
    labels = name.split(".")
    for i in range(len(labels) - 1):
        candidate = ".".join(labels[i:])
        if candidate in domains:
            return candidate
    return None


class Watch:
    def __init__(self, db: str | Path, upstream: tuple[str, int] | str, allow: list[str], blocked: set[str],
                 mode: str = "observe", never_block: set[str] | None = None, retention_days: int = 7,
                 timeout: float = 2.5, blocklists: list[str | Path] | None = None,
                 portal_net: str | None = None, portal_ip: str | None = None, portal_name: str | None = None,
                 devices: Devices | None = None, portal_retention_hours: int = 24, resolv_conf: Path = RESOLV_CONF):
        # "auto": the uplink's resolver from /etc/resolv.conf, re-read every 30 s, else 1.1.1.1.
        self.auto_upstream = upstream == "auto"
        self.upstream = ("1.1.1.1", 53) if self.auto_upstream else upstream
        self.resolv_conf = resolv_conf
        self.upstream_checked = 0.0
        self.blocklists = [Path(p) for p in blocklists or []]
        self.blocklist_mtimes = self._mtimes()
        self.portal_net = ipaddress.ip_network(portal_net, strict=False) if portal_net else None
        self.portal_ip = portal_ip
        self.portal_name = (portal_name or "").lower().rstrip(".") or None
        self.devices = devices
        self.portal_retention = portal_retention_hours * 3600
        self.allow = [ipaddress.ip_network(net, strict=False) for net in allow]
        if self.portal_net and self.portal_net not in self.allow:
            self.allow.append(self.portal_net)
        self.blocked = blocked
        self.never_block = never_block or set()
        self.mode = mode
        self.retention = retention_days * 86400
        self.timeout = timeout
        Path(db).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=2000")
        self.db.executescript(SCHEMA)
        if "device" not in {row[1] for row in self.db.execute("PRAGMA table_info(queries)")}:
            self.db.execute("ALTER TABLE queries ADD COLUMN device TEXT")  # logs from before the portal
        self.db.execute("CREATE INDEX IF NOT EXISTS queries_device ON queries(device, ts)")
        self.prune()

    @staticmethod
    def _ip(client: str):
        try:
            ip = ipaddress.ip_address(client)
        except ValueError:
            return None
        return ip.ipv4_mapped if ip.version == 6 and ip.ipv4_mapped else ip

    def allowed(self, client: str) -> bool:
        ip = self._ip(client)
        return ip is not None and any(ip in net for net in self.allow)

    def on_hotspot(self, client: str) -> bool:
        ip = self._ip(client)
        return ip is not None and self.portal_net is not None and ip in self.portal_net

    def current_upstream(self) -> tuple[str, int]:
        if self.auto_upstream and time.monotonic() - self.upstream_checked > 30:
            self.upstream_checked = time.monotonic()
            self.upstream = system_resolver(self.resolv_conf, {self.portal_ip or ""}) or ("1.1.1.1", 53)
        return self.upstream

    def _mtimes(self):
        return [p.stat().st_mtime if p.is_file() else None for p in self.blocklists]

    def reload_if_changed(self) -> bool:
        # setup_data.py --refresh-threats rewrites the URLhaus list weekly.
        mtimes = self._mtimes()
        if mtimes == self.blocklist_mtimes:
            return False
        self.blocked, self.blocklist_mtimes = load_blocklist(self.blocklists), mtimes
        return True

    def prune(self):
        now = int(time.time())
        self.db.execute("DELETE FROM queries WHERE ts < ?", (now - self.retention,))
        self.db.execute("DELETE FROM queries WHERE device IS NOT NULL AND ts < ?", (now - self.portal_retention,))

    def log(self, client, qname, qtype, rcode, answers, blocked, listed, device=None):
        self.db.execute("INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?)",
                        (int(time.time()), client, qname, qtype, rcode, json.dumps(answers), int(blocked), listed,
                         device))

    async def handle(self, data: bytes, client: str, tcp: bool = False) -> bytes | None:
        try:
            request = DNSRecord.parse(data)
        except Exception:  # noqa: BLE001 - not DNS: drop silently
            return None
        if not self.allowed(client):
            reply = request.reply()
            reply.header.rcode = RCODE.REFUSED
            return reply.pack()
        if not request.questions:
            return None
        question = request.questions[0]
        qname = str(question.qname).rstrip(".").lower()
        qtype = QTYPE.get(question.qtype, str(question.qtype))
        hotspot = self.on_hotspot(client)
        if hotspot and self.portal_ip and (qname in CAPTIVE_NAMES or qname == self.portal_name):
            reply = request.reply()
            if qtype == "A":
                reply.add_answer(RR(question.qname, QTYPE.A, ttl=10, rdata=A(self.portal_ip)))
            return reply.pack()  # infrastructure, not the user's browsing: not logged
        # Hotspot devices: logged only with the user's choice, tagged with the device.
        policy = self.devices.get(client) if hotspot and self.devices else None
        record = (not hotspot) or bool(policy and policy.get("watch"))
        device = policy["key"] if policy else None
        listed = None if listed_suffix(qname, self.never_block) else listed_suffix(qname, self.blocked)
        if listed and (self.mode == "block" or bool(policy and policy.get("block"))):
            reply = request.reply()
            if qtype == "A":
                reply.add_answer(RR(question.qname, QTYPE.A, ttl=60, rdata=A("0.0.0.0")))
            elif qtype == "AAAA":
                reply.add_answer(RR(question.qname, QTYPE.AAAA, ttl=60, rdata=AAAA("::")))
            if record:
                self.log(client, qname, qtype, "NOERROR", [], True, listed, device)
            return reply.pack()
        try:
            answer = await (self.forward_tcp(data) if tcp else self.forward_udp(data))
            response = DNSRecord.parse(answer)
            if response.header.id != request.header.id:
                raise ValueError("Upstream answered a different query")
        except Exception:  # noqa: BLE001 - timeout, refused or garbage upstream
            reply = request.reply()
            reply.header.rcode = RCODE.SERVFAIL
            if record:
                self.log(client, qname, qtype, "SERVFAIL", [], False, listed, device)
            return reply.pack()
        ips = [str(rr.rdata) for rr in response.rr if rr.rtype in (QTYPE.A, QTYPE.AAAA)]
        if record:
            self.log(client, qname, qtype, RCODE.get(response.header.rcode, "OTHER"), ips[:16], False, listed, device)
        return answer  # unchanged, so DNSSEC data and TTLs reach the client intact

    async def forward_udp(self, data: bytes) -> bytes:
        loop = asyncio.get_running_loop()
        done: asyncio.Future = loop.create_future()

        class Client(asyncio.DatagramProtocol):
            def datagram_received(self, packet, addr):
                if not done.done():
                    done.set_result(packet)

            def error_received(self, exc):
                if not done.done():
                    done.set_exception(exc)

        transport, _ = await loop.create_datagram_endpoint(Client, remote_addr=self.current_upstream())
        try:
            transport.sendto(data)
            return await asyncio.wait_for(done, self.timeout)
        finally:
            transport.close()

    async def forward_tcp(self, data: bytes) -> bytes:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(*self.current_upstream()), self.timeout)
        try:
            writer.write(struct.pack("!H", len(data)) + data)
            await writer.drain()
            size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), self.timeout))[0]
            return await asyncio.wait_for(reader.readexactly(size), self.timeout)
        finally:
            writer.close()


async def serve(watch: Watch, host: str, port: int, ready: asyncio.Event | None = None):
    loop = asyncio.get_running_loop()

    class Server(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            async def answer():
                reply = await watch.handle(data, addr[0])
                if reply:
                    self.transport.sendto(reply, addr)
            loop.create_task(answer())

    async def tcp_client(reader, writer):
        client = writer.get_extra_info("peername")[0]
        try:
            while True:
                size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 10))[0]
                reply = await watch.handle(await reader.readexactly(size), client, tcp=True)
                if not reply:
                    break
                writer.write(struct.pack("!H", len(reply)) + reply)
                await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    udp, _ = await loop.create_datagram_endpoint(Server, local_addr=(host, port))
    tcp = await asyncio.start_server(tcp_client, host, port)
    if ready:
        ready.set()
    try:
        while True:
            await asyncio.sleep(3600)
            watch.prune()
            watch.reload_if_changed()
    finally:
        udp.close()
        tcp.close()


def parse_upstream(value: str) -> tuple[str, int] | str:
    if value.strip().lower() == "auto":
        return "auto"
    host, _, port = value.rpartition(":") if value.count(":") == 1 else (value, "", "53")
    return (host or value), int(port or 53)


def main():
    env = os.environ.get
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--listen", default=env("DNSWATCH_LISTEN", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(env("DNSWATCH_PORT", "53")))
    parser.add_argument("--upstream", default=env("DNSWATCH_UPSTREAM", "auto"),
                        help="Resolver to forward to, host[:port], or auto (the uplink's resolver "
                             "from /etc/resolv.conf, else 1.1.1.1)")
    parser.add_argument("--allow", default=env("DNSWATCH_ALLOW", "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"),
                        help="Comma-separated client networks that may use this resolver")
    parser.add_argument("--mode", choices=("observe", "block"), default=env("DNSWATCH_MODE", "observe"))
    parser.add_argument("--blocklist", action="append",
                        default=[p for p in env("DNSWATCH_BLOCKLISTS", "pi/dns_trackers.txt,data/blocklists/easyprivacy.txt,"
                                                "data/blocklists/urlhaus_hosts.txt").split(",") if p])
    parser.add_argument("--never-block", default=env("DNSWATCH_NEVER_BLOCK", ""),
                        help="Comma-separated domains always answered normally (false positives)")
    parser.add_argument("--db", default=env("DNSWATCH_DB", "data/dnswatch.sqlite"))
    parser.add_argument("--retention-days", type=int, default=int(env("DNSWATCH_RETENTION_DAYS", "7")))
    # The DataExodus Wi-Fi (pi/hotspot.sh writes these to the settings file).
    parser.add_argument("--portal-net", default=env("PORTAL_NET", ""), help="Hotspot client network, e.g. 10.42.0.0/24")
    parser.add_argument("--portal-ip", default=env("PORTAL_IP", ""))
    parser.add_argument("--portal-name", default=env("PORTAL_HOSTNAME", "dataexodus.home.arpa"))
    parser.add_argument("--portal-devices", default=env("PORTAL_DEVICES", "data/portal/devices.json"))
    parser.add_argument("--portal-retention-hours", type=int, default=int(env("PORTAL_RETENTION_HOURS", "24")))
    args = parser.parse_args()
    blocked = load_blocklist(args.blocklist)
    watch = Watch(args.db, parse_upstream(args.upstream), [n for n in args.allow.split(",") if n.strip()],
                  blocked, args.mode, {d.strip().lower() for d in args.never_block.split(",") if d.strip()},
                  args.retention_days, blocklists=args.blocklist,
                  portal_net=args.portal_net or None, portal_ip=args.portal_ip or None, portal_name=args.portal_name,
                  devices=Devices(args.portal_devices) if args.portal_net else None,
                  portal_retention_hours=args.portal_retention_hours)
    print(f"[dnswatch] {args.listen}:{args.port} -> {args.upstream}, mode={args.mode}, "
          f"{len(blocked):,} listed domains, clients {args.allow}"
          + (f", hotspot {args.portal_net} (portal {args.portal_ip})" if args.portal_net else ""), flush=True)
    asyncio.run(serve(watch, args.listen, args.port))


if __name__ == "__main__":
    main()
