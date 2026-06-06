# Current Status

Last updated: 2026-06-06

## Execution policy
- Use `docs/implementation-plan.md` as the source of truth for sequencing work.
- Update this file after each completed step.
- Maintain strict Red-Green-Refactor TDD throughout.

## Completed so far
- Default snapshot generation no longer uses sample connectors; it uses the real connector set and surfaces connector/configuration gaps in dashboard JSON.
- Overview and series payloads include explicit missing states when a metric has no live connector output.
- Release Monitor includes connector status, emitted observation count, and error/note fields.
- Added Playwright-first metric extraction backend scaffold with target configs, artifact capture, and extraction CLI.
- Power metrics use NPP Monthly Generation Reports Actual (`https://npp.gov.in/monthlyGenerationReportsAct`) through Playwright form submission plus All India XLS parsing.
- Added dev-local SQLite refresh framework, reset script, and non-blocking website auto-repopulation when snapshots are missing/outside the requested month window.
- Project scaffold created across backend, SQL, and Next.js frontend.
- Canonical models, transforms, validation, pipeline, and snapshot generation implemented.
- Fixture-backed real connector modules implemented for:
  - CEA power output
  - CEA thermal PLF
  - OEA/DPIIT cement
  - JLL residential sales
  - MoSPI CPI
- Shared JSON fetch support added.
- Real connector factory added.
- `run_real(...)` entrypoint added.
- Snapshot overview includes `cement_utilization_est` and `cement_output_index`.
- OEA connector supports honest public-source representation via `cement_output_index`.
- Shared live text discovery/parsing helpers added.
- Live source-URL discovery/parsing implemented for:
  - MoSPI CPI listing HTML -> release text -> `cpi_index`, `cpi_headline`
  - JLL newsroom listing HTML -> article HTML -> `home_sales_jll`
  - OEA landing HTML -> release text -> `cement_output_index`
  - CEA executive-summary listing HTML -> release text -> `power_output_total`
  - CEA executive-summary listing HTML -> release text -> `power_utilization_plf`
- VAHAN dashboard retrieval workflow is the intended source for `two_wheeler_sales` and `four_wheeler_sales` registration proxy values.
- Dashboard refresh now includes VAHAN `/skill:vahan-dashboard` automation that fetches Tabular Summary data and emits `two_wheeler_sales` / `four_wheeler_sales` observations.

## Current truth about live coverage
- Connectors now support three input modes:
  - fixture-path JSON
  - source-url JSON
  - live source discovery from HTML pages that link to text fixtures representing extracted release documents
- NPP power uses Playwright plus XLS parsing for real monthly artifacts.
- VAHAN vehicle registration data is retrieved through `/skill:vahan-dashboard` Playwright automation rather than a static HTML/JSON connector.
- Remaining production hardening for the real internet is mainly document extraction quality and audit storage, not connector architecture.

## Metrics status

### Power
- `power_output_total`
  - NPP Playwright monthly form submission: done
  - All India XLS parsing: done
  - emits every requested/available month
- `power_utilization_plf`
  - NPP Playwright monthly form submission: done
  - All India XLS parsing: done
  - emits every requested/available month

### Construction
- `cement_output`
  - fixture-backed tonnage path exists
  - public official monthly MT source not verified
- `cement_output_index`
  - model/pipeline support: done
  - live discovery/parsing flow: done
- `cement_utilization_est`
  - estimated-only path exists
  - clearly labeled as estimated
- `home_sales_jll`
  - fixture-backed connector: done
  - live newsroom HTML parsing: done

### Demand
- `two_wheeler_sales`
  - VAHAN dashboard retrieval workflow: fetched via `/skill:vahan-dashboard` automation
- `four_wheeler_sales`
  - VAHAN dashboard retrieval workflow: fetched via `/skill:vahan-dashboard` automation
- `auto_sales_total`
  - treated as VAHAN registration proxy; 2W/4W component series are fetched via `/skill:vahan-dashboard`

### Inflation
- `cpi_index`
  - fixture-backed connector: done
  - live discovery/parsing flow: done
- `cpi_headline`
  - fixture-backed connector: done
  - live discovery/parsing flow: done

## Plan status
- `docs/implementation-plan.md` execution status: complete for planned scope.

## Test status
- Frontend production build passing as of 2026-06-03 with root `npm run build`.
- Backend local refresh passing as of 2026-06-03 for a 2-month NPP historical window.
- Backend pytest could not be verified in the current venv because `pytest` is not installed.

## Remaining production hardening
- Install Playwright browser binaries in the backend venv and configure user-provided target websites.
- Replace normalized text fixtures with robust PDF/XLSX/HTML extractors against live public documents where needed.
- Add provenance metadata fields such as `source_type`, `base_period`, and `is_partial` if desired.
- Add persistent raw-document archival for auditability.
- Add live-network regression fixtures when internet-enabled execution is available.

## Risks / caveats retained intentionally
- Public official sources often publish PDF/XLSX/HTML instead of stable JSON APIs.
- CEA filenames are inconsistent and should be discovered from listing pages, not synthesized.
- OEA monthly public data is index-based, not cement tonnage in MT.
- JLL page formats may shift between newsroom HTML and PDF-heavy insights pages.
