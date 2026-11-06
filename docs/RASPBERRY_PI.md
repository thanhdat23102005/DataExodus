# Setting up the Raspberry Pi 5

The Pi is a separate measurement and protection device. The laptop just browses;
anything risky or long-running is handed to the Pi. To let someone try it with
their own phone over the Pi's Wi-Fi, follow this document through section 5,
then go to [HOTSPOT.md](HOTSPOT.md).

| What the Pi runs | What it does | Why it belongs on separate hardware |
| --- | --- | --- |
| **Link check + Safe Browse** (`dataexodus-guard`) | Opens a suspicious link in headless Chromium **on the Pi**, scores it 0–100 with a reason for every point (password form posting to another site, forced download, clipboard write, notification request, lookalike brand, trackers, offshore servers…), screenshots it, and returns a clean link. Safe Browse: use that page by tapping its picture. | A real sandbox — a different machine, its own account, firewalled off the LAN. |
| **Wi-Fi + visitor portal** (`dataexodus-portal`, with `--hotspot`) | The Pi serves its own Wi-Fi; a phone that joins gets the welcome page automatically: check a link, Safe Browse, My device. | Anyone can try it on their own phone. See [HOTSPOT.md](HOTSPOT.md). |
| **DNS watch** (`dataexodus-dnswatch`) | Records the names a device looks up (Wi-Fi guests only if they consent), labelled with tracker, company and country. Has a blocking mode, including per-device blocking. | Measures where **every app's** data goes, not just the browser's. The APP 8 angle. |
| **Scheduled study** (`dataexodus-study.timer`, with `--study`) | Every Sunday at 03:00, crawls the 50-site list and builds a report and audit **against the previous week**. | The research half. Not needed to run the product. |
| **Dashboard** (`dataexodus-box`) | Service, Wi-Fi and DNS status, the **printable QR card** (`/card`), reference data, CPU temperature. | One page that says whether everything is actually up. |

The Pi's admin web services **listen on 127.0.0.1 only**. The laptop reaches them
through an **SSH tunnel** — encrypted, authenticated, and it opens no extra port
on the network. Guard still calls `127.0.0.1:8010` as before. Exactly two
services listen on the network: DNS watch (port 53, answering only permitted
ranges) and the visitor portal (port 80 on the Wi-Fi address `10.42.0.1`,
answering only devices on that Wi-Fi, and only with `--hotspot`).

> **Verified on real hardware, 27 October 2026.** A Raspberry Pi 5 Model B,
> 4 GB, Debian 13 (trixie), kernel 6.18.50, Python 3.13, system Chromium: the
> installer exited 0 with all self-checks passing; the firewall, Guard,
> dashboard, DNS watch and sample services came up; the service account's
> packets to the LAN were dropped while the internet still worked; sandbox
> scoring gave the same scores as on Windows at 3.6–5.3 s per link, and a Safe
> Browse session started in 2.1 s. Full log:
> `docs/evidence/pi-hardware-verification.txt`. **Not covered by that run:** the
> Wi-Fi access point and the portal on 10.42.0.1, because the Pi had no Ethernet
> uplink at the time — see [HOTSPOT.md](HOTSPOT.md) section 3.

## 1. What you need

- A Raspberry Pi 5 (4 GB is enough, 8 GB is more comfortable), a microSD card of
  32 GB or more (an NVMe SSD is better), the official 27 W supply, and
  preferably Ethernet.
- On the Windows laptop: [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
  and the OpenSSH client (Windows 11 ships it; otherwise Settings → System →
  Optional features).
- The project folder on the laptop. The commands below write `C:\DataExodus`; if
  you cloned it somewhere else, substitute your own path.

**Make an SSH key on the laptop** — better than a password. In PowerShell:

```powershell
ssh-keygen -t ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

## 2. Install Raspberry Pi OS

In Raspberry Pi Imager:

1. Device: **Raspberry Pi 5**. OS: **Raspberry Pi OS Lite (64-bit)**.
2. Open OS customisation:
   - Hostname: `dataexodus`
   - Username: for example `student`, with a password
   - Wi-Fi: only fill this in if you are not using Ethernet. If you intend to
     serve the visitor Wi-Fi ([HOTSPOT.md](HOTSPOT.md)), use Ethernet — the Pi's
     own Wi-Fi becomes the access point.
   - Locale: time zone `Australia/Sydney`
   - Services tab: enable **SSH**, choose *Allow public-key authentication
     only*, and paste the `id_ed25519.pub` you just printed.
3. Write the card, put it in the Pi and power it. Give it a minute or two.

From the laptop:

```powershell
ssh student@dataexodus.local
```

If `dataexodus.local` does not resolve, find the Pi's address in the router's
admin page and use that. Then, on the Pi:

```bash
sudo apt update && sudo apt full-upgrade -y
```

## 3. Copy the project to the Pi

A zip is tidiest, because the laptop's folder probably contains a Windows
`.venv` — large and useless on the Pi. Run these in **PowerShell on the laptop**
(prompt `PS C:\...>`), **not** in the Pi's SSH window (prompt `user@host:~ $`):
the `C:\...` paths only exist on the laptop. Replace
`student@dataexodus.local` with your own login and hostname or IP, for example
`admin@Lab.local` or `admin@192.168.0.83`; on the Pi, `hostname -I` prints it.

```powershell
scp C:\DataExodus.zip student@dataexodus.local:~/
ssh student@dataexodus.local "python3 -m zipfile -e DataExodus.zip ."
# Reuse the reference lists and the GeoLite2 file already downloaded on the laptop
# (no second 100 MB download, and no MaxMind key needed on the Pi):
scp -r C:\DataExodus\data\blocklists student@dataexodus.local:~/DataExodus/data/
```

If the zip is somewhere else, such as Downloads, adjust the first `scp` path.

Do not copy a `data/identities.local.yaml` that holds your own real details. If
the study needs a test identity, create that file on the Pi with synthetic data
(section 8).

## 4. Run the installer

On the Pi:

```bash
cd ~/DataExodus
sudo bash pi/install.sh              # add --hotspot for the visitor Wi-Fi, --study for the scheduled study
```

It takes 10–15 minutes and does this:

1. Installs `python3-venv`, `chromium`, `nftables`, `iw`.
2. Creates the `dataexodus` system account, with no login shell.
3. Copies the code to `/opt/dataexodus`; data lives in `/var/lib/dataexodus`.
4. Writes `/etc/dataexodus/dataexodus.env` with a **freshly generated Guard
   token**, mode 640.
5. Loads the nftables rules: the `dataexodus` account can reach the internet but
   **not the LAN** — not the router, and not any phone on the Pi's Wi-Fi.
6. Downloads EasyPrivacy, Tracker Radar and URLhaus, skipping any file you
   already copied across.
7. Starts the services and self-checks them. The study timer only with
   `--study`; the visitor Wi-Fi only with `--hotspot`, which runs
   `pi/hotspot.sh`.

What it should end with:

```
Guard service:        ok
Dashboard:            ok
Firewall:             service account cannot reach 192.168.1.1 (as intended)
Internet:             ok
```

Then **log out and SSH back in once**, so your own account can read the token.

## 5. Connect the laptop to the Pi

On the laptop, in the project folder:

```powershell
cd C:\DataExodus
powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost dataexodus.local -User student -CopyToken
```

- `-CopyToken` puts the token on the clipboard. Open Guard Settings → **Local
  service token**, paste, then **Save and apply rules**.
- **Leave that window open** while you are using it; Ctrl+C closes the tunnel.
- If the laptop is running its own Guard service on port 8010, stop it first.
  The script tells you if the port is busy.

Dashboard: `http://127.0.0.1:8020` on the laptop.

### Trying the Pi's sandbox

1. In Guard Settings, enable **Route ad clicks…** and save.
2. Search on Google or Bing and click a **Sponsored** result.
3. Guard holds the click on its **Quarantine** page: your browser has not
   contacted the ad network at all yet.
4. Press **Preview in isolated sandbox**. The Pi opens the link and returns the
   redirect chain, the trackers, a screenshot, and the line *Opened on:
   dataexodus* naming the machine that actually loaded it.
5. Press **Open clean destination** to reach the advertiser's page without
   `gclid` or `utm_*`.

Note: the `examples.guard_lab` lab runs on the **laptop's** loopback
(127.0.0.x), so the Pi's sandbox cannot see it, and the Pi's firewall blocks
that deliberately. To preview the lab's ad, close the tunnel and run the service
on the laptop as in [GUARD.md](GUARD.md). The acceptance script does this for
you.

## 6. DNS watch: where your own phone sends data

Only do this with a device **you own**. Other people's DNS lookups are their
personal information.

1. Get the Pi's address with `hostname -I`, for example `192.168.1.50`.
2. On the phone, point the Wi-Fi's DNS at it:
   - **Android:** Wi-Fi → the current network → IP settings: *Static* → DNS 1 =
     the Pi's address. **Turn Private DNS off.**
   - **iPhone:** Wi-Fi → (i) → Configure DNS → Manual → keep only the Pi's
     address.
3. Use a few apps normally for about five minutes: news, shopping, social.
4. Open `http://127.0.0.1:8020/dns`. It shows the number of lookups, the share
   going to trackers, the companies behind them, the countries of the answering
   addresses, and a breakdown per device.

Blocking mode: set `DNSWATCH_MODE=block` in `/etc/dataexodus/dataexodus.env` and
`sudo systemctl restart dataexodus-dnswatch`. Listed names then answer
`0.0.0.0`. The list is EasyPrivacy's whole-domain rules, URLhaus, and your own
`/var/lib/dataexodus/data/blocklists/custom.txt` (one domain per line). If an app
breaks, add its domain to `DNSWATCH_NEVER_BLOCK`.

Worth stating plainly alongside any of these numbers:

- A DNS lookup says where a device is *about to* connect. It does **not** say
  what it then sent.
- Country is a GeoIP estimate of the answering address, not where data is
  stored, and on its own it does not establish an APP 8 breach.
- Any app using DNS-over-HTTPS (Private DNS, or a browser's built-in DoH) does
  not pass through DNS watch at all.

## 7. The scheduled study (optional)

Off by default. To enable: `sudo bash pi/install.sh --study`, or
`sudo systemctl enable --now dataexodus-study.timer`. The timer runs every Sunday
at 03:00 in the Pi's time zone; if the Pi is off then, the run moves to the next
boot. To run one now:

```bash
sudo systemctl start dataexodus-study      # ~15-25 minutes for 50 sites
journalctl -u dataexodus-study -f          # progress
```

Results land in `/var/lib/dataexodus/runs/<UTC timestamp>/` and are listed on the
dashboard with links to `audit.html` and `report.md`. From the second run
onwards the audit compares against the last successful one. If the reference
lists or the protocol changed in between, the comparison reports *inconclusive*
rather than claiming an improvement. The Pi keeps the last 8 runs
(`STUDY_KEEP_RUNS`).

The 50-site list is frozen. Do not change it mid-study without recording a
protocol amendment.

## 8. A test identity for the study (optional)

The crawler fills no forms, so an identity is only useful on a site you are
**authorised** to test. If you need one, create it on the Pi with synthetic
data:

```bash
sudo -u dataexodus tee /var/lib/dataexodus/data/identities.local.yaml >/dev/null <<'EOF'
email: [student.demo@example.com]
phone: ["0491 570 006"]
EOF
```

(`example.com` is reserved by RFC 2606; 0491 570 006 is a number ACMA reserves
for fiction.)

## 9. Verification

Run these on the Pi and keep the output:

```bash
systemctl --no-pager status dataexodus-guard dataexodus-box dataexodus-dnswatch
sudo ss -tulpn | grep -E ':(22|53|80|8010|8020|8030)\b'   # 8010/8020 on 127.0.0.1 only; 80 on 10.42.0.1; 8030 on 127.0.0.49-58
sudo nft list table inet dataexodus               # firewall rules and counters
sudo -u dataexodus curl -m 3 http://$(ip -4 route show default | awk '{print $3}')/ ; echo "exit=$?"   # exit=28: blocked
sudo -u dataexodus curl -s -o /dev/null -w '%{http_code}\n' https://example.com/           # 200: the internet still works
systemd-analyze security dataexodus-guard dataexodus-dnswatch dataexodus-box | tail -n 5
```

On the laptop you can also time the sandbox: run one preview and record how long
it takes from the click to the screenshot appearing.

## 10. Troubleshooting

| Symptom | What to do |
| --- | --- |
| `connect-pi.ps1` cannot read the token | Log out and SSH in once more. Or run `sudo grep TOKEN /etc/dataexodus/dataexodus.env` on the Pi. |
| Preview says *Sandbox browser failed to start* | `journalctl -u dataexodus-guard -n 50`. If it is Chromium's own sandbox, set `DATAEXODUS_CHROMIUM_SANDBOX=0` in the env file and `sudo systemctl restart dataexodus-guard`. The firewall still keeps that account off the LAN. |
| Preview says *Only public http(s) URLs…* for a real ad | The router's or ISP's DNS is answering an ad domain with an internal address such as 10.10.10.1, and the sandbox is right to refuse. Give the Pi a public resolver: `sudo nmcli con mod "<connection name>" ipv4.dns 1.1.1.1 ipv4.ignore-auto-dns yes`, then bring the connection back up. |
| DNS watch will not start | Something else holds port 53: `sudo ss -lunp 'sport = :53'`. |
| A phone has no internet after pointing DNS at the Pi | The phone's address has to be inside `DNSWATCH_ALLOW`. Check `journalctl -u dataexodus-dnswatch`. |
| Dashboard says "Guard: token mismatch" | The token in the env file changed without a restart: `sudo systemctl restart dataexodus-guard dataexodus-box`. |
| You want a different upstream resolver | Change `DNSWATCH_UPSTREAM` (default `auto`: whatever resolver the Pi's own network gave it, read from `/etc/resolv.conf`, falling back to 1.1.1.1), then restart `dataexodus-dnswatch`. |

## 11. Updating and removing

To update: copy the new project folder across and run `sudo bash pi/install.sh`
again. Settings, token, data and past runs are kept.

To remove:

```bash
sudo bash pi/hotspot.sh --off      # if the visitor Wi-Fi was on
sudo systemctl disable --now dataexodus-guard dataexodus-box dataexodus-dnswatch dataexodus-study.timer dataexodus-firewall
sudo rm /etc/systemd/system/dataexodus-*.service /etc/systemd/system/dataexodus-study.timer
sudo systemctl daemon-reload
sudo rm -rf /opt/dataexodus /etc/dataexodus      # add /var/lib/dataexodus to delete the data too
sudo userdel dataexodus
```

## 12. Limits

- The sandbox reports **what a page did in one anonymous visit**. A clean result
  does not establish that a page is safe; it may behave differently for a
  signed-in browser.
- The application's SSRF guard checks the address before every request. The
  nftables firewall is the second layer, for DNS rebinding. Neither replaces a
  dedicated VM for real malware.
- DNS watch sees no content, cannot see DoH or DoT queries, and counts lookups
  rather than data transferred.
- There has been no trial with users outside the project, no performance
  measurement beyond the figures above, and no claim of complete protection.
