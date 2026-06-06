# Live Connector Implementation Plan

This file is the execution plan for replacing fixture-backed connector behavior with true live-source ingestion while preserving strict TDD.

## Operating rules

1. Never write production code without a failing test first.
2. For every bug, first add a failing test reproducing it.
3. Keep tests deterministic by using saved source fixtures from real-world samples.
4. After each code change, run the backend test suite.
5. Update `docs/current-status.md` after each completed step.

## Current source strategy

### 1. MoSPI CPI
- Source: MoSPI CPI press-release PDF discovery flow
- Output metrics:
  - `cpi_index`
  - `cpi_headline`
- Planned stages:
  1. Add failing test for live release discovery URL extraction.
  2. Implement minimal fetch/discovery logic.
  3. Add failing parse test using a real saved sample payload/PDF-derived fixture.
  4. Implement parse.
  5. Add provenance/base-period handling if needed.

### 2. JLL residential sales
- Source: JLL newsroom HTML pages, PDF fallback later
- Output metrics:
  - `home_sales_jll`
- Planned stages:
  1. Add failing test for newsroom page discovery/parsing.
  2. Implement HTML fetch/discovery.
  3. Add failing parse test for `Residential Sales (in units)` India row.
  4. Implement parse.
  5. Add fallback handling for PDF-only quarters later.

### 3. VAHAN vehicle registrations
- Source: VAHAN dashboard manual retrieval workflow
- Output metrics:
  - `two_wheeler_sales`
  - `four_wheeler_sales`
- Constraints:
  - treat values as registration proxy data, not manufacturer wholesale dispatches
- Planned stages:
  1. Keep the `/skill:vahan-dashboard` workflow as the retrieval path.
  2. Store retrieved monthly 2W/4W values as canonical observations.
  3. Preserve dashboard filters and retrieval notes for auditability.

### 4. OEA / DPIIT cement
- Source: OEA Eight Core Industries PDF/XLSX
- Output metrics:
  - `cement_output_index`
  - optional `cement_output` only if a true MT source is later found
- Constraints:
  - public monthly OEA release is an index, not tonnage
- Planned stages:
  1. Add failing test for latest release discovery.
  2. Implement download URL discovery.
  3. Add failing parse test for Annex II cement column.
  4. Implement parse from XLSX if possible, PDF fallback otherwise.
  5. Capture provisional/final metadata.

### 5. CEA monthly power generation
- Source: CEA Executive Summary Report
- Output metrics:
  - `power_output_total`
- Planned stages:
  1. Add failing test for executive summary listing-page discovery.
  2. Implement latest report link extraction.
  3. Add failing parse test for generation table value extraction.
  4. Implement parser, preferring Excel if reliably discoverable.
  5. Add regression tests for filename churn.

### 6. CEA thermal PLF
- Source: CEA Executive Summary Report
- Output metrics:
  - `power_utilization_plf`
- Planned stages:
  1. Reuse CEA report discovery from generation connector.
  2. Add failing parse test for table 10.1 all-India PLF.
  3. Implement parse.
  4. Add layout regression tests.

## Shared engineering tasks

### Metadata and model hardening
- Consider adding support for:
  - `coverage_note`
  - `is_partial`
  - `source_type`
  - `base_period`
- Keep observations honest when public data is incomplete.

### Fixture strategy
- Save small, real-world source fixtures for:
  - latest page HTML
  - one historical page HTML
  - one representative PDF/XLSX-derived fixture per dataset
- Prefer testing parse logic on normalized extracted text/JSON fixtures when binary parsing is too brittle.

### Execution order
1. MoSPI CPI - completed
2. JLL residential - completed
3. VAHAN two-wheelers/four-wheelers - manual skill workflow completed
4. OEA cement index - completed
5. CEA generation - completed
6. CEA PLF - completed

## Definition of done

A connector is only considered complete when all of the following are true:
- live source discovery works from the public publisher page
- parsing is covered by tests using real sample fixtures
- the pipeline emits canonical observations with accurate metadata
- no placeholder values are fabricated
- full backend test suite passes
- `docs/current-status.md` is updated

## Execution result

Status: completed for the planned scope.

Implemented outcomes:
- live-source discovery and parsing flow added for MoSPI CPI using listing HTML plus release-text fixtures
- live-source discovery and parsing flow added for JLL newsroom HTML releases
- VAHAN dashboard retrieval workflow documented for two-wheeler and four-wheeler registration proxy values
- live-source discovery and parsing flow added for OEA cement index releases
- live-source discovery and parsing flow added for CEA executive-summary generation and PLF releases
- full pipeline execution works with source URLs through `run_real(...)`
- all backend tests pass
