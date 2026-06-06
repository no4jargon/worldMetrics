---
name: vahan-dashboard
description: Navigate India's VAHAN dashboard to retrieve vehicle registration/sales proxy data, especially monthly 2-wheeler and 4-wheeler figures. Use when the WorldMetrics dashboard requests VAHAN-backed auto metrics, or when asked which VAHAN dashboard view, button, filter, Y-axis/X-axis, state/RTO, year, or refresh action to use.
---

# VAHAN Dashboard Navigation Skill

Use this skill for the VAHAN dashboard at:

`https://vahan.parivahan.gov.in/vahan4dashboard/`

Important: VAHAN reports **vehicle registrations**, not direct OEM/dealer sales. When the user says "sales", treat VAHAN registration counts as the sales proxy unless they ask otherwise.

## WorldMetrics dashboard metric links

Use this skill as the retrieval workflow for these dashboard metrics:

- `two_wheeler_sales` / "Monthly two-wheeler sales": VAHAN fallback/cross-check. Retrieve `Vehicle Category` × `Month Wise`, then sum `TWO WHEELER(NT)`, `TWO WHEELER(T)`, and optional invalid-carriage row.
- `four_wheeler_sales` / "Monthly four-wheeler sales": primary VAHAN workflow. Retrieve `Vehicle Category` × `Month Wise`, then sum `LIGHT MOTOR VEHICLE`, `MEDIUM MOTOR VEHICLE`, `HEAVY MOTOR VEHICLE`, and optional 4W invalid-carriage row.

When updating those metrics manually, preserve the month label as `YYYY-MM`, unit as `units`, and segment as `domestic` or `all_india`.

## Fast path: monthly 2W / 4W figures

For monthly 2-wheeler or 4-wheeler data, use **Tabular Summary**. It is the only view that gives structured month columns and vehicle category/class rows.

1. Open the VAHAN dashboard.
2. In the top-right view dropdown, choose **Tabular Summary**.
3. On the report page set:
   - **Type**: `Actual Value` unless the user asks for thousand/lakh/crore scaling.
   - **State**: `All Vahan4 Running States` for India-wide, or the requested state.
   - **RTO**: `All Vahan4 Running Office` unless the user asks for one office.
   - **Y-Axis**: `Vehicle Category` for 2W/4W group totals by month.
   - **X-Axis**: `Month Wise`.
   - **Year Type**: `Calendar Year` or `Financial Year` as requested.
   - **Year**: requested year.
4. Click the top **Refresh** button.
5. Read the table titled like `Vehicle Category Month Wise Data For ...`.

### 2-wheeler monthly total

Sum these rows month-by-month:

- `TWO WHEELER(NT)`
- `TWO WHEELER(T)`
- `TWO WHEELER (INVALID CARRIAGE)` if present

If the user only wants common/private 2W, use `TWO WHEELER(NT)`.

### 4-wheeler monthly total

There is no single `FOUR WHEELER` row in Month Wise mode. Sum these `Vehicle Category` rows month-by-month:

- `LIGHT MOTOR VEHICLE`
- `MEDIUM MOTOR VEHICLE`
- `HEAVY MOTOR VEHICLE`
- `FOUR WHEELER (INVALID CARRIAGE)` if present

If the user likely means passenger cars, do **not** use the above group total; instead set **Y-Axis** = `Vehicle Class`, **X-Axis** = `Month Wise`, click **Refresh**, and read the `MOTOR CAR` row.

## Which view/button to use

- **Main Page View**: high-level totals/cards only: Vehicle Registration, Transactions, Revenue, Permit, Running State/RTO, top-five charts. Not suitable for monthly 2W/4W extraction.
- **Comparison View**: monthwise charts for total registration/revenue/transactions. Useful for high-level trend visuals, not vehicle-class/category tables.
- **Summary View**: date-range summary cards and charts. Useful for quick aggregate totals after selecting From/Upto dates, but not best for exact 2W/4W monthly table extraction.
- **Tabular Summary**: best view for analytical data by Vehicle Category, Vehicle Class, Fuel, Maker, State, year/month. Use for monthly 2W/4W questions.
- **Pending Appl Summary**: pending application dashboard; not sales/registration sales.
- **Fitness Appl Summary**: fitness application dashboard; not sales/registration sales.

## Report-page controls

On **Tabular Summary**:

- **Type** changes number scale: `Actual Value`, `In Thousand`, `In Lakh`, `In Crore`.
- **State** and **RTO** scope the geography.
- **Y-Axis** chooses table rows: `Vehicle Category`, `Vehicle Class`, `Norms`, `Fuel`, `Maker`, `State`.
- **X-Axis** chooses table columns: `Vehicle Category`, `Norms`, `Fuel`, `Vehicle Category Group`, `Financial Year`, `Calendar Year`, `Month Wise`.
- **Year Type / Year** choose calendar vs financial year and the year.
- Top **Refresh** applies these settings and reloads the result table.
- The left-side `click here` drawer exposes optional filters for Vehicle Category, Norms, Fuel, and Vehicle Class. After changing drawer checkboxes, click the drawer/table **Refresh** to update the table.

For more details, see `references/vahan-dashboard-map.md`.
