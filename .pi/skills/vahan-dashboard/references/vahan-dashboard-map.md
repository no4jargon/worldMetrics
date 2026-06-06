# VAHAN Dashboard Map

Source inspected: `https://vahan.parivahan.gov.in/vahan4dashboard/`.

## WorldMetrics metric links

- `two_wheeler_sales`: linked retrieval skill `/skill:vahan-dashboard`; use `Vehicle Category` rows with `Month Wise` columns and sum 2W rows.
- `four_wheeler_sales`: linked retrieval skill `/skill:vahan-dashboard`; use `Vehicle Category` rows with `Month Wise` columns and sum LMV/MMV/HMV plus optional invalid-carriage row.

## Mental model

VAHAN's dashboard is a JSF/PrimeFaces application. Many dropdown changes do not fully refresh results until a **Refresh** button is clicked. Always click the relevant refresh after changing filters.

VAHAN data shown here is registration data. Treat it as a sales proxy only when that is acceptable to the user.

## Top navigation dropdown

The top-right dropdown has these choices:

| Choice | What it opens | Use for |
|---|---|---|
| `Main Page View` | Landing dashboard cards and top-five charts | High-level totals only |
| `Comparison View` | Monthwise total registration/revenue/transaction charts | Overall monthly trends, not 2W/4W split |
| `Summary View` | Date range summary cards/charts | Quick totals for chosen From/Upto dates |
| `Tabular Summary` | Analytical report page | Best for monthly 2W/4W, maker, fuel, state tables |
| `Pending Appl Summary` | Pending application dashboard | Application backlog, not sales |
| `Fitness Appl Summary` | Fitness application dashboard | Fitness applications, not sales |

## Common top filters on main/comparison/summary pages

- **Type**: numeric scale (`Actual Value`, `In Thousand`, `In Lakh`, `In Crore`).
- **State/UTs**: all India or one state.
- **Office/RTO**: all offices in the selected geography or one RTO.
- **Refresh icon**: reloads current view after filter changes.

## Main Page View

Contains high-level panels/cards:

- Vehicle Registration
- No of Transaction
- Revenue Collection
- Permit
- Tax Defaulter / Running State-RTO information
- Registration/Transaction/Revenue/Permit top-five charts
- Status of sites on centralized VAHAN4

The year labels such as `Till Today` are clickable and open more detailed year-wise tables/dialogs, but this view does not provide clean monthly 2W/4W tables.

## Comparison View

Shows accordions/charts:

- `Monthwise Vehicle Registration`
- `Monthwise Revenue Collection`
- `Monthwise Transaction`

Use this for overall total monthly trends only. It does not expose the vehicle-category/class split needed for 2W/4W sales extraction.

## Summary View

Adds date pickers:

- **From** date
- **Upto** date

Shows cards/charts including:

- Vehicle Registration
- No of Transaction
- Revenue Collection
- Permit
- Tax Defaulter
- Monthwise Vehicle Registration
- Monthwise Transaction
- Splitwise Vehicle Type
- Monthwise Revenue Collection
- Fuel-type/other split charts

Use this for quick dashboard visuals over a custom date range. For exact monthly 2W/4W numbers, prefer **Tabular Summary**.

## Tabular Summary report page

This is the main data extraction page.

### Top controls

| Control | Options / meaning |
|---|---|
| **Type** | `Actual Value`, `In Thousand`, `In Lakh`, `In Crore` |
| **State** | all states or one state |
| **RTO** | all offices or one RTO |
| **Y-Axis** | table row dimension: `Vehicle Category`, `Vehicle Class`, `Norms`, `Fuel`, `Maker`, `State` |
| **X-Axis** | table column dimension: `Vehicle Category`, `Norms`, `Fuel`, `Vehicle Category Group`, `Financial Year`, `Calendar Year`, `Month Wise` |
| **Year Type** | `Calendar Year` or `Financial Year` |
| **Year** | `Till Today` or a specific year, currently listed from 2003 onward |
| **Refresh** | applies top controls and reloads side filters/table |

### Left filter drawer

The vertical `click here` image/drawer on the left opens optional checkbox filters:

- Vehicle Category
- Norms
- Fuel
- Vehicle Class

After checkbox changes, click the drawer/table **Refresh** button. Top Refresh is for the main axis/year/geography controls; drawer Refresh applies checkbox filtering to the table.

### Useful Y/X combinations

| User asks | Y-Axis | X-Axis | Notes |
|---|---|---|---|
| Monthly 2W registrations/sales proxy | `Vehicle Category` | `Month Wise` | Sum `TWO WHEELER(NT)`, `TWO WHEELER(T)`, and invalid carriage if present |
| Monthly 4W group registrations/sales proxy | `Vehicle Category` | `Month Wise` | Sum `LIGHT MOTOR VEHICLE`, `MEDIUM MOTOR VEHICLE`, `HEAVY MOTOR VEHICLE`, and 4W invalid carriage if present |
| Monthly passenger car registrations | `Vehicle Class` | `Month Wise` | Read `MOTOR CAR` row |
| Monthly motorcycle/scooter registrations | `Vehicle Class` | `Month Wise` | Read `M-CYCLE/SCOOTER`; include moped/sidecar rows only if requested |
| Fuel split | `Fuel` | `Month Wise` or `Vehicle Category Group` | Use Vehicle Class/Category filters if narrowing to 2W/4W |
| Maker split by month | `Maker` | `Month Wise` | Use filters first or pagination will be large |
| State-wise annual total | `State` | `Calendar Year` or `Financial Year` | Good for regional comparisons |
| Vehicle group columns | `Vehicle Class` or `Vehicle Category` | `Vehicle Category Group` | Produces columns like TWO WHEELER, THREE WHEELER, FOUR WHEELER |

## 2W and 4W interpretation rules

### 2W

For group totals from `Vehicle Category Month Wise`, sum:

- `TWO WHEELER(NT)` = non-transport/private two-wheelers
- `TWO WHEELER(T)` = transport two-wheelers
- `TWO WHEELER (INVALID CARRIAGE)` = include only if the user wants all two-wheeler registrations

For a class-level motorcycle/scooter view, use `Vehicle Class Month Wise` and rows such as:

- `M-CYCLE/SCOOTER`
- `M-CYCLE/SCOOTER-WITH SIDE CAR`
- `MOPED`
- `MOTORISED CYCLE (CC > 25CC)`

Only sum these if the user's definition requires class-level two-wheelers.

### 4W

The report page exposes `Vehicle Category Group` as an X-axis, not as a Y-axis for monthwise rows. Therefore there is usually no single monthly `FOUR WHEELER` row.

For broad 4W monthly group totals from `Vehicle Category Month Wise`, sum:

- `LIGHT MOTOR VEHICLE`
- `MEDIUM MOTOR VEHICLE`
- `HEAVY MOTOR VEHICLE`
- `FOUR WHEELER (INVALID CARRIAGE)` if present

For passenger car sales/registrations, use `Vehicle Class Month Wise` and read:

- `MOTOR CAR`

Do not confuse `LIGHT GOODS VEHICLE`, `HEAVY GOODS VEHICLE`, or passenger vehicle categories with the compact VCG `FOUR WHEELER` group unless the user explicitly wants broader commercial/passenger categories too.

## Known limitations

- VAHAN reports registrations, not literal retail sales.
- Month-wise 2W/4W group totals may require summing rows; there is no one-click `FOUR WHEELER` month-wise row in the inspected report page.
- The inspected report page did not expose a clear export/download button. Use table reading/copying or browser automation if extraction is needed.
- Large dimensions such as `Maker` paginate heavily; filter first.
