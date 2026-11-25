# Local refresh and auto-repopulation

This project now has a dev-local SQLite cache plus dashboard JSON snapshots.

## Daily FII equity flows

FII/FPI cash-equity flows have a separate lightweight refresh and do not run the monthly macro collectors:

```bash
npm run refresh:fii
```

Or run from `backend/`:

```bash
./.venv/bin/python -m app.main refresh-fii
```

The job atomically updates `web/data/fii-flows.json`, upserts revised trading dates, and retains previous records on an upstream failure. It uses a process lock to avoid concurrent writes. The first refresh requests 12 calendar months of history; subsequent refreshes revisit recent months and expand the window if the app was idle.

The Overview loads this snapshot and polls `/api/fii-flows`. Source checks are throttled to 15 minutes after 15:30 IST on weekdays, six hours otherwise, and five minutes after a failure; a new India calendar day triggers a check. The browser polls every minute, or every five seconds while a refresh is in progress. Checks require the local app to be running and a page or API client to request the data. Set `WM_FII_AUTO_REFRESH=0` to disable these checks.

The chart defaults to daily net flows in ₹ crore. Monthly values sum available daily records, with MTD and partial-history labels. The latest session is directly from NSE's combined provisional cash-market report; historical daily records are attributed to Groww, with overlap and calendar checks. The snapshot exposes the actual latest publication date and any coverage gaps. No missing day is treated as a zero flow.

## Default behavior

When the website reads data, `web/app/lib/data.ts` checks for:

- `web/data/overview.json`
- `web/data/series.json`
- `web/data/release-monitor.json`

If any are missing or stale, the website starts this command in the background:

```bash
cd backend
source .venv/bin/activate
python -m app.main refresh-dev --months 60
```

The page opens immediately. While scraping is running, the Overview page shows progress from `web/data/refresh-status.json`: current month, months checked, records found, skipped months, and percentage complete. Refresh the browser to update progress.

Disable website-triggered refresh with:

```bash
WM_AUTO_REFRESH_ON_OPEN=0 npm run dev
```

Use a smaller/larger auto-refresh window with:

```bash
WM_AUTO_REFRESH_MONTHS=16 npm run dev
```

## Complete reset command

To wipe local dev data and force auto-repopulation on the next website open:

```bash
./scripts/reset-local-dev-data.sh
```

This removes:

- `backend/data/worldmetrics.sqlite3`
- `web/data/overview.json`
- `web/data/series.json`
- `web/data/release-monitor.json`
- `web/data/refresh-metadata.json`
- `web/data/refresh-status.json`
- `web/data/fii-flows.json`

Then start/open the website:

```bash
cd web
npm run dev
```

The first page load will repopulate automatically.

## Manual refresh command

To wipe and repopulate immediately:

```bash
cd backend
source .venv/bin/activate
python -m app.main refresh-dev --reset-db --months 60
```

For a quicker dev run:

```bash
python -m app.main refresh-dev --reset-db --months 16
```

For a deterministic historical window during development:

```bash
python -m app.main refresh-dev --reset-db --months 16 --end-month 2025-05
```

## Power source

Power uses NPP Monthly Generation Reports Actual:

```text
https://npp.gov.in/monthlyGenerationReportsAct
```

The NPP connector attempts the requested month window and skips months where NPP has no published XLS report. For each available month it stores:

- `power_output_total`
- `power_utilization_plf`
