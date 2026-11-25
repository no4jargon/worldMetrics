from __future__ import annotations

import html
import http.cookiejar
import re
import urllib.parse
import urllib.request
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
FORM_ID = 'masterLayout_formlogin'
MONTH_BY_ABBR = {abbr: index + 1 for index, abbr in enumerate(MONTH_ABBR)}
VAHAN_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)
VAHAN_REFRESH_RENDER_TARGETS = 'VhCatg norms fuel VhClass combTablePnl groupingTable msg vhCatgPnl'
VAHAN_DASHBOARD_RENDER_TARGETS = (
    'v4chart comparison dashboardContentsPanel mainpagepnl calendaryear '
    'yearWiseRegnDataTable yearWiseTransDataTable yearWiseRevDataTable yearWisePermitDataTable'
)


def _parse_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _, value in re.findall(r'([:\w.-]+)\s*=\s*(["\'])(.*?)\2', tag, flags=re.DOTALL):
        attrs[key.lower()] = html.unescape(value)
    return attrs


def _clean_cell(value: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _normalize_row_label(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(value)).strip().upper()


def _parse_indian_number(value: str) -> float:
    cleaned = value.replace(',', '').strip()
    return float(cleaned or '0')


def _extract_form_html(page_html: str) -> str:
    form_match = re.search(
        rf'<form\b(?=[^>]*\bid=["\']{re.escape(FORM_ID)}["\'])[^>]*>.*?</form>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if form_match is None:
        raise ValueError('Could not find VAHAN JSF form')
    return form_match.group(0)


def _form_action(page_html: str, base_url: str) -> str:
    form_html = _extract_form_html(page_html)
    attrs = _parse_attrs(form_html.split('>', 1)[0])
    action = attrs.get('action')
    if not action:
        raise ValueError('Could not find VAHAN JSF form action')
    return urllib.parse.urljoin(base_url, action)


def _extract_form_fields(page_html: str) -> dict[str, str]:
    form_html = _extract_form_html(page_html)
    fields: dict[str, str] = {}

    for input_tag in re.findall(r'<input\b[^>]*>', form_html, flags=re.IGNORECASE | re.DOTALL):
        attrs = _parse_attrs(input_tag)
        name = attrs.get('name')
        if not name:
            continue
        input_type = attrs.get('type', 'text').lower()
        if input_type in {'button', 'file', 'image', 'reset', 'submit'}:
            continue
        if input_type in {'checkbox', 'radio'} and 'checked' not in attrs:
            continue
        fields[name] = attrs.get('value', '')

    for select_match in re.finditer(r'<select\b[^>]*>.*?</select>', form_html, flags=re.IGNORECASE | re.DOTALL):
        select_html = select_match.group(0)
        attrs = _parse_attrs(select_html.split('>', 1)[0])
        name = attrs.get('name')
        if not name:
            continue

        selected_value: str | None = None
        first_value: str | None = None
        for option_match in re.finditer(r'<option\b[^>]*>.*?</option>', select_html, flags=re.IGNORECASE | re.DOTALL):
            option_html = option_match.group(0)
            option_attrs = _parse_attrs(option_html.split('>', 1)[0])
            value = option_attrs.get('value', _clean_cell(option_html))
            if first_value is None:
                first_value = value
            if 'selected' in option_attrs:
                selected_value = value
                break
        fields[name] = selected_value if selected_value is not None else first_value or ''

    return fields


def _find_select_source_for_option(page_html: str, option_label: str, option_value: str) -> str | None:
    normalized_label = _normalize_row_label(option_label)
    for select_match in re.finditer(r'<select\b[^>]*>.*?</select>', page_html, flags=re.IGNORECASE | re.DOTALL):
        select_html = select_match.group(0)
        attrs = _parse_attrs(select_html.split('>', 1)[0])
        select_id = attrs.get('id')
        if not select_id:
            continue
        for option_match in re.finditer(r'<option\b[^>]*>.*?</option>', select_html, flags=re.IGNORECASE | re.DOTALL):
            option_html = option_match.group(0)
            option_attrs = _parse_attrs(option_html.split('>', 1)[0])
            if option_attrs.get('value') == option_value and _normalize_row_label(_clean_cell(option_html)) == normalized_label:
                return select_id.removesuffix('_input')
    return None


def _partial_redirect_url(partial_xml: str) -> str | None:
    match = re.search(r'<redirect\b[^>]*\burl=["\']([^"\']+)["\']', partial_xml, flags=re.IGNORECASE)
    return html.unescape(match.group(1)) if match else None


def _extract_partial_update(partial_xml: str, update_id: str) -> str | None:
    escaped_id = re.escape(update_id)
    cdata_match = re.search(
        rf'<update\b[^>]*\bid=["\']{escaped_id}["\'][^>]*><!\[CDATA\[(.*?)\]\]></update>',
        partial_xml,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cdata_match:
        return cdata_match.group(1)

    update_match = re.search(
        rf'<update\b[^>]*\bid=["\']{escaped_id}["\'][^>]*>(.*?)</update>',
        partial_xml,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html.unescape(update_match.group(1)) if update_match else None


def _apply_view_state(form_fields: dict[str, str], partial_xml: str) -> None:
    match = re.search(
        r'<update\b[^>]*\bid=["\'][^"\']*javax\.faces\.ViewState[^"\']*["\'][^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</update>',
        partial_xml,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        form_fields['javax.faces.ViewState'] = html.unescape(match.group(1)).strip()


def _find_refresh_source(page_html: str) -> tuple[str, str]:
    for button_match in re.finditer(r'<button\b[^>]*>.*?</button>', page_html, flags=re.IGNORECASE | re.DOTALL):
        button_html = button_match.group(0)
        if 'combTablePnl' not in button_html:
            continue
        if 'Refresh' not in _clean_cell(button_html):
            continue
        attrs = _parse_attrs(button_html.split('>', 1)[0])
        source = attrs.get('id')
        if not source:
            continue
        render_match = re.search(r'u:"([^"]+)"', attrs.get('onclick', ''))
        render_targets = render_match.group(1) if render_match else VAHAN_REFRESH_RENDER_TARGETS
        return source, render_targets
    raise ValueError('Could not find VAHAN table refresh button')


def _extract_vahan_year_records(table_html: str, year: int) -> list[dict[str, Any]]:
    headers = [_clean_cell(match.group(0)).upper() for match in re.finditer(r'<th\b[^>]*>.*?</th>', table_html, flags=re.IGNORECASE | re.DOTALL)]
    months: list[int] = []
    for header in headers:
        abbr = header[:3]
        month = MONTH_BY_ABBR.get(abbr)
        if month is not None and month not in months:
            months.append(month)
    if not months:
        raise ValueError(f'Could not find VAHAN month columns for {year}')

    body_match = re.search(r'<tbody\b[^>]*\bid=["\']groupingTable_data["\'][^>]*>(.*?)</tbody>', table_html, flags=re.IGNORECASE | re.DOTALL)
    row_source = body_match.group(1) if body_match else table_html
    totals: dict[int, dict[str, float]] = {month: {'two_wheeler_sales': 0.0, 'four_wheeler_sales': 0.0} for month in months}
    tracked_categories = 0

    for row_match in re.finditer(r'<tr\b[^>]*>.*?</tr>', row_source, flags=re.IGNORECASE | re.DOTALL):
        cells = [_clean_cell(cell.group(0)) for cell in re.finditer(r'<td\b[^>]*>.*?</td>', row_match.group(0), flags=re.IGNORECASE | re.DOTALL)]
        if len(cells) < 2 + len(months):
            continue
        category = _normalize_row_label(cells[1])
        if category not in TWO_WHEELER_ROWS and category not in FOUR_WHEELER_ROWS:
            continue
        tracked_categories += 1
        month_values = cells[2 : 2 + len(months)]
        for month, value in zip(months, month_values):
            parsed_value = _parse_indian_number(value)
            if category in TWO_WHEELER_ROWS:
                totals[month]['two_wheeler_sales'] += parsed_value
            if category in FOUR_WHEELER_ROWS:
                totals[month]['four_wheeler_sales'] += parsed_value

    if tracked_categories == 0:
        raise ValueError(f'Could not find VAHAN tracked vehicle-category rows for {year}')

    return [
        {
            'month': f'{year:04d}-{month:02d}',
            'two_wheeler_sales': totals[month]['two_wheeler_sales'],
            'four_wheeler_sales': totals[month]['four_wheeler_sales'],
        }
        for month in months
    ]


class VAHANDashboardSkillConnector(DatasetConnector, JsonFetchMixin):
    """VAHAN dashboard connector driven by the vahan-dashboard workflow.

    In metadata-only mode this records that `/skill:vahan-dashboard` is the
    retrieval path. In live mode it submits VAHAN's JSF form sequence for
    Tabular Summary -> Vehicle Category x Month Wise -> Calendar Year, then
    sums the rows needed for 2W and 4W registration proxies.
    """

    dataset_code = 'vahan_vehicle_registrations'
    parser_version = 'vahan-tabular-monthwise-jsf-v2'

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
        records: list[dict[str, Any]] = []
        years = sorted(set(self.years))
        self._progress('VAHAN: opening dashboard.', completed_years=0, total_years=len(years))

        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        dashboard_html = self._read_text(opener, self.source_url)
        dashboard_action = _form_action(dashboard_html, self.source_url)
        dashboard_fields = _extract_form_fields(dashboard_html)
        tabular_source = _find_select_source_for_option(dashboard_html, 'Tabular Summary', 'R')
        if tabular_source is None:
            raise ValueError('Could not find VAHAN Tabular Summary selector')
        dashboard_fields[f'{tabular_source}_input'] = 'R'
        redirect_xml = self._post_ajax(
            opener,
            dashboard_action,
            dashboard_fields,
            source=tabular_source,
            execute=tabular_source,
            render=VAHAN_DASHBOARD_RENDER_TARGETS,
            event='change',
        )
        report_url = urllib.parse.urljoin(self.source_url, _partial_redirect_url(redirect_xml) or 'vahan/view/reportview.xhtml')
        report_html = self._read_text(opener, report_url)
        report_action = _form_action(report_html, report_url)
        report_fields = _extract_form_fields(report_html)
        actual_source = _find_select_source_for_option(report_html, 'Actual Value', 'A')
        if actual_source is not None:
            report_fields[f'{actual_source}_input'] = 'A'
        report_fields['selectedYearType_input'] = 'C'
        report_fields['yaxisVar_input'] = 'Vehicle Category'
        yaxis_xml = self._post_ajax(
            opener,
            report_action,
            report_fields,
            source='yaxisVar',
            execute='yaxisVar',
            render='xaxisVar',
            event='change',
        )
        _apply_view_state(report_fields, yaxis_xml)
        report_fields['xaxisVar_input'] = 'Month Wise'
        xaxis_xml = self._post_ajax(
            opener,
            report_action,
            report_fields,
            source='xaxisVar',
            execute='xaxisVar',
            render='multipleYear',
            event='change',
        )
        _apply_view_state(report_fields, xaxis_xml)
        refresh_source, refresh_render = _find_refresh_source(report_html)

        for index, year in enumerate(years, start=1):
            self._progress(f'VAHAN: fetching Calendar Year {year}.', completed_years=index - 1, total_years=len(years), current_year=year)
            report_fields['selectedYear_input'] = str(year)
            year_xml = self._post_ajax(
                opener,
                report_action,
                report_fields,
                source='selectedYear',
                execute='selectedYear',
                render='selectedYear',
                event='change',
            )
            _apply_view_state(report_fields, year_xml)

            table_xml = self._post_ajax(
                opener,
                report_action,
                report_fields,
                source=refresh_source,
                execute=refresh_source,
                render=refresh_render,
                command_field=True,
            )
            _apply_view_state(report_fields, table_xml)
            table_html = _extract_partial_update(table_xml, 'combTablePnl')
            if table_html is None:
                raise ValueError(f'Could not find VAHAN table update for {year}')
            year_records = _extract_vahan_year_records(table_html, year)
            if not self.include_current_month:
                current_month = date.today().strftime('%Y-%m')
                year_records = [record for record in year_records if record['month'] != current_month]
            records.extend(year_records)
            self._progress(f'VAHAN: parsed Calendar Year {year}.', completed_years=index, total_years=len(years), current_year=year)

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

    def _read_text(self, opener, url: str) -> str:
        request = urllib.request.Request(url, headers={'User-Agent': VAHAN_USER_AGENT})
        with opener.open(request, timeout=90) as response:
            return response.read().decode('utf-8', errors='replace')

    def _post_ajax(
        self,
        opener,
        url: str,
        form_fields: dict[str, str],
        source: str,
        execute: str,
        render: str,
        event: str | None = None,
        command_field: bool = False,
    ) -> str:
        payload = dict(form_fields)
        payload.update(
            {
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': source,
                'javax.faces.partial.execute': execute,
                'javax.faces.partial.render': render,
            }
        )
        if event is not None:
            payload['javax.faces.behavior.event'] = event
            payload['javax.faces.partial.event'] = event
        if command_field:
            payload[source] = source

        data = urllib.parse.urlencode(payload).encode('utf-8')
        origin = f'{urllib.parse.urlsplit(url).scheme}://{urllib.parse.urlsplit(url).netloc}'
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Faces-Request': 'partial/ajax',
                'Origin': origin,
                'Referer': url,
                'User-Agent': VAHAN_USER_AGENT,
                'X-Requested-With': 'XMLHttpRequest',
            },
        )
        with opener.open(request, timeout=90) as response:
            return response.read().decode('utf-8', errors='replace')

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
