# The DataExodus Wi-Fi

The Raspberry Pi 5 serves its own Wi-Fi network, **DataExodus-Box**. A visitor
scans a QR code to join, their phone opens the welcome page by itself (a captive
portal, the same mechanism as hotel Wi-Fi), and from there they get three
things:

| Feature | What the visitor sees |
| --- | --- |
| **Check a link** | Paste a link, or a whole scam message containing one. The Pi opens it in an isolated Chromium and returns a 0–100 score with every reason behind it, the redirect chain, a screenshot, the trackers and companies involved, and the countries their servers are in. **The phone never opens the page.** |
| **Safe Browse** | Use the suspicious page by tapping its picture: scroll, type, go back. The page runs on the Pi; the phone only receives JPEG images. |
| **My device** (only on consent) | Which companies the phone's apps talk to, and where those servers are. A switch blocks trackers for that phone alone, and **Forget this device** deletes everything. |

There are also **four sample links** served by the Pi itself — all fictional and
harmless: an ordinary news article, an ad click, a fake bank sign-in, and a fake
CAPTCHA. They mean the thing can be demonstrated with no internet at all, and
without opening a real scam page in front of anyone.

> **What has actually been tested.** The whole visitor flow — portal, sandbox,
> Safe Browse, DNS watch with consent and per-device blocking, sample links —
> ran in real Chromium on Windows over loopback addresses and passed 19 of 19
> steps (`docs/evidence/box-v05-acceptance.json`, screenshots in
> `docs/evidence/box-v05/`). On a **real Pi 5** the installer, the services, the
> firewall, sandbox scoring (identical scores to Windows, 3.6–5.3 s per link)
> and Safe Browse were all verified
> (`docs/evidence/pi-hardware-verification.txt`). **The radio itself, the portal
> on 10.42.0.1 and the automatic sign-in pop-up on real iPhones and Androids
> have not been run**, because the Pi had no wired uplink at the time. Section 3
> is the checklist for doing that.

## 0. What you need first

- A Pi 5 installed per [RASPBERRY_PI.md](RASPBERRY_PI.md), sections 1–5.
- **An uplink for the Pi that is not Wi-Fi**, because the Pi's own Wi-Fi becomes
  the access point. Any of:
  1. **Ethernet into a router.** Simplest, and what to use at home.
  2. **Ethernet into a Windows laptop**, sharing the laptop's Wi-Fi over that
     port: Control Panel → Network Connections → right-click Wi-Fi → Properties
     → Sharing → tick *Allow other network users to connect…* → pick the
     Ethernet adapter. The Pi gets a 192.168.137.x address.
  3. **An Android phone on USB**, with Settings → Hotspot & tethering → *USB
     tethering*. The Pi picks it up as `usb0`. Full field setup:
     [PORTABLE_SETUP.md](PORTABLE_SETUP.md).
  - **With no uplink:** the portal and the four samples still work. Real links,
    and *My device* with real apps, need one.
- **SSH in over the wire when you run the command**, not over Wi-Fi
  (`ip -4 addr show eth0` gives the wired address). The command switches `wlan0`
  into access-point mode, so an existing Wi-Fi connection goes away. If your SSH
  session is on `wlan0`, the script warns you first, then carries on in the
  background. Wait a minute, reconnect (over the wire, or join the DataExodus
  Wi-Fi and SSH to `10.42.0.1`), and read
  `sudo tail -n 40 /var/log/dataexodus-hotspot.log`.

## 1. Turning the Wi-Fi on

Three modes, run from `~/DataExodus` on the Pi:

| Command | What it does |
| --- | --- |
| `sudo bash pi/hotspot.sh --prepare` | Install everything, but leave the Pi on its current Wi-Fi. |
| `sudo bash pi/hotspot.sh --on` | Serve `DataExodus-Box` — now, and on every boot. |
| `sudo bash pi/hotspot.sh --home` | Back to the home Wi-Fi. The configuration is kept for the next `--on`. |

To do it all in one step, copy the current tree to the Pi
([RASPBERRY_PI.md](RASPBERRY_PI.md), section 3) and run:

```bash
cd ~/DataExodus
sudo bash pi/install.sh --hotspot
```

Re-running that on an existing install is safe: settings, token and data are
kept. It finishes by printing:

```
The DataExodus Wi-Fi is on.
  Network:  DataExodus-Box
  Password: xxxx-xxxx-xxxx        (random, stored in /etc/dataexodus/dataexodus.env)
  Portal:   http://10.42.0.1  (or http://dataexodus.home.arpa)
Scan this with a phone camera to join:
█▀▀▀▀▀█ ...                       (the QR code, in the terminal)
```

To choose the name or password yourself (at least 8 characters):

```bash
sudo HOTSPOT_SSID="DataExodus-Demo" HOTSPOT_PSK="your-password" bash pi/hotspot.sh
```

What the script set up:

- A WPA2 access point on `wlan0` at `10.42.0.1/24`, with **client isolation** —
  a visitor's phone cannot see your laptop on this network.
- NetworkManager hands out addresses (DHCP). DNS is answered by DataExodus's own
  **DNS watch**, not by dnsmasq.
- `dataexodus-portal` (the web portal on `http://10.42.0.1`) and
  `dataexodus-samples` (the sample links on `127.0.0.49–58:8030`, reachable only
  from the sandbox).
- `DNSWATCH_UPSTREAM=auto`, so DNS keeps working whether the Pi is at home, on a
  venue network, or on a tethered phone.

To switch it off and give `wlan0` back: `sudo bash pi/hotspot.sh --off`.

## 2. Printing the QR card

On the laptop, open the tunnel ([RASPBERRY_PI.md](RASPBERRY_PI.md), section 5),
then go to **http://127.0.0.1:8020/card** and press Ctrl+P. The card carries two
QR codes — one to join the Wi-Fi, one to open the portal — and four steps of
instructions.

The laptop can also join the DataExodus Wi-Fi and SSH to `10.42.0.1`:

```powershell
cd C:\DataExodus
powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost 10.42.0.1 -User student -CopyToken
```

## 3. Check it yourself first

Work through this and keep the screenshots.

1. **Join:** scan the QR code with your own phone. Android shows a *Sign in to
   network* notification; iPhone opens a window by itself. If neither happens,
   open `http://10.42.0.1`.
2. **Welcome page:** leave *Show my device's connections* ticked and press **Join
   and continue**. "You're online" means it worked, and the phone now treats the
   network as having internet.
3. **Check a link → Try a sample**, all four:

   | Sample | Expected |
   | --- | --- |
   | Local news article | **Low risk**, 0 |
   | Sponsored deal (an ad click) | **Be careful**, about 35: advertising, a `gclid` click ID, a notification request, a redirect through another site |
   | "Verify your account" text message | **Dangerous**, about 60: password and card form posting to another site, scam wording |
   | Fake "I'm not a robot" check | **Dangerous**, about 85: writes a command to the clipboard, forces a `browser_update.exe` download |

4. **Paste a whole message**, for example
   `KoalaBank: unusual sign-in. Verify: http://127.0.0.55:8030/s/kb7Q`. The Pi
   pulls the link out of the text itself.
5. **Safe Browse:** on the fake bank result, press **Open in Safe Browse**. Tap
   the *Password* field in the picture, type anything in the box below, press
   **Type**, then **Enter ↵**. The page shows *"The form was sent to another
   site"* — what you typed did leave, but from the Pi, not from the phone.
6. **My device:** use a few apps (YouTube, Facebook, a news site), then come
   back. You get domains, companies and countries. Tick **Block known trackers**
   → **Save**, reopen the apps, and *blocked* labels appear.
7. **Forget this device:** the device's data is deleted and the welcome page
   returns.
8. **A real link** (needs the uplink): try an ad link, or anything. The result
   now carries real trackers, real companies and real server countries.

Verification on the Pi:

```bash
nmcli -f NAME,DEVICE,TYPE connection show --active             # DataExodus-AP on wlan0
systemctl --no-pager status dataexodus-portal dataexodus-samples dataexodus-dnswatch
sudo ss -tlnp | grep -E ':(80|8030)\b'                         # 80 on 10.42.0.1 only; 8030 on 127.0.0.x only
cat /var/lib/NetworkManager/dnsmasq-wlan0.leases               # devices that joined
sudo -u dataexodus curl -m 3 http://10.42.0.23/ ; echo "exit=$?"   # use a phone's IP: exit=28 means the sandbox cannot reach it
sudo nft list table inet dataexodus                            # includes 127.0.0.48/28 tcp dport 8030 accept
```

From a laptop on the DataExodus Wi-Fi,
`nslookup connectivitycheck.gstatic.com 10.42.0.1` returns `10.42.0.1`. That
answer is exactly what makes the sign-in window pop up.

## 4. A walkthrough, about seven minutes

| Time | Do | Say |
| --- | --- | --- |
| 0:00–0:45 | Hand over the QR card. They scan; the welcome page opens. | "This is a Raspberry Pi 5's own Wi-Fi. Nothing is recorded unless you agree to it; if you do, it is 24 hours, and only your phone can see it." |
| 0:45–2:30 | Check a link: the fake bank sample, then the fake CAPTCHA. | "The Pi opens the link in a throwaway browser — no cookies, firewalled off the local network. Every point in the score has a named reason. There is no mystery model." |
| 2:30–3:30 | Let them paste a real scam message they have received. | "Your phone does not load that page. Only the Pi does." |
| 3:30–4:45 | Safe Browse: tap the fake bank's form, type, Enter. | "You just used a scam page without any of it running on your device. What got sent, got sent from the Pi." |
| 4:45–6:00 | My device: they open a few apps, look at the companies and countries, turn blocking on. | "Hashing is not anonymisation — a hashed email is still an identifier. Here you can see where the apps' data goes, much of it outside Australia (APP 8). The country is an estimate." |
| 6:00–7:00 | On the laptop: Guard holds an ad click → *Preview in isolated sandbox* → the score comes from the Pi. | "Same sandbox, now driven from a browser extension on a laptop." |
| End | They press **Forget this device**, then forget the Wi-Fi network. | "Deleted now. You do not have to take my word for it." |

## 5. Troubleshooting

| Symptom | What to do |
| --- | --- |
| `the Pi reaches the internet through wlan0 itself` | Plug in Ethernet or USB tethering first, then re-run. For an offline demo only: `sudo HOTSPOT_FORCE=1 bash pi/hotspot.sh`. |
| No DataExodus-Box network | `nmcli connection up DataExodus-AP`, `journalctl -u NetworkManager -n 50`, `rfkill list`. Check the Wi-Fi country: `sudo raspi-config` → Localisation → WLAN Country → AU. |
| It reports *client isolation* failed and retries without it | The Wi-Fi driver does not support it. The access point still works, but guest devices can see each other. Do not leave file shares open on the laptop during a demo. |
| The welcome page does not open itself | Open `http://10.42.0.1`. Some devices skip the captive check: a VPN, Android *Private DNS* set to a specific host, or iCloud Private Relay. |
| *My device* is empty | The device is using its own resolver: Android *Private DNS* (set it to Automatic or Off), a VPN, or Chrome's *Secure DNS*. DNS watch sees nothing then — which is a limit worth stating out loud rather than hiding. |
| A real link reports *could not open* | The Pi has no uplink: check `ip route` for `default via … dev eth0` or `usb0`. |
| *Safe Browse is busy* | One session at a time (`SANDBOX_BROWSE_SESSIONS=1`). Sessions close after two idle minutes. On an 8 GB Pi 5 you can set it to 2 and `sudo systemctl restart dataexodus-guard`. |
| The portal is not running | `journalctl -u dataexodus-portal -n 50`. The service retries until `10.42.0.1` exists. |
| DNS watch will not start (port 53 taken) | `sudo ss -lunp 'sport = :53'`. If it is `systemd-resolved`, set `DNSStubListener=no` in `/etc/systemd/resolved.conf` and restart. |

## 6. Privacy, when other people are using it

- Nothing is recorded unless the visitor ticks *Show my device's connections*.
  If they do, only the names looked up are stored, for 24 hours
  (`PORTAL_RETENTION_HOURS`), and each device can see only its own. **Forget this
  device** deletes it immediately.
- The owner's dashboard (`127.0.0.1:8020`) deliberately does **not** count
  visitors' lookups — only how many devices joined. One honest caveat: anyone
  with root on the Pi can still open the SQLite file.
- Devices are identified by their MAC address on this network. Most phones use a
  random MAC per network. A MAC is still a device identifier: it is stored on
  the Pi and deleted on Forget.
- The Pi is the router for this network, so it *could* see connection metadata.
  DataExodus does not record that and does not decrypt HTTPS. Say so if anyone
  asks.
- Only run this for **invited** people. Do not open this Wi-Fi to strangers in a
  public place.
- The sample links use fictional brands. Anything typed into the fake bank's
  form is discarded — not stored, not logged.

## 7. Limits

- A score comes from **one anonymous visit**. A scam page can serve different
  content to an automated browser (cloaking). A low score does not establish
  that a link is safe.
- The scoring rules are heuristics, published on the portal's *How it works*
  page. Their accuracy against a labelled set of real phishing links has not
  been measured.
- The sandbox reduces risk. It is not a malware analysis VM.
- DNS watch cannot see DoH, DoT or VPN traffic, and it counts lookups, not data
  sent.
- The automatic sign-in window was tested with Chromium on Windows. It has not
  been tried on a real iPhone or Android until section 3 is done.
