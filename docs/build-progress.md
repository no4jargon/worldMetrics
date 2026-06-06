# Build Progress

Last updated: 2026-06-06

## Goal
Reach checkpoint one for the personal Bloomberg build:
- reliable scraping focus
- traceable value extraction logs
- minimal UI changes
- strict TDD throughout

## Completed
- Saved repo guidance in `docs/coding-practices.md`.
- Saved the personal Bloomberg implementation plan in `docs/personal-bloomberg-plan.md`.
- Added a simple personal-tracker CLI entrypoint in `backend/app/main.py`.
- Added an operator-friendly launcher script at `scripts/run-personal-tracker.sh`.
- Added personal source registry in `backend/app/live/source_registry.py` for:
  - JLL newsroom
  - VAHAN dashboard retrieval workflow
- Added trace logging helper in `backend/app/connectors/trace.py`.
- Added trace-capable JLL connector flow.
- Added VAHAN dashboard retrieval skill metadata.
- Added NPP Playwright/XLS power connector for:
  - power generation
  - thermal PLF
- Added personal tracker connector factory in `backend/app/live/factory.py`.
- Added `run_personal_tracker(...)` in `backend/app/main.py`.
- Added tests for:
  - personal source registry
  - end-to-end personal tracker run with trace logs and snapshot output

## Current checkpoint status
Checkpoint one: achieved in the current fixture-driven environment.

Evidence:
- trace logs are printed during source discovery and value extraction
- snapshots build successfully from configured personal tracker connectors
- backend test suite passes for the exercised modules

## Current test status
- Backend tests run with `unittest` in the local venv; `pytest` is not installed.

## Remaining work after checkpoint one
- Wire actual LLM extraction calls behind a narrow extraction interface where applicable
- Persist raw artifacts and extraction outputs
- Add scheduling and local deployment automation for the spare laptop
