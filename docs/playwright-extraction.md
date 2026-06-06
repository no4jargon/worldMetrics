# Playwright Metric Extraction Backend

The backend now has a Playwright-first extraction path for messy government websites.

## Power: NPP monthly generation

Power now uses `https://npp.gov.in/monthlyGenerationReportsAct` via `NPPMonthlyGenerationConnector`.

Flow:

1. Open the NPP monthly generation actual page in Playwright Chromium.
2. For each requested month, remove `readonly` from the `rmonth` field and submit `MM/YYYY`.
3. Find the `1. All India` row.
4. Download the linked `.xls` report.
5. Parse the workbook with `xlrd`.
6. Emit canonical units:
   - `power_output_total`: TOTAL row, monthly ACTUAL generation column, in `GWh`.
   - `power_utilization_plf`: THERMAL row, monthly ACTUAL PLF column, in `percent`.

Month controls:

```bash
# Explicit months
NPP_POWER_MONTHS=2025-04,2025-05 python -m app.main

# Range, inclusive
NPP_POWER_START_MONTH=2024-04 NPP_POWER_END_MONTH=2025-05 python -m app.main
```

If no env vars are set, the connector attempts the last 60 months and skips months that NPP does not publish.

## Install

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```bash
cd backend
source .venv/bin/activate
python -m app.main extract \
  --targets-file config/targets.example.json \
  --output-dir ../artifacts/extractions
```

Use `--headed` to watch the browser:

```bash
python -m app.main extract --targets-file config/targets.json --headed
```

## Target config shape

Each target declares:

- `code`: target/site identifier
- `url`: landing page or release page
- `wait_until`: Playwright navigation wait mode
- `wait_for_selector`: optional selector that must appear before extraction
- `follow_link_text_regex`: optional regex to select a release link by anchor text
- `follow_link_href_regex`: optional regex to select a release link by href
- `screenshot`: whether to save a screenshot artifact
- `metrics`: extraction rules

Each metric rule declares:

- `metric_code`
- `unit`: source unit. The extractor converts to the canonical unit for known metrics, e.g. `BU` / billion units becomes `GWh` for `power_output_total`, and utilization metrics remain `percent`.
- `selector`: optional CSS selector to scope extraction
- `value_regex`: regex for the value; prefer Python named group `(?P<value>...)`
- `period_regex`: optional period extraction; prefer `(?P<period>...)`
- `release_date_regex`: optional date extraction; prefer `(?P<release_date>...)`

## Artifacts

Every run saves artifacts under the output dir:

```text
<output>/<target_code>/<timestamp>/
  page.html
  page.txt
  page.png         # if screenshot=true
  extraction.json
```

A combined `runs.json` is also written at the output root.

## Current limitation

The generic extraction layer renders dynamic pages and extracts from DOM text. The NPP power connector additionally parses linked XLS workbooks. PDF table OCR is not implemented yet.

## Unit guardrails

Canonical units live in `backend/app/core/metric_registry.py`. Add every new metric there before wiring a target. This prevents silent unit mistakes: for example, `power_consumed_total` and `power_output_total` are stored as `GWh`; `BU` source values are multiplied by 1,000, while utilization/rate metrics must be `percent`.
