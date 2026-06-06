# World Metrics

India macro-industrial dashboard for tracking monthly changes across power, construction, demand, and inflation.

![World Metrics dashboard overview](docs/images/dashboard-overview.png)

## What it tracks

Current v1 metric scope:

- Power output
- Power utilization / thermal PLF
- Cement output and cement utilization estimate
- JLL residential home sales
- VAHAN two-wheeler and four-wheeler registration proxy data
- CPI inflation

## Current local status

This project is local-only for now. The dashboard is backed by generated JSON snapshots in `web/data/`, which are intentionally treated as local build artifacts and are not committed.

The current implementation includes live/local connector support for:

- **NPP Monthly Generation Reports** via Playwright form submission and XLS parsing for power output and thermal PLF
- **VAHAN dashboard retrieval workflow** via the `vahan-dashboard` skill for two-wheeler and four-wheeler registration proxy data
- Connector scaffolds and fixture/live-source parsing paths for OEA/DPIIT cement, JLL residential sales, and MoSPI CPI

The frontend surfaces connector gaps directly in the dashboard and Release Monitor instead of silently substituting fake data.

## Architecture

```text
backend/   Python ingestion jobs, connectors, parsers, validators, transforms
sql/       PostgreSQL schema and seed metadata for production-style persistence
web/       Next.js dashboard, API/data helpers, generated local snapshots
scripts/   Local development helper scripts
docs/      Implementation notes, refresh docs, plans, and screenshots
```

## Quick start

### 1. Install frontend dependencies

```bash
cd web
npm install
```

### 2. Create backend virtual environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Refresh local data

From the project root:

```bash
npm run refresh
```

For a smaller development window:

```bash
npm run refresh:16
```

To wipe local generated data and force a clean repopulation:

```bash
npm run reset:data
```

### 4. Run the dashboard

From the project root:

```bash
npm run dev
```

Open `http://localhost:3000`.

## Useful commands

```bash
npm run dev        # run the Next.js dashboard
npm run build      # production frontend build with auto-refresh disabled
npm run refresh    # refresh 60 months of local data
npm run refresh:16 # faster 16-month refresh
npm run reset:data # remove local SQLite DB and generated dashboard JSON
```

Backend commands can also be run directly:

```bash
cd backend
source .venv/bin/activate
python -m app.main refresh-dev --reset-db --months 60
python -m app.main personal-tracker
```

## Data and generated files

Generated runtime artifacts are excluded from Git, including:

- `backend/data/*.sqlite3`
- `web/data/*.json`
- `web/.next/`
- `web/node_modules/`
- `backend/.venv/`

This keeps the repository focused on source code, documentation, schema, and reproducible project setup.

## Production hardening still to do

- Make all backend tests deterministic without triggering slow live connector calls
- Add robust PDF/XLSX/HTML extraction for sources that do not publish stable APIs
- Persist raw source artifacts and extraction logs for auditability
- Wire scheduled refreshes for always-on local deployment
- Move from dev SQLite snapshots toward the PostgreSQL schema if/when needed
