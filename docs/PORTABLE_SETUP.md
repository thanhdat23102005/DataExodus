# Running the box away from your own network

```
your phone (4G/5G) ──USB cable──> Raspberry Pi 5 ──Wi-Fi "DataExodus-Box"──> visitors' phones, your laptop
```

The Pi takes its internet from a phone over a USB cable (USB tethering) and
serves the `DataExodus-Box` Wi-Fi from it. No venue network, no Ethernet socket,
no permission to plug into anything.

## What to bring

- The Pi 5 and its **official 27 W USB-C power supply**, into a wall socket. A
  phone charger or a weak power bank will brown it out, and an undervolted Pi
  drops its Wi-Fi.
- **A USB cable that carries data**, USB-A into the Pi and whatever your phone
  takes at the other end. Test the exact cable at home — charge-only cables look
  identical and fail silently.
- A phone with 4G/5G, charged, with at least 1 GB of data left.
- The printed QR card: open `reports/wifi-card.html` and press Ctrl+P.
- The laptop and its charger, for the Guard half.
- **A fallback that needs no Pi at all:**
  ```powershell
  python -m examples.run_box_acceptance --out reports\box-run --headed
  ```
  That walks the whole visitor flow on the laptop.

## Once, at home

The Pi is already prepared (`--prepare`): the Wi-Fi, the portal and the sample
links are installed, but it is still using the home network.

1. If you also want a 50-site study run, start it **before step 2**, while the
   Pi still has the home connection:
   ```bash
   sudo systemctl start dataexodus-study
   ```
2. **Switch the Pi to serving its own Wi-Fi:**
   ```bash
   cd ~/DataExodus && sudo bash pi/hotspot.sh --on
   ```
   The script warns that the SSH session is about to drop and counts down 10
   seconds. That is expected. From here on it brings up `DataExodus-Box` on every
   boot.
3. **Rehearse the whole sequence below at home.** Join `DataExodus-Box` from the
   laptop or a second phone — not from the phone that is sharing its connection.

## On site, about five minutes beforehand

1. **Power the Pi.** Give it a minute, until `DataExodus-Box` appears in the
   laptop's Wi-Fi list.
2. **On the phone that will provide the uplink:** turn **Wi-Fi off**, so it
   cannot latch onto the venue network, and turn **mobile data on**.
3. **Plug the cable** into the Pi's USB-A port and turn tethering on:
   - **Android:** Settings → Connections → Mobile Hotspot and Tethering → **USB
     tethering**. On a Pixel: Network & internet → Hotspot & tethering → USB
     tethering.
   - **iPhone:** Settings → Personal Hotspot → **Allow Others to Join**, then
     tap **Trust** when the cable goes in. The Pi already has the packages
     iPhone tethering needs.
4. **Check it from the laptop:**
   1. Join `DataExodus-Box`. The welcome page should open by itself; if not, open
      `http://10.42.0.1`.
   2. Press **Join and continue**.
   3. Open **Check a link** and try one of the samples.
   4. Then try a real link, say `https://www.abc.net.au`. A real link working is
      the proof that the phone's connection is reaching through.
5. **The Guard half.** Leave the laptop on `DataExodus-Box` and run:
   ```powershell
   cd C:\DataExodus
   powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost 10.42.0.1 -User admin -CopyToken
   ```
   It asks for the Pi's `admin` password. Leave that window open.
6. **Hand over the QR card.** A seven-minute walkthrough is in
   [HOTSPOT.md](HOTSPOT.md), section 4.

## When something goes wrong

From the laptop on `DataExodus-Box`, `ssh admin@10.42.0.1`, then:

```bash
nmcli device                      # wlan0: DataExodus-AP; usb0 (or enx...): connected = the phone is feeding it
ip -4 route show default          # the first line must say dev usb0
systemctl is-active dataexodus-portal dataexodus-dnswatch dataexodus-guard
```

| Symptom | What it is |
| --- | --- |
| No `DataExodus-Box` after two minutes | The Pi was never switched over (`--on`), or it is undervolted. Re-seat the power supply; failing that, use the laptop fallback. |
| Wi-Fi joins, but real links will not open | USB tethering is off, or the cable is charge-only. `nmcli device` must show `usb0` as connected. Toggle tethering off and on. |
| A visitor's phone says "no internet" | They need to press **Join and continue** first. If it persists, check tethering as above. |
| The welcome page does not open itself | Open `http://10.42.0.1`. A phone with a VPN or Private DNS will not get the automatic pop-up. |
| No mobile signal in the room | The portal and the four sample links still work offline, Safe Browse on a sample included. Real links and *My device* with real apps need the connection. |
| The phone gets hot or drains | The Pi back-feeds a little power over USB, but not much. Start fully charged. |

### Wi-Fi is flaky or slow

On the Pi:

```bash
vcgencmd get_throttled            # 0x0 = power is fine; anything else (e.g. 0x50005) = UNDERVOLTED, use the 27 W supply
ip -4 route show default          # must show dev usb0 (or enx...) = the phone's connection is up
ping -c 5 -q 1.1.1.1 | tail -2    # packet loss, or over ~150 ms, means weak mobile signal
sudo iw dev wlan0 info | grep -E 'channel|txpower'
sudo iw dev wlan0 station dump | grep -E 'Station|signal:|tx bitrate'
```

**Move the Wi-Fi to 5 GHz** — faster and far less crowded than 2.4 GHz, and
every recent phone supports it. The command below falls back to 2.4 GHz by
itself if 5 GHz will not come up. SSH drops for about ten seconds, then rejoin
`DataExodus-Box`:

```bash
sudo setsid nohup bash -c 'nmcli connection modify DataExodus-AP 802-11-wireless.band a 802-11-wireless.channel 36 && nmcli connection up DataExodus-AP || { nmcli connection modify DataExodus-AP 802-11-wireless.band bg 802-11-wireless.channel 6; nmcli connection up DataExodus-AP; }' > /dev/null 2>&1 &
```

With the current `hotspot.sh` there is a cleaner way:

```bash
sudo HOTSPOT_BAND=a bash pi/hotspot.sh --prepare && sudo bash pi/hotspot.sh --on
```

**Data use:** roughly 1–5 MB per link check, a few MB per Safe Browse session. A
fifteen-minute session usually costs 50–200 MB. Worth asking people not to
stream video over this Wi-Fi.

## Afterwards

Back in range of the home Wi-Fi: join `DataExodus-Box` from the laptop,
`ssh admin@10.42.0.1`, then:

```bash
cd ~/DataExodus && sudo bash pi/hotspot.sh --home
```

SSH drops and the Pi returns to the home network at `192.168.0.83`. Run `--on`
again next time.
