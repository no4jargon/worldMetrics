# Personal Bloomberg Plan

## Product intent
Build a private macro tracker hosted on a spare laptop, focused on a small set of sources and metrics that matter personally. Keep the UI simple. Make scraping and value extraction trustworthy first.

## Source plan

### JLL
- Listing URL: `https://www.jll.com/en-in/newsroom`
- Detection rule: check for new relevant residential articles
- Artifact mode: article HTML/text, PDF fallback later
- Extraction mode: LLM text extraction with deterministic validation
- Primary metric target:
  - `home_sales_jll`

### VAHAN
- Listing URL: `https://vahan.parivahan.gov.in/vahan4dashboard/`
- Detection rule: manual dashboard retrieval workflow
- Artifact mode: dashboard HTML/table export
- Extraction mode: agent skill `vahan-dashboard`
- Primary metric targets:
  - `two_wheeler_sales`
  - `four_wheeler_sales`
- Constraint:
  - treat these values as registration proxy data, not manufacturer wholesale dispatches

### Power
- Listing URL: `https://npp.gov.in/monthlyGenerationReportsAct`
- Detection rule: submit target month and select the All India XLS report
- Artifact mode: XLS download
- Extraction mode: Playwright form submission plus deterministic XLS parsing
- Primary metric targets:
  - `power_output_total`
  - `power_utilization_plf`

## First checkpoint
The first checkpoint is complete when the system can:
- load each listing page or dashboard
- select the relevant article/report/table
- extract the relevant values
- print trace logs showing where the values were found
- build snapshot output from those extracted values

## Architecture
- Simple UI, backend-first focus
- Modular backend boundaries:
  - source registry
  - connector/scraper layer
  - extraction layer
  - transforms/validation layer
  - snapshot serving layer
- No hidden magic
- No raw SQL outside the abstraction layer

## Operational requirements
- Use a project-local virtual environment
- Avoid polluting the laptop root environment
- Prefer deterministic fixtures for tests
- Preserve raw artifacts for debugging and future auditability

## Delivery sequence
1. Save coding practices and working plan in-repo.
2. Add build-progress tracking.
3. Add source registry for personal tracker sources.
4. Implement traceable scraping/extraction for JLL.
5. Implement the VAHAN dashboard retrieval skill.
6. Use NPP Playwright/XLS parsing for power metrics.
7. Add a simple personal-tracker runner that prints extraction traces and builds snapshots.
8. Keep the full test suite green after every change.

## Next production hardening after checkpoint one
- Add raw artifact storage for HTML/XLS/dashboard captures
- Add prompt/version tracking for LLM extraction where applicable
- Add persistence abstraction for historical runs
- Add scheduled execution on the laptop
- Add alerting for extraction failures or missing releases
