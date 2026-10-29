#!/usr/bin/env bash
# DataExodus Box: the "DataExodus-Box" Wi-Fi with a captive portal, so a visitor
# can try the box with their own phone.
#
#   sudo bash pi/hotspot.sh --prepare   set everything up; the Pi stays on its current Wi-Fi
#   sudo bash pi/hotspot.sh --on        demo mode: the Pi's Wi-Fi becomes DataExodus-Box,
#                                       now and after every boot (until --home)
#   sudo bash pi/hotspot.sh --home      back to the saved home Wi-Fi; the setup is kept
#   sudo bash pi/hotspot.sh --off       remove the DataExodus Wi-Fi completely
#   sudo bash pi/hotspot.sh             --prepare and --on in one go
#
# In demo mode the Pi reaches the internet through a phone's USB tethering or an
# Ethernet cable. Without either, the portal and the sample links still work.
# Switching modes drops an SSH session that runs over that Wi-Fi: the script
# then finishes by itself in the background (log: /var/log/dataexodus-hotspot.log).
# Settings (optional, in /etc/dataexodus/dataexodus.env or the environment):
#   HOTSPOT_SSID, HOTSPOT_PSK (8+ characters), HOTSPOT_IFACE (wlan0), HOTSPOT_COUNTRY (AU),
#   HOTSPOT_BAND (bg = 2.4 GHz, reaches every phone; a = 5 GHz, faster and less crowded),
#   HOTSPOT_CHANNEL (6 for 2.4 GHz, 36 for 5 GHz)
set -euo pipefail

APP=/opt/dataexodus
CONF=/etc/dataexodus
ENV_FILE="$CONF/dataexodus.env"
CON=DataExodus-AP
DNSMASQ_CONF=/etc/NetworkManager/dnsmasq-shared.d/dataexodus.conf
PORTAL_IP=10.42.0.1
PORTAL_NET=10.42.0.0/24
LOG=/var/log/dataexodus-hotspot.log
SELF="$(readlink -f "$0")"
MODE="${1:-}"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

case "$MODE" in ""|--prepare|--on|--home|--off) ;; *) die "unknown option $MODE (use --prepare, --on, --home or --off)" ;; esac
[[ $EUID -eq 0 ]] || die "run it with sudo: sudo bash pi/hotspot.sh $MODE"
[[ -f "$ENV_FILE" && -x "$APP/.venv/bin/python" ]] || die "run sudo bash pi/install.sh first"
command -v nmcli >/dev/null || die "NetworkManager (nmcli) is required: Raspberry Pi OS Bookworm or newer"

# Settings already saved win over defaults; the environment wins over both.
setting() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true; }
set_setting() {
  local key="$1" value="$2" escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')"
  if grep -qE "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$escaped|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

IFACE="${HOTSPOT_IFACE:-$(setting HOTSPOT_IFACE)}"; IFACE="${IFACE:-wlan0}"
have_profile() { nmcli -t -f NAME connection show | grep -qx "$CON"; }

# Is an SSH session connected through the Wi-Fi interface that is about to change mode?
ssh_through_iface() {
  local ip
  for ip in $(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{split($4, a, "/"); print a[1]}'); do
    ss -Htn state established '( sport = :22 )' 2>/dev/null | awk '{print $3}' | grep -qx "$ip:22" && return 0
  done
  return 1
}

# Switching the radio drops such a session, which would stop this script half-way.
# Re-run it detached instead, so it always finishes.
detach_if_needed() {
  [[ -z "${HOTSPOT_DETACHED:-}" ]] || return 0
  ssh_through_iface || return 0
  echo "Your SSH session runs over $IFACE, which is about to change mode, so the session will drop."
  echo "The change finishes by itself. Its log: $LOG"
  if [[ "$MODE" == "--home" || "$MODE" == "--off" ]]; then
    echo "Afterwards, connect to the Pi over your home Wi-Fi again."
  else
    local ssid; ssid="$(setting HOTSPOT_SSID)"
    echo "Afterwards, join the Wi-Fi \"${ssid:-DataExodus-Box}\" (password: HOTSPOT_PSK in $ENV_FILE) and use: ssh ${SUDO_USER:-<user>}@$PORTAL_IP"
  fi
  if [[ -t 0 ]]; then echo "Starting in 10 seconds (Ctrl+C to cancel)..."; sleep 10; fi
  HOTSPOT_DETACHED=1 setsid nohup bash "$SELF" "$MODE" > "$LOG" 2>&1 < /dev/null &
  exit 0
}

prepare() {
  say "Wi-Fi country and radio"
  local country ssid psk band channel
  country="${HOTSPOT_COUNTRY:-$(setting HOTSPOT_COUNTRY)}"; country="${country:-AU}"
  if command -v raspi-config >/dev/null; then raspi-config nonint do_wifi_country "$country" || true; fi
  command -v iw >/dev/null && iw reg set "$country" || true
  rfkill unblock wifi 2>/dev/null || true

  ssid="${HOTSPOT_SSID:-$(setting HOTSPOT_SSID)}"; ssid="${ssid:-DataExodus-Box}"
  psk="${HOTSPOT_PSK:-$(setting HOTSPOT_PSK)}"
  if [[ -z "$psk" ]]; then
    # Easy to read aloud and type on a phone: no 0/O or 1/l.
    psk="$(python3 -c 'import secrets; a="abcdefghjkmnpqrstuvwxyz23456789"; print("-".join("".join(secrets.choice(a) for _ in range(4)) for _ in range(3)))')"
  fi
  (( ${#psk} >= 8 )) || die "HOTSPOT_PSK must have at least 8 characters"
  [[ "$ssid$psk" != *$'\n'* && "$ssid$psk" != *'"'* ]] || die "HOTSPOT_SSID / HOTSPOT_PSK must not contain quotes or line breaks"
  band="${HOTSPOT_BAND:-$(setting HOTSPOT_BAND)}"; band="${band:-bg}"
  [[ "$band" == bg || "$band" == a ]] || die "HOTSPOT_BAND must be bg (2.4 GHz) or a (5 GHz)"
  channel="${HOTSPOT_CHANNEL:-$(setting HOTSPOT_CHANNEL)}"
  if [[ -z "$channel" || ( "$band" == a && "$channel" -lt 36 ) || ( "$band" == bg && "$channel" -gt 14 ) ]]; then
    channel=$([[ "$band" == a ]] && echo 36 || echo 6)
  fi

  say "DHCP by NetworkManager, DNS by the DataExodus DNS watch"
  install -d -m 755 "$(dirname "$DNSMASQ_CONF")"
  cat > "$DNSMASQ_CONF" <<EOF
# DataExodus (pi/hotspot.sh): NetworkManager's dnsmasq hands out addresses on the
# hotspot; the DataExodus DNS watch (port 53) answers the devices' lookups.
port=0
dhcp-option=option:dns-server,$PORTAL_IP
EOF

  say "Access point profile $CON ($ssid on $IFACE, $([[ "$band" == a ]] && echo 5 || echo 2.4) GHz channel $channel)"
  local props=(802-11-wireless.mode ap 802-11-wireless.band "$band"
               802-11-wireless.channel "$channel" 802-11-wireless.ap-isolation yes 802-11-wireless.powersave 2
               wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp
               wifi-sec.psk "$psk" ipv4.method shared ipv4.addresses "$PORTAL_IP/24" ipv6.method disabled)
  if have_profile; then
    nmcli connection modify "$CON" 802-11-wireless.ssid "$ssid" "${props[@]}"   # keeps its on/off state
  else
    # Off until --on: preparing never takes the Pi off its current Wi-Fi.
    nmcli connection add type wifi ifname "$IFACE" con-name "$CON" autoconnect no ssid "$ssid" "${props[@]}" >/dev/null
  fi

  say "Settings"
  set_setting HOTSPOT_SSID "$ssid"
  set_setting HOTSPOT_PSK "$psk"
  set_setting HOTSPOT_IFACE "$IFACE"
  set_setting HOTSPOT_BAND "$band"
  set_setting HOTSPOT_CHANNEL "$channel"
  set_setting HOTSPOT_LEASES "/var/lib/NetworkManager/dnsmasq-$IFACE.leases"
  set_setting PORTAL_NET "$PORTAL_NET"
  set_setting PORTAL_IP "$PORTAL_IP"
  set_setting PORTAL_PORT 80
  grep -qE '^PORTAL_HOSTNAME=' "$ENV_FILE" || set_setting PORTAL_HOSTNAME dataexodus.home.arpa
  set_setting PORTAL_DEVICES /var/lib/dataexodus/portal/devices.json
  grep -qE '^PORTAL_RETENTION_HOURS=' "$ENV_FILE" || set_setting PORTAL_RETENTION_HOURS 24
  # The Pi moves between networks: follow whichever uplink resolver it has.
  set_setting DNSWATCH_UPSTREAM auto
  # The local sample links (examples/sample_links.py) for the link checker.
  set_setting SANDBOX_ALLOW_HOSTS 127.0.0.48/28
  set_setting PORTAL_SAMPLES 1
  install -d -o dataexodus -g dataexodus -m 750 /var/lib/dataexodus/portal

  say "Services"
  systemctl daemon-reload
  systemctl enable dataexodus-samples.service >/dev/null
  systemctl restart dataexodus-samples.service dataexodus-guard.service dataexodus-dnswatch.service dataexodus-box.service
}

ap_up() {
  if ! nmcli connection up "$CON" >/dev/null 2>&1; then
    # Some Wi-Fi driver / supplicant versions do not support client isolation.
    warn "the access point did not start with client isolation; retrying without it (visitors' devices can see each other)"
    nmcli connection modify "$CON" 802-11-wireless.ap-isolation default
    nmcli connection up "$CON" >/dev/null || die "the access point did not start: journalctl -u NetworkManager -n 50"
  fi
}

switch_on() {
  have_profile || die "not prepared yet: sudo bash pi/hotspot.sh --prepare"
  say "Demo mode: $IFACE becomes the DataExodus Wi-Fi (also after every boot)"
  nmcli connection modify "$CON" connection.autoconnect yes connection.autoconnect-priority 100
  ap_up
  systemctl enable dataexodus-portal.service >/dev/null
  systemctl restart dataexodus-portal.service dataexodus-dnswatch.service
  sleep 3
  local uplink http
  uplink="$(ip -4 route show default | awk '{print $5; exit}')"
  # Any HTTP answer means the portal is up (it may refuse the Pi itself with 403).
  http="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://$PORTAL_IP/" || true)"
  [[ "$http" == 403 || "$http" == 200 ]] && echo "Portal:               up on http://$PORTAL_IP" || \
    warn "portal not answering (HTTP ${http:-none}): journalctl -u dataexodus-portal -n 50"
  systemctl is-active -q dataexodus-dnswatch && echo "DNS watch:            answering the hotspot" || \
    warn "DNS watch is not running: journalctl -u dataexodus-dnswatch -n 50"
  if [[ -n "$uplink" && "$uplink" != "$IFACE" ]]; then
    echo "Internet uplink:      $uplink"
  else
    warn "no internet uplink: plug in a phone and turn on USB tethering (or an Ethernet cable). The portal and sample links work without one."
  fi
  local ssid psk
  ssid="$(setting HOTSPOT_SSID)"; psk="$(setting HOTSPOT_PSK)"
  cat <<EOF

The DataExodus Wi-Fi is on.
  Network:  $ssid
  Password: $psk
  Portal:   http://$PORTAL_IP  (or http://dataexodus.home.arpa)
Scan this with a phone camera to join:
EOF
  "$APP/.venv/bin/python" - "$ssid" "$psk" <<'PY' || true
import sys
from segno import helpers
helpers.make_wifi(ssid=sys.argv[1], password=sys.argv[2], security="WPA").terminal(compact=True)
PY
  cat <<EOF
Manage the Pi from a laptop on this Wi-Fi: ssh ${SUDO_USER:-<user>}@$PORTAL_IP
Back to the home Wi-Fi later: sudo bash pi/hotspot.sh --home
EOF
}

switch_home() {
  say "Back to the saved home Wi-Fi"
  if have_profile; then
    nmcli connection modify "$CON" connection.autoconnect no
    nmcli connection down "$CON" >/dev/null 2>&1 || true
  fi
  systemctl disable --now dataexodus-portal.service >/dev/null 2>&1 || true
  nmcli device connect "$IFACE" >/dev/null 2>&1 || warn "no saved Wi-Fi network in range: sudo nmtui to connect"
  sleep 2
  nmcli -t -f DEVICE,STATE,CONNECTION device | grep "^$IFACE:" || true
  echo "The DataExodus Wi-Fi setup is kept: sudo bash pi/hotspot.sh --on switches back."
}

remove_all() {
  say "Removing the DataExodus Wi-Fi"
  systemctl disable --now dataexodus-portal.service dataexodus-samples.service 2>/dev/null || true
  nmcli connection down "$CON" 2>/dev/null || true
  nmcli connection delete "$CON" 2>/dev/null || true
  rm -f "$DNSMASQ_CONF"
  sed -i -e 's|^PORTAL_NET=|#PORTAL_NET=|' -e 's|^HOTSPOT_SSID=|#HOTSPOT_SSID=|' "$ENV_FILE"
  systemctl restart dataexodus-dnswatch.service || true
  nmcli device connect "$IFACE" >/dev/null 2>&1 || true
  echo "Done. $IFACE is free for normal Wi-Fi again (sudo nmtui to connect)."
}

case "$MODE" in
  --prepare) prepare
             echo; echo "Prepared. The Pi stays on its current Wi-Fi. Demo mode: sudo bash pi/hotspot.sh --on" ;;
  --on)      detach_if_needed; switch_on ;;
  --home)    detach_if_needed; switch_home ;;
  --off)     detach_if_needed; remove_all ;;
  "")        detach_if_needed; prepare; switch_on ;;
esac
