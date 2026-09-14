# DataExodus

> **A measurement study and monitoring tool that reveals where Australian websites send user data, what personal information those flows contain, and whether that behaviour matches their stated privacy policies.**

## Quick Start

### 1. Install

```bash
# On RHEL/CentOS/Rocky
chmod +x setup-rhel.sh
./setup-rhel.sh

# On macOS/Ubuntu (manual)
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
```

### 2. Download Reference Data

```bash
python setup_data.py --geoip-key YOUR_MAXMIND_KEY
```

Get a free GeoLite2 key at [maxmind.com](https://www.maxmind.com/en/geolite2/signup).

### 3. Configure Your Identifiers

```bash
cp data/identities.local.yaml data/identities.local.yaml
cat > data/identities.local.yaml <<EOF
email:
  - your.real@email.com
phone:
  - "04XXXXXXXX"
EOF
```

**Never commit this file.**

### 4. Run Tests

```bash
python -m pytest tests/ -v
```

### 5. Crawl (Batch Mode)

```bash
# Test one sector
python -m crawler.crawl --sector government

# Full crawl (50 sites)
python -m crawler.crawl

# Process results
python -m pipeline.process

# Generate report & charts
python -m analysis.report
```

### 6. Live Mode (Real-time Monitoring)

Terminal 1 — start agent:
```bash
uvicorn pipeline.agent:app --host 127.0.0.1 --port 8000
```

Terminal 2 — open dashboard:
```bash
open dashboard.html  # or just double-click it
```

Chrome — install extension:
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select `extension/` folder
4. Browse normally. Watch the dashboard update live.

## Project Structure

```
dataexodus/
├── data/
│   ├── sites.yaml              # 50 AU sites (frozen week 1)
│   ├── identities.local.yaml   # YOUR identifiers (gitignored)
│   ├── raw/                    # Crawl output
│   └── blocklists/             # EasyPrivacy, Tracker Radar, GeoIP
├── crawler/
│   └── crawl.py                # Playwright crawler
├── pipeline/
│   ├── classify.py             # Tracker/entity/GeoIP classification
│   ├── pii.py                  # Hash-based PII detection (Aho-Corasick)
│   ├── process.py              # Batch pipeline → DuckDB
│   ├── agent.py                # FastAPI real-time agent
│   └── risk.py                 # Risk scorer 0–100
├── analysis/
│   └── report.py               # Stats, hypotheses, charts
├── extension/
│   ├── manifest.json
│   ├── background.js           # Request capture & batch push
│   ├── popup.html
│   └── popup.js
├── tests/
│   └── test_pipeline.py        # 25 unit tests
├── dashboard.html              # Live WebSocket dashboard
├── setup_data.py               # Download reference datasets
├── setup-rhel.sh               # RHEL system setup
└── requirements.txt
```

## Three Layers

| Layer | Question | Done When |
|-------|----------|-----------|
| 1 — Where | Destination mapping | One session renders as Sankey |
| 2 — What | Data classification | Point at request, name the PII |
| 3 — So What | Legal/risk framing | Compliance finding per site |

## Ethics & Safety

- **Only your own traffic** is recorded.
- The database contains your full browsing history — **encrypt your disk**.
- **Never push `identities.local.yaml` to git.**
- Add a **pause toggle** in the extension for sensitive sites (banking, health).
- If running on a Pi in your LAN, bind to `0.0.0.0` **with authentication**.

## License

MIT — for academic/research use.
