from __future__ import annotations

from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.core.models import CanonicalObservation, FetchResult

VAHAN_DASHBOARD_URL = 'https://vahan.parivahan.gov.in/vahan4dashboard/'
VAHAN_RETRIEVAL_SKILL = 'vahan-dashboard'
MONTH_ABBR = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
TWO_WHEELER_ROWS = {'TWO WHEELER(NT)', 'TWO WHEELER(T)', 'TWO WHEELER (INVALID CARRIAGE)'}
FOUR_WHEELER_ROWS = {'LIGHT MOTOR VEHICLE', 'MEDIUM MOTOR VEHICLE', 'HEAVY MOTOR VEHICLE', 'FOUR WHEELER (INVALID CARRIAGE)'}


def _parse_indian_number(value: str) -> float:
    cleaned = value.replace(',', '').strip()
    return float(cleaned or '0')


class VAHANDashboardSkillConnector(DatasetConnector, JsonFetchMixin):
    """VAHAN dashboard connector driven by the vahan-dashboard skill workflow.

    In metadata-only mode this records that `/skill:vahan-dashboard` is the
    retrieval path. In live mode it automates the same skill workflow with
    Playwright: Tabular Summary -> Vehicle Category x Month Wise -> Calendar
    Year, then sums the VAHAN rows needed for 2W and 4W registration proxies.
    """

    dataset_code = 'vahan_vehicle_registrations'
    parser_version = 'vahan-tabular-monthwise-v1'

    def __init__(
        self,
        source_url: str = VAHAN_DASHBOARD_URL,
        retrieval_skill: str = VAHAN_RETRIEVAL_SKILL,
        years: list[int] | None = None,
        fixture_path: Path | None = None,
        live: bool = False,
        progress_callback=None,
        include_current_month: bool = False,
    ) -> None:
        self.source_url = source_url
        self.retrieval_skill = retrieval_skill
        self.years = years or [date.today().year - 1, date.today().year]
        self.fixture_path = fixture_path
        self.live = live
        self.progress_callback = progress_callback
        self.include_current_month = include_current_month

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or self.source_url.endswith('.json'):
            return self._fetch_json()

        if not self.live:
            return FetchResult(
                dataset_code=self.dataset_code,
                status='skill_requested',
                parser_version='vahan-skill-001',
                source_url=self.source_url,
                payload_type='agent_skill_request',
                payload={
                    'retrieval_skill': self.retrieval_skill,
                    'skill_command': f'/skill:{self.retrieval_skill}',
                    'auto_requested': True,
                    'metrics': ['two_wheeler_sales', 'four_wheeler_sales'],
                    'message': f'Automatically requested /skill:{self.retrieval_skill} for VAHAN Tabular Summary retrieval.',
                },
            )

        return self._fetch_live()

    def _progress(self, message: str, **extra: Any) -> None:
        if self.progress_callback:
            self.progress_callback({'dataset_code': self.dataset_code, 'message': message, **extra})

    def _fetch_live(self) -> FetchResult:
        from playwright.sync_api import sync_playwright

        records: list[dict[str, Any]] = []
        years = sorted(set(self.years))
        self._progress('VAHAN: opening dashboard.', completed_years=0, total_years=len(years))

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(ignore_https_errors=True)
            page.goto(self.source_url, wait_until='networkidle', timeout=90_000)
            self._select_hidden(page, '#j_idt17_input', 'R')  # Tabular Summary
            self._select_hidden(page, '#j_idt27_input', 'A')  # Actual Value
            self._select_hidden(page, '#yaxisVar_input', 'Vehicle Category')
            self._select_hidden(page, '#xaxisVar_input', 'Month Wise')
            self._select_hidden(page, '#selectedYearType_input', 'C')  # Calendar Year

            for index, year in enumerate(years, start=1):
                self._progress(f'VAHAN: fetching Calendar Year {year}.', completed_years=index - 1, total_years=len(years), current_year=year)
                self._select_hidden(page, '#selectedYear_input', str(year))
                page.locator('#j_idt68').click(timeout=15_000)
                page.wait_for_load_state('networkidle', timeout=90_000)
                page.wait_for_function(
                    "year => document.querySelector('#groupingTable')?.innerText.includes(`(${year})`)",
                    arg=str(year),
                    timeout=90_000,
                )
                page.wait_for_selector('#groupingTable_data tr', timeout=90_000)
                # PrimeFaces can mark the page as network-idle before the
                # scrollable datatable body has swapped from the previous year.
                page.wait_for_timeout(3_000)
                year_records = self._extract_year_records(page, year)
                if not self.include_current_month:
                    current_month = date.today().strftime('%Y-%m')
                    year_records = [record for record in year_records if record['month'] != current_month]
                records.extend(year_records)
                self._progress(f'VAHAN: parsed Calendar Year {year}.', completed_years=index, total_years=len(years), current_year=year)

            browser.close()

        return FetchResult(
            dataset_code=self.dataset_code,
            status='success',
            parser_version=self.parser_version,
            source_url=self.source_url,
            payload_type='json',
            payload={
                'retrieval_skill': self.retrieval_skill,
                'workflow': 'Tabular Summary: Vehicle Category x Month Wise, Calendar Year, Actual Value',
                'records': records,
            },
        )

    @staticmethod
    def _select_hidden(page, selector: str, value: str) -> None:
        page.locator(selector).select_option(value=value, force=True, timeout=20_000)
        page.wait_for_load_state('networkidle', timeout=90_000)
        page.wait_for_timeout(500)

    @staticmethod
    def _extract_year_records(page, year: int) -> list[dict[str, Any]]:
        headers = page.locator('#groupingTable_head th[id^="groupingTable:j_idt100:"]').evaluate_all(
            "els => els.map(e => e.innerText.trim().toUpperCase()).filter(Boolean)"
        )
        months = [MONTH_ABBR.index(header[:3]) + 1 for header in headers if header[:3] in MONTH_ABBR]
        totals: dict[int, dict[str, float]] = {month: {'two_wheeler_sales': 0.0, 'four_wheeler_sales': 0.0} for month in months}

        rows = page.locator('#groupingTable_data tr')
        for row_index in range(rows.count()):
            cells = rows.nth(row_index).locator('td').evaluate_all('els => els.map(e => e.innerText.trim())')
            if len(cells) < 4:
                continue
            category = cells[1].upper()
            month_values = cells[2:2 + len(months)]
            for month, value in zip(months, month_values):
                parsed_value = _parse_indian_number(value)
                if category in TWO_WHEELER_ROWS:
                    totals[month]['two_wheeler_sales'] += parsed_value
                if category in FOUR_WHEELER_ROWS:
                    totals[month]['four_wheeler_sales'] += parsed_value

        records = []
        for month in months:
            period = f'{year:04d}-{month:02d}'
            records.append(
                {
                    'month': period,
                    'two_wheeler_sales': totals[month]['two_wheeler_sales'],
                    'four_wheeler_sales': totals[month]['four_wheeler_sales'],
                }
            )
        return records

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('VAHAN payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            for metric_code in ('two_wheeler_sales', 'four_wheeler_sales'):
                if metric_code not in record:
                    continue
                observations.append(
                    CanonicalObservation(
                        metric_code=metric_code,
                        period_label=record['month'],
                        period_start=period_start,
                        period_end=period_end,
                        value=float(record[metric_code]),
                        unit='units',
                        geography='India',
                        segment='domestic',
                        notes=f'VAHAN registration proxy via /skill:{self.retrieval_skill}; Tabular Summary Vehicle Category x Month Wise.',
                        source_url=raw.source_url,
                    )
                )
        return observations
