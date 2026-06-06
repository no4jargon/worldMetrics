from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.core.models import CanonicalObservation, FetchResult

NPP_MONTHLY_GENERATION_URL = 'https://npp.gov.in/monthlyGenerationReportsAct'
DEFAULT_MONTH_COUNT = 60

MONTH_ABBR = {
    1: 'JAN',
    2: 'FEB',
    3: 'MAR',
    4: 'APR',
    5: 'MAY',
    6: 'JUN',
    7: 'JUL',
    8: 'AUG',
    9: 'SEP',
    10: 'OCT',
    11: 'NOV',
    12: 'DEC',
}


class NPPMonthlyGenerationConnector(DatasetConnector, JsonFetchMixin):
    """Power metrics from NPP Monthly Generation Reports Actual.

    The NPP page is form-driven and CSRF/session protected. This connector uses
    Playwright to render the page, submit one month at a time, find the All India
    XLS link, download it through the browser context, and parse the workbook.
    """

    dataset_code = 'npp_monthly_generation'
    parser_version = 'npp-monthly-generation-playwright-v1'

    def __init__(
        self,
        fixture_path: Path | None = None,
        source_url: str | None = NPP_MONTHLY_GENERATION_URL,
        months: list[str] | None = None,
        start_period: str | None = None,
        end_period: str | None = None,
        artifact_dir: Path | None = None,
        headed: bool = False,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.fixture_path = fixture_path
        self.source_url = source_url
        self.months = months
        self.start_period = start_period
        self.end_period = end_period
        self.artifact_dir = artifact_dir
        self.headed = headed
        self.progress_callback = progress_callback

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or (self.source_url and self.source_url.endswith('.json')):
            return self._fetch_json()

        if self.source_url is None:
            raise NotImplementedError('Wire this connector to the NPP monthly generation source')

        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as error:
            raise RuntimeError(
                'Playwright is not installed. Run: cd backend && pip install -r requirements.txt && python -m playwright install chromium'
            ) from error

        records: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        months = self._target_months()
        artifact_dir = self.artifact_dir or Path(os.environ.get('NPP_POWER_ARTIFACT_DIR', '../artifacts/npp-power'))
        artifact_dir.mkdir(parents=True, exist_ok=True)

        self._emit_progress({'event': 'start', 'total_months': len(months), 'completed_months': 0})

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not self.headed)
            try:
                page = browser.new_page(user_agent='world-metrics-playwright/0.1')
                page.set_default_timeout(45_000)
                for index, period in enumerate(months, start=1):
                    self._emit_progress(
                        {
                            'event': 'month_running',
                            'current_month': period,
                            'total_months': len(months),
                            'completed_months': index - 1,
                            'records_found': len(records),
                            'skipped_months': len(skipped),
                        }
                    )
                    try:
                        page.goto(self.source_url, wait_until='networkidle')
                        xls_url = self._submit_month_and_find_all_india_xls(page, period)
                        xls_bytes = self._download_xls(page, xls_url)
                        xls_path = artifact_dir / f'npp-all-india-{period}.xls'
                        xls_path.write_bytes(xls_bytes)
                        record = self._parse_all_india_xls(xls_bytes, period)
                        record['xls_url'] = xls_url
                        record['artifact_path'] = str(xls_path)
                        records.append(record)
                        self._emit_progress(
                            {
                                'event': 'month_success',
                                'current_month': period,
                                'total_months': len(months),
                                'completed_months': index,
                                'records_found': len(records),
                                'skipped_months': len(skipped),
                            }
                        )
                    except Exception as error:
                        skipped.append({'month': period, 'error': str(error)})
                        self._emit_progress(
                            {
                                'event': 'month_skipped',
                                'current_month': period,
                                'total_months': len(months),
                                'completed_months': index,
                                'records_found': len(records),
                                'skipped_months': len(skipped),
                                'last_error': str(error),
                            }
                        )
            finally:
                browser.close()

        self._emit_progress(
            {
                'event': 'done',
                'total_months': len(months),
                'completed_months': len(months),
                'records_found': len(records),
                'skipped_months': len(skipped),
            }
        )

        return FetchResult(
            dataset_code=self.dataset_code,
            status='success' if records else 'failed',
            parser_version=self.parser_version,
            source_url=self.source_url,
            payload_type='json',
            payload={'records': records, 'skipped': skipped},
        )

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if self.progress_callback is not None:
            self.progress_callback({'dataset_code': self.dataset_code, **payload})

    def _target_months(self) -> list[str]:
        if self.months is not None:
            return self.months

        env_months = os.environ.get('NPP_POWER_MONTHS')
        if env_months:
            return [item.strip() for item in env_months.split(',') if item.strip()]

        start = self.start_period or os.environ.get('NPP_POWER_START_MONTH')
        end = self.end_period or os.environ.get('NPP_POWER_END_MONTH')
        if start or end:
            range_end = end or date.today().strftime('%Y-%m')
            if start is None:
                return _last_n_months(DEFAULT_MONTH_COUNT, range_end)
            return _month_range(start, range_end)
        return _last_n_months(DEFAULT_MONTH_COUNT)

    def _submit_month_and_find_all_india_xls(self, page, period: str) -> str:
        form_month = _period_to_form_month(period)
        page.locator('#rmonth').evaluate("el => el.removeAttribute('readonly')")
        page.locator('#rmonth').fill(form_month)
        page.locator('#submitBtn').click()
        page.wait_for_load_state('networkidle')

        return page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('tr'));
                for (const row of rows) {
                    const text = (row.innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (text.includes('1.') && text.includes('all india')) {
                        const link = Array.from(row.querySelectorAll('a'))
                            .map(a => a.href)
                            .find(href => href && href.toLowerCase().endsWith('.xls'));
                        if (link) return link;
                    }
                }
                return null;
            }"""
        ) or _raise(f'No All India XLS link found for {period}')

    def _download_xls(self, page, xls_url: str) -> bytes:
        response = page.request.get(xls_url)
        if not response.ok:
            raise ValueError(f'NPP XLS download failed with HTTP {response.status}: {xls_url}')
        return response.body()

    def _parse_all_india_xls(self, xls_bytes: bytes, period: str) -> dict[str, Any]:
        try:
            import xlrd
        except ModuleNotFoundError as error:
            raise RuntimeError('xlrd is required for NPP .xls parsing. Run: cd backend && pip install -r requirements.txt') from error

        book = xlrd.open_workbook(file_contents=xls_bytes)
        sheet = book.sheet_by_index(0)
        rows = [[sheet.cell_value(row_index, col_index) for col_index in range(sheet.ncols)] for row_index in range(sheet.nrows)]
        total_row_index: int | None = None
        thermal_row: list[Any] | None = None
        release_date: date | None = None

        for row_index, row in enumerate(rows):
            label = str(row[0]).strip().upper() if row else ''
            if label == 'TOTAL':
                total_row_index = row_index
            if label == 'THERMAL':
                thermal_row = row
            for col_index, value in enumerate(row[:-1]):
                if str(value).strip().upper().startswith('DATE'):
                    release_date = _excel_date_to_date(row[col_index + 1], book.datemode)

        if total_row_index is None:
            raise ValueError(f'Could not find TOTAL row in NPP All India XLS for {period}')
        if thermal_row is None:
            raise ValueError(f'Could not find THERMAL row in NPP All India XLS for {period}')

        generation_gwh = _first_exact_actual_value_for_row(rows, total_row_index, period)
        thermal_plf = float(thermal_row[18])
        return {
            'month': period,
            'generation_bu': generation_gwh / 1000.0,
            'generation_gwh': generation_gwh,
            'thermal_plf_percent': thermal_plf,
            'release_date': release_date.isoformat() if release_date else None,
            'source_note': 'NPP Monthly Generation Reports Actual, All India XLS sub-report 1.',
        }

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('NPP monthly generation payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            release_date = date.fromisoformat(record['release_date']) if record.get('release_date') else None
            notes = record.get('source_note')
            observations.append(
                CanonicalObservation(
                    metric_code='power_output_total',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=_record_generation_gwh(record),
                    unit='GWh',
                    source_release_date=release_date,
                    notes=notes,
                    source_url=record.get('xls_url'),
                )
            )
            observations.append(
                CanonicalObservation(
                    metric_code='power_utilization_plf',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['thermal_plf_percent']),
                    unit='percent',
                    source_release_date=release_date,
                    notes=notes,
                    source_url=record.get('xls_url'),
                )
            )
        return observations


def _first_exact_actual_value_for_row(rows: list[list[Any]], row_index: int, period: str) -> float:
    """Return the row value in the first column containing a cell exactly equal to ACTUAL.

    NPP workbooks have several nearby labels such as "Actual Same Month". Those
    must not count. Scan columns from left to right, pick the first column where
    any cell value normalises exactly to "ACTUAL", then read that column from
    the requested row, e.g. TOTAL.
    """

    max_cols = max((len(row) for row in rows), default=0)
    target_row = rows[row_index]
    for col_index in range(max_cols):
        if any(col_index < len(row) and _normalise_header_cell(row[col_index]) == 'ACTUAL' for row in rows):
            if col_index >= len(target_row) or target_row[col_index] in ('', None):
                raise ValueError(f'First ACTUAL column has no value in TOTAL row for {period}')
            return float(target_row[col_index])
    raise ValueError(f'Could not find first ACTUAL column value in TOTAL row for {period}')


def _normalise_header_cell(value: Any) -> str:
    return ' '.join(str(value).replace('\xa0', ' ').split()).upper()


def _record_generation_gwh(record: dict[str, Any]) -> float:
    if record.get('generation_gwh') is not None:
        return float(record['generation_gwh'])
    return float(record['generation_bu']) * 1000.0


def _period_to_form_month(period: str) -> str:
    year, month = period.split('-')
    return f'{int(month):02d}/{year}'


def _last_n_months(months: int, end_period: str | None = None) -> list[str]:
    if end_period:
        year, month = [int(part) for part in end_period.split('-')]
    else:
        today = date.today()
        year, month = today.year, today.month
    periods: list[str] = []
    for _ in range(months):
        periods.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return list(reversed(periods))


def _month_range(start: str, end: str) -> list[str]:
    start_year, start_month = [int(part) for part in start.split('-')]
    end_year, end_month = [int(part) for part in end.split('-')]
    year, month = start_year, start_month
    periods: list[str] = []
    while (year, month) <= (end_year, end_month):
        periods.append(f'{year:04d}-{month:02d}')
        month += 1
        if month == 13:
            year += 1
            month = 1
    return periods


def _excel_date_to_date(value: Any, datemode: int) -> date | None:
    if value in ('', None):
        return None
    try:
        import xlrd

        if isinstance(value, (int, float)):
            return xlrd.xldate_as_datetime(value, datemode).date()
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _raise(message: str) -> None:
    raise ValueError(message)
