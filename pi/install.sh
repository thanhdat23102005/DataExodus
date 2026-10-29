#!/usr/bin/env bash
# DataExodus Box installer: Raspberry Pi 5 with Raspberry Pi OS 64-bit (Bookworm or newer).
#
#   cd ~/DataExodus_Final && sudo bash pi/install.sh [--hotspot] [--study]
#
# Safe to run again after copying a newer project version: the settings file,
# the Guard token, reference lists, DNS log and study runs are kept.
# What it sets up (details: docs/RASPBERRY_PI_VI.md, docs/HOTSPOT_VI.md):
#   dataexodus-guard    link checker, Safe Browse and Guard service, 127.0.0.1:8010
#   dataexodus-box      dashboard and printable Wi-Fi card, 127.0.0.1:8020
#   dataexodus-dnswatch DNS watch on port 53 for the networks you allow
#   dataexodus-firewall nftables: the service account cannot reach your LAN
#   --hotspot           the DataExodus Wi-Fi + captive portal (pi/hotspot.sh), sample links
#   --study             the weekly crawl of the research site list (timer, Sunday 03:00)
set -euo pipefail

WITH_HOTSPOT=0
WITH_STUDY=0
for arg in "$@"; do
  case "$arg" in
    --hotspot) WITH_HOTSPOT=1 ;;
    --study) WITH_STUDY=1 ;;
    *) printf 'unknown option: %s (use --hotspot and/or --study)\n' "$arg" >&2; exit 2 ;;
  esac
done

APP=/opt/dataexodus
STATE=/var/lib/dataexodus
CONF=/etc/dataexodus
SVC_USER=dataexodus
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADMIN="${SUDO_USER:-}"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run it with sudo: sudo bash pi/install.sh"
[[ -f "$SRC/protection/api.py" && -f "$SRC/pi/dnswatch.py" ]] || die "run it from the DataExodus project folder"
[[ "$(uname -m)" == "aarch64" ]] || warn "expected 64-bit Raspberry Pi OS (aarch64), found $(uname -m)"
grep -qa "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null || warn "this is not a Raspberry Pi 5; continuing anyway"

say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv python3-dev build-essential nftables rsync curl iw usbmuxd
apt-get install -y chromium || apt-get install -y chromium-browser
CHROMIUM="$(command -v chromium || command -v chromium-browser || true)"
[[ -n "$CHROMIUM" ]] || die "Chromium was not found after installing it"

say "Service account and folders"
id -u "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin "$SVC_USER"
install -d -m 755 "$APP"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$STATE" "$STATE/data" "$STATE/data/blocklists" "$STATE/runs" "$STATE/reports"
install -d -o root -g "$SVC_USER" -m 750 "$CONF"
# Lets you read the token over SSH (pi/connect-pi.ps1 -CopyToken) after you log in again.
if [[ -n "$ADMIN" && "$ADMIN" != root ]]; then usermod -aG "$SVC_USER" "$ADMIN"; fi

say "Copying DataExodus to $APP"
rsync -a --delete --exclude '/.venv/' --exclude '/data' --exclude '/reports' \
      --exclude '__pycache__/' --exclude '.pytest_cache/' "$SRC/" "$APP/"
# The project's data/ and reports/ defaults point at the writable state folder.
for dir in data reports; do
  if [[ ! -L "$APP/$dir" ]]; then rm -rf "${APP:?}/$dir"; ln -s "$STATE/$dir" "$APP/$dir"; fi
done
install -o "$SVC_USER" -g "$SVC_USER" -m 640 "$SRC/data/sites.yaml" "$SRC/data/identities.example.yaml" "$STATE/data/"
# Reference lists already downloaded on the laptop (including your GeoLite2 file) are reused.
if [[ -d "$SRC/data/blocklists" ]]; then
  rsync -a --ignore-existing "$SRC/data/blocklists/" "$STATE/data/blocklists/"
fi
chown -R "$SVC_USER:$SVC_USER" "$STATE"

say "Python environment (a few minutes on a Pi 5)"
[[ -x "$APP/.venv/bin/python" ]] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/python" -m pip install --upgrade pip
"$APP/.venv/bin/python" -m pip install -r "$APP/requirements-pi.txt"
"$APP/.venv/bin/python" -m compileall -q "$APP" >/dev/null || true

ENV_FILE="$CONF/dataexodus.env"
if [[ ! -f "$ENV_FILE" ]]; then
  say "Settings file $ENV_FILE (new Guard token)"
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  NETS="127.0.0.0/8"
  for cidr in $(ip -o -4 addr show scope global | awk '{print $4}'); do
    NETS="$NETS,$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$cidr")"
  done
  sed -e "s|__TOKEN__|$TOKEN|" -e "s|__HOST__|$(hostname)|" -e "s|__CHROMIUM__|$CHROMIUM|" \
      -e "s|__ALLOW__|$NETS|" "$APP/pi/dataexodus.env.example" > "$ENV_FILE"
fi
chown root:"$SVC_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"
# Settings files from older versions: add the DNS tracker list.
if ! grep -q 'dns_trackers.txt' "$ENV_FILE"; then
  sed -i "s|^DNSWATCH_BLOCKLISTS=|DNSWATCH_BLOCKLISTS=$APP/pi/dns_trackers.txt,|" "$ENV_FILE"
fi

say "Firewall: the service account may use the internet, not your LAN"
sed "s|@UID@|$(id -u "$SVC_USER")|" "$APP/pi/nftables-dataexodus.nft" > "$CONF/nftables-dataexodus.nft"
nft -c -f "$CONF/nftables-dataexodus.nft"

say "Reference lists (EasyPrivacy, Tracker Radar ~100 MB, URLhaus)"
if ! (cd "$APP" && sudo -u "$SVC_USER" env HOME="$STATE" "$APP/.venv/bin/python" setup_data.py); then
  warn "download failed; run later: cd $APP && sudo -u $SVC_USER $APP/.venv/bin/python setup_data.py"
fi
[[ -f "$STATE/data/blocklists/GeoLite2-Country.mmdb" ]] || \
  warn "no GeoLite2-Country.mmdb: copy yours to $STATE/data/blocklists/ (countries stay unknown until then)"

say "Services"
install -m 644 "$APP"/pi/systemd/*.service "$APP"/pi/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dataexodus-firewall.service
systemctl restart dataexodus-firewall.service
systemctl enable dataexodus-guard.service dataexodus-box.service dataexodus-dnswatch.service
systemctl restart dataexodus-guard.service dataexodus-box.service
if ! systemctl is-active -q dataexodus-dnswatch && ss -H -lnu 'sport = :53' | grep -q .; then
  warn "another program already uses port 53; DNS watch may not start (see docs)"
fi
systemctl restart dataexodus-dnswatch.service || warn "DNS watch did not start: journalctl -u dataexodus-dnswatch"
# The research crawl is optional: the product runs without it.
if [[ $WITH_STUDY -eq 1 ]]; then
  systemctl enable --now dataexodus-study.timer
fi
# Running portal / sample services pick up the new code too.
for svc in dataexodus-portal dataexodus-samples; do
  if systemctl is-enabled -q "$svc" 2>/dev/null; then systemctl restart "$svc" || true; fi
done

say "Checks"
sleep 4
TOKEN="$(grep '^DATAEXODUS_GUARD_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
if curl -fsS -m 5 -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8010/health >/dev/null; then
  echo "Guard service:        ok"
else
  warn "Guard service is not answering yet: journalctl -u dataexodus-guard -n 50"
fi
curl -fsS -m 5 -o /dev/null http://127.0.0.1:8020/ && echo "Dashboard:            ok" || warn "dashboard: journalctl -u dataexodus-box -n 50"
GATEWAY="$(ip -4 route show default | awk '{print $3; exit}')"
if [[ -n "$GATEWAY" ]]; then
  # Dropped packets time out (curl exit 28); a refused or answered connection
  # means the packets got through.
  code=0; sudo -u "$SVC_USER" curl -s -m 3 -o /dev/null "http://$GATEWAY/" || code=$?
  if [[ $code -eq 28 ]]; then
    echo "Firewall:             service account cannot reach $GATEWAY (as intended)"
  else
    warn "the service account reached $GATEWAY (curl exit $code): the firewall is NOT working"
  fi
fi
sudo -u "$SVC_USER" curl -s -m 8 -o /dev/null https://example.com/ && echo "Internet:             ok" || warn "the service account cannot reach the internet"

IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

DataExodus Box is installed on $(hostname) ($IP).

On the Windows laptop, in the project folder:
  powershell -ExecutionPolicy Bypass -File pi\\connect-pi.ps1 -PiHost $IP -User ${ADMIN:-<your Pi user>} -CopyToken
Then paste the token into Guard Settings > Local service token and Save.
Dashboard (while the tunnel is open): http://127.0.0.1:8020
DNS watch: set a device's DNS server to $IP (only networks in DNSWATCH_ALLOW are answered).
Log out and back in on the Pi once, so your account can read the token.
EOF

if [[ $WITH_HOTSPOT -eq 1 ]]; then
  bash "$APP/pi/hotspot.sh"
else
  echo "The DataExodus Wi-Fi for visitors: sudo bash pi/hotspot.sh (needs Ethernet or USB tethering for internet)."
fi
