# World Metrics — automatically updated dashboard

The static app loads an initial verified economic-data fallback, then reads the latest
validated bundle from the public `no4jargon/worldMetrics` repository:

`https://raw.githubusercontent.com/no4jargon/worldMetrics/main/published-data/snapshot.json`

GitHub Actions checks published sources daily at 20:30 Asia/Kolkata. The browser checks
on load and every 15 minutes while visible. Provider state is shared by all pages,
charts, source statuses, and current-data downloads; a reload is not required.

Incoming bundles are bounded and validated before use. Future, older, invalid, or
unavailable updates leave the last usable figures in place. The dashboard labels
partial/failed/stale checks and preserves per-source reporting periods.

## Build

Install with `npm ci`, then run `npm run build`. Next.js exports the site to `out/`.
The `.openai/hosting.json` manifest identifies the Sites deployment and static output.
The prebuild script retains static fallback data downloads; in-app download links
serialize the currently displayed live payload.

## Refresh the initial fallback

Copy the four public economic snapshots into `data/`, then rebuild and publish a new
version. The live source bundle is updated independently by the cloud workflow.
Never copy backend databases, environment files, collector logs, credentials, or
local refresh metadata into this project.
