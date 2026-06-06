# Coding Practices

These rules guide all implementation work in this repo.

## Delivery priorities
- Do not over-engineer the UI.
- Prioritize scraping reliability and value extraction quality first.
- The first checkpoint is traceable extraction: print logs that show how the system found the relevant values.

## Mandatory workflow
- Use strict test-driven development.
- Never write production code before a failing test exists.
- After every change, run the test suite.
- Keep tests deterministic and fixture-backed whenever possible.

## Environment and runtime
- Do not pollute the laptop root environment.
- Use a project-local virtual environment for Python work.
- Prefer project-local configuration and storage paths.

## Code constraints
- No bare catch-alls.
  - Handle specific expected failures explicitly.
  - Let unexpected failures surface rather than masking them.
- No raw SQL outside the abstraction layer.
  - Preserve the query interface and keep persistence concerns contained.
- No raw input boxes in the UI.
  - Use the component library only.
- No dynamic imports.
- Unique function names enforced.
  - Prefer discovery and reuse over duplication.
- TypeScript should stay in erasable-syntax-only mode.

## Architecture rules
- Modularization with clear boundaries.
  - Scraping, extraction, transforms, persistence, and presentation must stay separated.
- Known patterns and conventions.
  - Add code that future agents can pattern-match safely.
- Simple core, complexity pushed to layers above.
- No hidden magic.
  - If behavior matters, it must be visible in code and tests.

## Extraction and observability
- Every scraper/extractor path must be auditable.
- Emit trace logs that show:
  - listing page loaded
  - candidate item selected
  - relevant value found
  - period and release date inferred
- Do not fabricate missing values.
- Mark partial, estimated, and provisional values clearly.
