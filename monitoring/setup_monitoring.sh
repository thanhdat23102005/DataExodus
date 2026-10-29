#!/usr/bin/env bash
# Download and start the local monitoring stack: InfluxDB (stores every
# classified request pipeline/agent.py sees) + Grafana (reads it, dashboard
# provisioned from conf/dashboards/dataexodus.json).
#
# Runs as plain user-space binaries, no root/Docker required - the same
# provisioning files work unchanged if this later moves to a Raspberry Pi
# (or any other host): just re-run this script there.
#
# Usage:
#   ./monitoring/setup_monitoring.sh          # first-time setup + start
#   ./monitoring/setup_monitoring.sh stop      # stop both
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

INFLUXDB_VERSION="2.9.1"
GRAFANA_VERSION="13.1.3"
GRAFANA_BUILD="31135815010"  # part of the release filename, see grafana.com/grafana/download

if [[ "${1:-}" == "stop" ]]; then
  pkill -f "influxd --bolt-path" 2>/dev/null && echo "stopped influxd" || echo "influxd not running"
  pkill -f "bin/grafana server" 2>/dev/null && echo "stopped grafana" || echo "grafana not running"
  exit 0
fi

# --- InfluxDB ---------------------------------------------------------
if [[ ! -x influxdb/influxd ]]; then
  echo "Downloading InfluxDB ${INFLUXDB_VERSION} ..."
  mkdir -p influxdb/data
  curl -sL -o /tmp/influxdb2.tar.gz \
    "https://dl.influxdata.com/influxdb/releases/influxdb2-${INFLUXDB_VERSION}_linux_amd64.tar.gz"
  tar xzf /tmp/influxdb2.tar.gz --strip-components=1 -C influxdb
  rm /tmp/influxdb2.tar.gz
fi

if ! pgrep -f "influxd --bolt-path" > /dev/null; then
  echo "Starting influxd ..."
  (cd influxdb && nohup ./influxd \
      --bolt-path="$(pwd)/data/influxd.bolt" \
      --engine-path="$(pwd)/data/engine" \
      --http-bind-address=127.0.0.1:8086 \
      > /tmp/influxd.log 2>&1 &)
  for _ in $(seq 1 15); do
    curl -s -o /dev/null http://127.0.0.1:8086/health && break
    sleep 1
  done
fi

if [[ ! -f influxdb/credentials.env ]]; then
  echo "Onboarding InfluxDB (org=dataexodus, bucket=live_requests) ..."
  PASS=$(openssl rand -base64 18)
  RESP=$(curl -s -XPOST http://127.0.0.1:8086/api/v2/setup -H 'Content-Type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$PASS\",\"org\":\"dataexodus\",\"bucket\":\"live_requests\",\"retentionPeriodSeconds\":0}")
  TOKEN=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['auth']['token'])" "$RESP")
  {
    echo "INFLUX_URL=http://127.0.0.1:8086"
    echo "INFLUX_ORG=dataexodus"
    echo "INFLUX_BUCKET=live_requests"
    echo "INFLUX_TOKEN=$TOKEN"
    echo "INFLUX_ADMIN_USER=admin"
    echo "INFLUX_ADMIN_PASS=$PASS"
  } > influxdb/credentials.env
  chmod 600 influxdb/credentials.env
fi

# --- Grafana ------------------------------------------------------------
if [[ ! -x grafana/bin/grafana ]]; then
  echo "Downloading Grafana ${GRAFANA_VERSION} ..."
  mkdir -p grafana
  curl -sL -o /tmp/grafana.tar.gz \
    "https://dl.grafana.com/grafana/release/${GRAFANA_VERSION}/grafana_${GRAFANA_VERSION}_${GRAFANA_BUILD}_linux_amd64.tar.gz"
  tar xzf /tmp/grafana.tar.gz --strip-components=1 -C grafana
  rm /tmp/grafana.tar.gz
fi
mkdir -p grafana/data-storage

if [[ ! -f grafana/credentials.env ]]; then
  echo "GF_ADMIN_USER=admin" > grafana/credentials.env
  echo "GF_ADMIN_PASS=$(openssl rand -base64 18)" >> grafana/credentials.env
  chmod 600 grafana/credentials.env
fi

if ! pgrep -f "bin/grafana server" > /dev/null; then
  echo "Starting grafana-server ..."
  INFLUX_TOKEN=$(grep INFLUX_TOKEN influxdb/credentials.env | cut -d= -f2-)
  GRAFANA_PASS=$(grep GF_ADMIN_PASS grafana/credentials.env | cut -d= -f2-)
  (cd grafana && \
    GF_PATHS_DATA="$(pwd)/data-storage" \
    GF_PATHS_LOGS="$(pwd)/data-storage/logs" \
    GF_PATHS_PLUGINS="$(pwd)/data-storage/plugins" \
    GF_PATHS_PROVISIONING="$(pwd)/conf/provisioning" \
    GF_SERVER_HTTP_ADDR="127.0.0.1" \
    GF_SERVER_HTTP_PORT="3000" \
    GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASS" \
    INFLUX_TOKEN="$INFLUX_TOKEN" \
    nohup ./bin/grafana server --homepath="$(pwd)" > /tmp/grafana.log 2>&1 &)
fi

echo
echo "InfluxDB : http://127.0.0.1:8086  (admin / see monitoring/influxdb/credentials.env)"
echo "Grafana  : http://127.0.0.1:3000  (admin / see monitoring/grafana/credentials.env)"
echo "Dashboard: http://127.0.0.1:3000/d/dataexodus-live"
echo "Stop both with: ./monitoring/setup_monitoring.sh stop"
