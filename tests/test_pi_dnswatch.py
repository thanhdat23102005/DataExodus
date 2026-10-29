import asyncio
import json
import socket
import struct

from dnslib import QTYPE, RCODE, RR, A, DNSRecord

from pi import dnswatch
from pi.dnswatch import Watch, listed_suffix, load_blocklist


def test_blocklists_accept_easyprivacy_hosts_and_plain_lists(tmp_path):
    (tmp_path / "easyprivacy.txt").write_text(
        "! comment\n||tracker.example^\n||cdn.example/path.js\n@@||allowed.example^\n||ads.example^$third-party\n")
    (tmp_path / "hosts.txt").write_text("# URLhaus mirror\n0.0.0.0 malware.example\n127.0.0.1 bad.example # note\n")
    (tmp_path / "plain.txt").write_text("custom.example\nlocalhost\nnot a domain at all\n")
    domains = load_blocklist([tmp_path / "easyprivacy.txt", tmp_path / "hosts.txt", tmp_path / "plain.txt",
                              tmp_path / "missing.txt"])
    # Only unconditional domain rules: path rules, exceptions and $options are not guessed.
    assert domains == {"tracker.example", "malware.example", "bad.example", "custom.example"}
    assert listed_suffix("a.b.tracker.example", domains) == "tracker.example"
    assert listed_suffix("tracker.example.org", domains) is None


class Upstream:
    """A local resolver: answers 'name' with 93.184.216.34 and counts queries."""

    def __init__(self, break_id=False):
        self.queries = 0
        self.break_id = break_id

    def answer(self, data):
        self.queries += 1
        request = DNSRecord.parse(data)
        reply = request.reply()
        reply.add_answer(RR(request.q.qname, QTYPE.A, ttl=30, rdata=A("93.184.216.34")))
        if self.break_id:
            reply.header.id = (request.header.id + 1) % 65536
        return reply.pack()

    async def start(self):
        loop = asyncio.get_running_loop()
        outer = self

        class Proto(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                self.transport.sendto(outer.answer(data), addr)

        self.transport, _ = await loop.create_datagram_endpoint(Proto, local_addr=("127.0.0.1", 0))
        address = self.transport.get_extra_info("sockname")

        async def tcp(reader, writer):  # a truncated answer makes clients retry over TCP
            size = struct.unpack("!H", await reader.readexactly(2))[0]
            answer = outer.answer(await reader.readexactly(size))
            writer.write(struct.pack("!H", len(answer)) + answer)
            await writer.drain()
            writer.close()

        self.tcp = await asyncio.start_server(tcp, "127.0.0.1", address[1])
        return address


def query(name, qtype="A"):
    return DNSRecord.question(name, qtype).pack()


def rows(watch):
    return watch.db.execute("SELECT client, qname, qtype, rcode, answers, blocked, listed FROM queries").fetchall()


def test_observe_forwards_unchanged_logs_answers_and_refuses_outsiders(tmp_path):
    async def scenario():
        upstream = Upstream()
        address = await upstream.start()
        watch = Watch(tmp_path / "dns.sqlite", address, ["127.0.0.0/8"], {"tracker.example"}, mode="observe")
        reply = DNSRecord.parse(await watch.handle(query("www.tracker.example"), "127.0.0.1"))
        assert [str(r.rdata) for r in reply.rr] == ["93.184.216.34"]
        refused = DNSRecord.parse(await watch.handle(query("example.com"), "203.0.113.9"))
        assert refused.header.rcode == RCODE.REFUSED
        assert await watch.handle(b"not dns", "127.0.0.1") is None
        upstream.transport.close()
        return upstream.queries, rows(watch)

    count, logged = asyncio.run(scenario())
    assert count == 1  # the outsider never reached the upstream resolver
    assert logged == [("127.0.0.1", "www.tracker.example", "A", "NOERROR", json.dumps(["93.184.216.34"]), 0,
                       "tracker.example")]


def test_block_mode_sinkholes_listed_names_without_asking_upstream(tmp_path):
    async def scenario():
        upstream = Upstream()
        address = await upstream.start()
        watch = Watch(tmp_path / "dns.sqlite", address, ["127.0.0.0/8"], {"tracker.example"}, mode="block",
                      never_block={"needed.tracker.example"})
        a = DNSRecord.parse(await watch.handle(query("px.tracker.example"), "127.0.0.1"))
        aaaa = DNSRecord.parse(await watch.handle(query("px.tracker.example", "AAAA"), "127.0.0.1"))
        https = DNSRecord.parse(await watch.handle(query("px.tracker.example", "HTTPS"), "127.0.0.1"))
        kept = DNSRecord.parse(await watch.handle(query("needed.tracker.example"), "127.0.0.1"))
        upstream.transport.close()
        return a, aaaa, https, kept, upstream.queries, rows(watch)

    a, aaaa, https, kept, count, logged = asyncio.run(scenario())
    assert [str(r.rdata) for r in a.rr] == ["0.0.0.0"]
    assert [str(r.rdata) for r in aaaa.rr] == ["::"]
    assert https.rr == [] and https.header.rcode == RCODE.NOERROR
    assert [str(r.rdata) for r in kept.rr] == ["93.184.216.34"]
    assert count == 1
    assert [r[5] for r in logged] == [1, 1, 1, 0]


def test_unanswered_or_mismatched_upstream_gives_servfail(tmp_path):
    async def scenario():
        dead = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dead.bind(("127.0.0.1", 0))  # bound but never answers
        watch = Watch(tmp_path / "a.sqlite", dead.getsockname(), ["127.0.0.0/8"], set(), timeout=0.3)
        timeout = DNSRecord.parse(await watch.handle(query("example.com"), "127.0.0.1"))
        dead.close()
        liar = Upstream(break_id=True)
        address = await liar.start()
        watch2 = Watch(tmp_path / "b.sqlite", address, ["127.0.0.0/8"], set())
        mismatch = DNSRecord.parse(await watch2.handle(query("example.com"), "127.0.0.1"))
        liar.transport.close()
        return timeout, mismatch, rows(watch)

    timeout, mismatch, logged = asyncio.run(scenario())
    assert timeout.header.rcode == RCODE.SERVFAIL
    assert mismatch.header.rcode == RCODE.SERVFAIL
    assert logged[0][3] == "SERVFAIL"


def test_udp_and_tcp_listeners_answer_real_clients(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    async def scenario():
        upstream = Upstream()
        address = await upstream.start()
        watch = Watch(tmp_path / "dns.sqlite", address, ["127.0.0.0/8"], set())
        ready = asyncio.Event()
        server = asyncio.create_task(dnswatch.serve(watch, "127.0.0.1", port, ready))
        await ready.wait()

        def ask_udp():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(3)
                s.sendto(query("udp.example"), ("127.0.0.1", port))
                return DNSRecord.parse(s.recv(4096))

        def ask_tcp():
            with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
                packet = query("tcp.example")
                s.sendall(struct.pack("!H", len(packet)) + packet)
                size = struct.unpack("!H", s.recv(2))[0]
                return DNSRecord.parse(s.recv(size))

        udp = await asyncio.to_thread(ask_udp)
        tcp = await asyncio.to_thread(ask_tcp)
        server.cancel()
        upstream.transport.close()
        return udp, tcp, rows(watch)

    udp, tcp, logged = asyncio.run(scenario())
    assert str(udp.rr[0].rdata) == "93.184.216.34" and str(tcp.rr[0].rdata) == "93.184.216.34"
    assert {r[1] for r in logged} == {"udp.example", "tcp.example"}


def test_retention_and_blocklist_reload(tmp_path):
    listed = tmp_path / "list.txt"
    listed.write_text("one.example\n")
    watch = Watch(tmp_path / "dns.sqlite", ("127.0.0.1", 9), ["127.0.0.0/8"], load_blocklist([listed]),
                  retention_days=1, blocklists=[listed])
    watch.db.execute("INSERT INTO queries VALUES (1, '127.0.0.1', 'old.example', 'A', 'NOERROR', '[]', 0, NULL, NULL)")
    watch.log("127.0.0.1", "new.example", "A", "NOERROR", [], False, None)
    watch.prune()
    assert [r[1] for r in rows(watch)] == ["new.example"]
    assert watch.reload_if_changed() is False
    listed.write_text("one.example\ntwo.example\n")
    import os
    os.utime(listed, (listed.stat().st_atime, listed.stat().st_mtime + 5))
    assert watch.reload_if_changed() is True and watch.blocked == {"one.example", "two.example"}


def test_ipv4_mapped_clients_and_upstream_parsing():
    watch = Watch(":memory:", ("127.0.0.1", 53), ["192.168.1.0/24"], set())
    assert watch.allowed("::ffff:192.168.1.20") is True
    assert watch.allowed("192.168.2.1") is False and watch.allowed("garbage") is False
    assert dnswatch.parse_upstream("192.168.1.1") == ("192.168.1.1", 53)
    assert dnswatch.parse_upstream("1.1.1.1:5353") == ("1.1.1.1", 5353)
    assert dnswatch.parse_upstream("auto") == "auto"


def test_shipped_dns_tracker_list_blocks_trackers_but_not_the_platforms_themselves():
    shipped = load_blocklist([dnswatch.Path(dnswatch.__file__).with_name("dns_trackers.txt")])
    for name in ("www.google-analytics.com", "ssl.google-analytics.com", "connect.facebook.net", "bat.bing.com",
                 "app-measurement.com", "analytics.tiktok.com", "static.hotjar.com", "sb.scorecardresearch.com"):
        assert listed_suffix(name, shipped), name
    for name in ("www.google.com", "www.facebook.com", "www.cloudflare.com", "www.apple.com", "www.microsoft.com",
                 "login.microsoftonline.com", "fonts.gstatic.com", "www.youtube.com", "www.hotjar.com",
                 "www.abc.net.au", "graph.facebook.com"):
        assert listed_suffix(name, shipped) is None, name


def test_auto_upstream_follows_the_uplinks_resolver(tmp_path):
    conf = tmp_path / "resolv.conf"
    conf.write_text("# Generated by NetworkManager\nnameserver 127.0.0.53\nnameserver fe80::1%eth0\n"
                    "nameserver 10.42.0.1\nnameserver 192.168.1.1\n")
    assert dnswatch.system_resolver(conf, {"10.42.0.1"}) == ("192.168.1.1", 53)
    assert dnswatch.system_resolver(tmp_path / "missing") is None
    watch = Watch(":memory:", "auto", ["127.0.0.0/8"], set(), resolv_conf=conf, portal_ip="10.42.0.1")
    assert watch.current_upstream() == ("192.168.1.1", 53)
    conf.write_text("nameserver 127.0.0.1\n")
    watch.upstream_checked = 0
    assert watch.current_upstream() == ("1.1.1.1", 53)  # nothing usable: a public resolver


# --------------------------------------------------------- DataExodus Wi-Fi

PHONE, VISITOR, LAPTOP = "10.42.0.23", "10.42.0.77", "192.168.1.9"


def hotspot_watch(tmp_path, address, arp_lines=()):
    arp = tmp_path / "arp"
    arp.write_text("IP address       HW type     Flags       HW address            Mask     Device\n"
                   + "".join(f"{ip}        0x1         {flags}         {mac}     *        wlan0\n"
                             for ip, flags, mac in arp_lines))
    devices = dnswatch.Devices(tmp_path / "devices.json", arp=arp, refresh=0)
    watch = Watch(tmp_path / "dns.sqlite", address, ["192.168.1.0/24"], {"tracker.example"},
                  portal_net="10.42.0.0/24", portal_ip="10.42.0.1", portal_name="dataexodus.home.arpa",
                  devices=devices)
    return watch, devices


def test_hotspot_devices_are_logged_only_after_opting_in_and_tagged(tmp_path):
    async def scenario():
        upstream = Upstream()
        address = await upstream.start()
        watch, devices = hotspot_watch(tmp_path, address, [(PHONE, "0x2", "aa:bb:cc:00:00:23")])
        await watch.handle(query("before.example"), PHONE)          # no choice yet: answered, not logged
        devices.set(PHONE, watch=True, block=False)
        await watch.handle(query("after.example"), PHONE)
        devices.set(VISITOR, watch=False, block=False)
        await watch.handle(query("private.example"), VISITOR)       # chose not to be shown: not logged
        await watch.handle(query("laptop.example"), LAPTOP)         # a LAN device the owner allowed: as before
        upstream.transport.close()
        return upstream.queries, watch.db.execute("SELECT client, qname, device FROM queries").fetchall()

    count, logged = asyncio.run(scenario())
    assert count == 4  # every device got real answers
    assert logged == [(PHONE, "after.example", "mac:aa:bb:cc:00:00:23"), (LAPTOP, "laptop.example", None)]


def test_per_device_blocking_and_captive_names(tmp_path):
    async def scenario():
        upstream = Upstream()
        address = await upstream.start()
        watch, devices = hotspot_watch(tmp_path, address)
        devices.set(PHONE, watch=True, block=True)
        devices.set(VISITOR, watch=True, block=False)
        blocked = DNSRecord.parse(await watch.handle(query("px.tracker.example"), PHONE))
        allowed = DNSRecord.parse(await watch.handle(query("px.tracker.example"), VISITOR))
        captive = DNSRecord.parse(await watch.handle(query("connectivitycheck.gstatic.com"), PHONE))
        portal = DNSRecord.parse(await watch.handle(query("dataexodus.home.arpa"), VISITOR))
        portal6 = DNSRecord.parse(await watch.handle(query("captive.apple.com", "AAAA"), VISITOR))
        lan = DNSRecord.parse(await watch.handle(query("captive.apple.com"), LAPTOP))
        upstream.transport.close()
        rows = watch.db.execute("SELECT client, qname, blocked FROM queries ORDER BY rowid").fetchall()
        return blocked, allowed, captive, portal, portal6, lan, upstream.queries, rows

    blocked, allowed, captive, portal, portal6, lan, count, rows = asyncio.run(scenario())
    assert [str(r.rdata) for r in blocked.rr] == ["0.0.0.0"]
    assert [str(r.rdata) for r in allowed.rr] == ["93.184.216.34"]
    assert [str(r.rdata) for r in captive.rr] == ["10.42.0.1"] and [str(r.rdata) for r in portal.rr] == ["10.42.0.1"]
    assert portal6.rr == [] and portal6.header.rcode == RCODE.NOERROR
    assert [str(r.rdata) for r in lan.rr] == ["93.184.216.34"]  # LAN devices are not redirected to the portal
    assert count == 2  # the visitor's tracker lookup and the LAN device's
    # Captive-portal and portal names are infrastructure, never logged for hotspot devices;
    # the LAN device's ordinary lookup is logged as before.
    assert rows == [(PHONE, "px.tracker.example", 1), (VISITOR, "px.tracker.example", 0),
                    (LAPTOP, "captive.apple.com", 0)]


def test_hotspot_lookups_expire_sooner_and_old_logs_gain_the_device_column(tmp_path):
    import sqlite3
    db = tmp_path / "old.sqlite"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE queries (ts INTEGER NOT NULL, client TEXT NOT NULL, qname TEXT NOT NULL, "
                      "qtype TEXT NOT NULL, rcode TEXT NOT NULL, answers TEXT NOT NULL, blocked INTEGER NOT NULL, listed TEXT);"
                      "INSERT INTO queries VALUES (strftime('%s','now') - 7200, '192.168.1.9', 'kept.example', 'A', "
                      "'NOERROR', '[]', 0, NULL);")
    con.commit()
    con.close()
    watch = Watch(db, ("127.0.0.1", 9), ["192.168.1.0/24"], set(), portal_net="10.42.0.0/24",
                  portal_retention_hours=1)
    import time as clock
    watch.db.execute("INSERT INTO queries VALUES (?, ?, 'phone-old.example', 'A', 'NOERROR', '[]', 0, NULL, 'mac:x')",
                     (int(clock.time()) - 7200, PHONE))
    watch.log(PHONE, "phone-new.example", "A", "NOERROR", [], False, None, "mac:x")
    watch.prune()
    assert sorted(r[0] for r in watch.db.execute("SELECT qname FROM queries")) == ["kept.example", "phone-new.example"]


def test_device_keys_follow_the_mac_not_the_address(tmp_path):
    arp = tmp_path / "arp"
    arp.write_text("IP address HW type Flags HW address Mask Device\n"
                   "10.42.0.23 0x1 0x2 AA:BB:CC:00:00:01 * wlan0\n10.42.0.24 0x1 0x0 00:00:00:00:00:00 * wlan0\n")
    devices = dnswatch.Devices(tmp_path / "devices.json", arp=arp, refresh=0)
    devices.set("10.42.0.23", watch=True, block=False)
    assert devices.get("10.42.0.23")["key"] == "mac:aa:bb:cc:00:00:01"
    assert devices.get("10.42.0.24") is None  # incomplete neighbour entry: no inherited choice
    # The phone moves to another address: its choice follows it.
    arp.write_text("IP address HW type Flags HW address Mask Device\n10.42.0.40 0x1 0x2 aa:bb:cc:00:00:01 * wlan0\n")
    assert devices.get("10.42.0.40")["watch"] is True and devices.get("10.42.0.23") is None
    assert devices.forget("10.42.0.40") == "mac:aa:bb:cc:00:00:01" and devices.all() == {}
