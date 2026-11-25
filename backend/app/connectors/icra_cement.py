from __future__ import annotations

import json
import os
import re
import time
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from app.connectors.base import DatasetConnector
from app.core.models import CanonicalObservation, FetchResult

ICRA_RESEARCH_DETAILS_URL = 'https://www.icra.in/Research/ResearchDetails/1'
ICRA_REPORTS_AJAX_URL = 'https://www.icra.in/Research/GetSectorResearchReportDetails'
ICRA_CEMENT_SECTOR_ID = '40'
ICRA_MONTHLY_UPDATE_CATEGORY_ID = '6'
ICRA_CORPORATE_INDUSTRY_ID = '1'


@dataclass(frozen=True)
class ICRAReport:
    report_id: str
    title: str
    report_url: str
    release_date: str | None
    listing_page: int


class ICRACementMonthlyUpdatesConnector(DatasetConnector):
    """Extract explicit monthly cement production volumes from ICRA monthly updates.

    ICRA's listing is an ASP.NET form. Report pages can expose either HTML body text
    or an embedded PDF summary. This connector reads the PDF when it is available and
    falls back to the HTML page text. Only explicit month-level statements such as
    "Cement volumes ... in April 2026 to 42.8 million metric tonnes" are emitted.
    Cumulative FY/Q/11M values are retained in audit context but not emitted.
    """

    dataset_code = 'icra_cement_monthly_updates'
    parser_version = 'icra-cement-monthly-v1'

    def __init__(
        self,
        fixture_path: Path | None = None,
        source_url: str = ICRA_RESEARCH_DETAILS_URL,
        max_pages: int = 10,
        artifact_dir: Path | None = None,
        request_delay_seconds: float = 0.15,
        llm_model: str | None = None,
    ):
        self.fixture_path = fixture_path
        self.source_url = source_url
        self.max_pages = max_pages
        self.artifact_dir = artifact_dir
        self.request_delay_seconds = request_delay_seconds
        self.llm_model = llm_model or os.environ.get('OPENAI_MODEL') or 'gpt-5.5'

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None:
            payload = json.loads(Path(self.fixture_path).read_text())
            return FetchResult(
                dataset_code=self.dataset_code,
                status='success',
                parser_version=self.parser_version,
                source_url=self.source_url,
                payload_type='json',
                payload=payload,
            )

        reports, listing_pages = self._fetch_report_listing()
        records: list[dict] = []
        unmatched_reports: list[dict] = []

        for report in reports:
            report_html = self._read_url(report.report_url).decode('utf-8', 'ignore')
            self._write_artifact(f'reports/{report.report_id}.html', report_html.encode())
            text_sources: list[tuple[str, str]] = []

            pdf_url = self._summary_pdf_url(report.report_id, report_html, report.report_url)
            if pdf_url:
                pdf_bytes = self._try_read_binary(pdf_url, referer=report.report_url)
                if pdf_bytes and pdf_bytes.startswith(b'%PDF'):
                    self._write_artifact(f'pdfs/{report.report_id}.pdf', pdf_bytes)
                    pdf_text = self._extract_pdf_text(pdf_bytes)
                    self._write_artifact(f'text/{report.report_id}.txt', pdf_text.encode())
                    if pdf_text.strip():
                        text_sources.append(('pdf_summary', pdf_text))

            html_text = self._html_to_text(report_html)
            if html_text.strip():
                text_sources.append(('html_page', html_text))

            report_records = self._extract_records_from_sources(report, text_sources)
            if report_records:
                records.extend(report_records)
            else:
                unmatched_reports.append(
                    {
                        'report_id': report.report_id,
                        'title': report.title,
                        'report_url': report.report_url,
                        'release_date': report.release_date,
                    }
                )
            time.sleep(self.request_delay_seconds)

        payload = {
            'records': self._dedupe_records(records),
            'reports': [report.__dict__ for report in reports],
            'listing_pages_checked': listing_pages,
            'unmatched_reports': unmatched_reports,
        }
        self._write_artifact('icra-cement-extracted.json', json.dumps(payload, indent=2).encode())

        return FetchResult(
            dataset_code=self.dataset_code,
            status='success',
            parser_version=self.parser_version,
            source_url=self.source_url,
            payload_type='json',
            payload=payload,
        )

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('ICRA cement payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            release_date = self._parse_release_date(record.get('release_date'))
            observations.append(
                CanonicalObservation(
                    metric_code='cement_output',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['cement_output_mt']),
                    unit='MT',
                    source_release_date=release_date,
                    notes=record.get('evidence'),
                    source_url=record.get('report_url') or raw.source_url,
                )
            )
        return observations

    def _fetch_report_listing(self) -> tuple[list[ICRAReport], list[int]]:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        landing_html = self._read_url(self.source_url, opener=opener).decode('utf-8', 'ignore')
        token_match = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', landing_html)
        if token_match is None:
            raise ValueError('Could not find ICRA anti-forgery token')
        token = token_match.group(1)

        reports: list[ICRAReport] = []
        seen_ids: set[str] = set()
        listing_pages: list[int] = []
        for page in range(1, self.max_pages + 1):
            page_html = self._post_listing_page(opener, token, page)
            self._write_artifact(f'pages/page-{page}.html', page_html.encode())
            page_reports = self._parse_listing_page(page_html, page)
            if not page_reports:
                if page > 1:
                    break
                continue
            listing_pages.append(page)
            for report in page_reports:
                if report.report_id in seen_ids:
                    continue
                seen_ids.add(report.report_id)
                reports.append(report)

            if 'PagedList-skipToNext' in page_html and re.search(r'PagedList-skipToNext[^>]*disabled', page_html):
                break
            time.sleep(self.request_delay_seconds)
        return reports, listing_pages

    def _post_listing_page(self, opener, token: str, page: int) -> str:
        data = urlencode(
            {
                '__RequestVerificationToken': token,
                'SelectedSector.SectorId': ICRA_CEMENT_SECTOR_ID,
                'ResearchReportCategoryId': ICRA_MONTHLY_UPDATE_CATEGORY_ID,
                'DateFrom': '',
                'DateTo': '',
                'KeyWord': '',
            }
        ).encode()
        url = f'{ICRA_REPORTS_AJAX_URL}?IndustryId={ICRA_CORPORATE_INDUSTRY_ID}&page={page}&isSpecialComments=false'
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': self.source_url,
            'Origin': 'https://www.icra.in',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/html, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        with opener.open(Request(url, data=data, headers=headers), timeout=45) as response:
            return response.read().decode('utf-8', 'ignore')

    def _parse_listing_page(self, html: str, page: int) -> list[ICRAReport]:
        reports: list[ICRAReport] = []
        for match in re.finditer(r'<a[^>]+href="([^"]*?/Research/ViewResearchReport/[^"]+)"[^>]*title="([^"]+)"', html, re.S):
            href = unescape(match.group(1))
            title = self._normalize_space(unescape(match.group(2)))
            report_id_match = re.search(r'/Research/ViewResearchReport/(?:[^/]+/)?(\d+)', href)
            if report_id_match is None:
                continue
            row_start = html.rfind('<tr', 0, match.start())
            row_end = html.find('</tr>', match.end())
            row = html[row_start:row_end] if row_start != -1 and row_end != -1 else ''
            cells = [self._html_to_text(cell) for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            release_date = cells[0] if cells else None
            reports.append(
                ICRAReport(
                    report_id=report_id_match.group(1),
                    title=title,
                    report_url=urljoin(self.source_url, href),
                    release_date=release_date,
                    listing_page=page,
                )
            )
        return reports

    def _summary_pdf_url(self, report_id: str, report_html: str, report_url: str) -> str | None:
        match = re.search(r'file=([^"&]*?/Rating/DownloadResearchSummaryReport/\d+)', report_html)
        if match:
            return urljoin(report_url, unescape(match.group(1)))
        if 'Download Summary' in report_html:
            return urljoin(report_url, f'/Rating/DownloadResearchSummaryReport/{report_id}')
        return None

    def _extract_records_from_sources(self, report: ICRAReport, text_sources: Iterable[tuple[str, str]]) -> list[dict]:
        return self._extract_records_with_llm(report, list(text_sources))

    def _extract_records_with_llm(self, report: ICRAReport, text_sources: list[tuple[str, str]]) -> list[dict]:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY is required for ICRA cement extraction; non-LLM extraction is intentionally disabled')

        source_name, source_text = self._preferred_llm_source(text_sources)
        if not source_text.strip():
            return []

        prompt = self._llm_prompt(report, source_name, source_text)
        request_payload = {
            'model': self.llm_model,
            'input': [
                {
                    'role': 'system',
                    'content': (
                        'You are a careful financial-data extraction analyst. Extract only explicit India cement '
                        'production/output/volume values stated for a named calendar month. Return only valid JSON. '
                        'Never infer a monthly value from cumulative FY/quarter/month-to-date values.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
            'text': {'format': {'type': 'json_object'}},
        }
        request = Request(
            'https://api.openai.com/v1/responses',
            data=json.dumps(request_payload).encode(),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                response_payload = json.loads(response.read().decode('utf-8'))
        except Exception as error:
            self._write_artifact(f'llm/{report.report_id}-error.txt', str(error).encode())
            raise RuntimeError(f'OpenAI extraction failed for ICRA report {report.report_id}: {error}') from error

        content = self._response_text(response_payload)
        self._write_artifact(f'llm/{report.report_id}.json', content.encode())
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError(f'OpenAI extraction returned non-JSON for ICRA report {report.report_id}') from error

        records: list[dict] = []
        for item in parsed.get('records', []):
            month = str(item.get('month') or '')
            if not self._is_period_label(month):
                continue
            try:
                value = float(item['cement_output_mt'])
            except (KeyError, TypeError, ValueError):
                continue
            records.append(
                {
                    'month': month,
                    'cement_output_mt': value,
                    'release_date': report.release_date,
                    'report_id': report.report_id,
                    'report_title': report.title,
                    'report_url': report.report_url,
                    'evidence': self._normalize_space(str(item.get('evidence') or '')),
                    'artifact_source': source_name,
                    'extraction_method': f'openai:{self.llm_model}',
                }
            )
        return self._dedupe_records(records)

    def _preferred_llm_source(self, text_sources: list[tuple[str, str]]) -> tuple[str, str]:
        for source_name, source_text in text_sources:
            if source_name == 'pdf_summary' and source_text.strip():
                return source_name, source_text[:18000]
        if not text_sources:
            return '', ''
        source_name, source_text = text_sources[0]
        snippets = self._relevant_snippets(source_text)
        return source_name, snippets[:18000]

    def _relevant_snippets(self, text: str) -> str:
        normalized = self._normalize_space(text)
        lower_text = normalized.lower()
        needles = [
            'cement production volumes',
            'cement volumes',
            'production volumes',
            'million metric tonnes',
            'million mt',
        ]
        snippets: list[str] = []
        seen_offsets: set[int] = set()
        for needle in needles:
            start = 0
            while True:
                index = lower_text.find(needle, start)
                if index == -1:
                    break
                window_start = max(0, index - 700)
                window_end = min(len(normalized), index + 1200)
                if window_start not in seen_offsets:
                    seen_offsets.add(window_start)
                    snippets.append(normalized[window_start:window_end])
                if len('\n---\n'.join(snippets)) > 18000:
                    return '\n---\n'.join(snippets)[:18000]
                start = index + len(needle)
        return '\n---\n'.join(snippets) if snippets else normalized[:18000]

    def _llm_prompt(self, report: ICRAReport, source_name: str, source_text: str) -> str:
        return f"""
Report title: {report.title}
Report date: {report.release_date}
Report URL: {report.report_url}
Artifact source: {source_name}

Task: find explicit month-specific India cement production/output/volume in million tonnes/MT.
Return JSON exactly like:
{{"records":[{{"month":"YYYY-MM","cement_output_mt":42.8,"evidence":"exact quote from report","confidence":"high"}}],"conflicts":[]}}

Rules:
- Use the PDF/presentation text when Artifact source is pdf_summary; use the page text only when no PDF/presentation text exists.
- Include a record only when a specific calendar month is named (for example April 2026) and the report explicitly gives a million tonnes/MT production/output/volume value for that month.
- Ignore cumulative periods such as FY2026, Q1 FY2026, H1 FY2026, 11M FY2026, 9M FY2025, forecasts, installed capacity, prices, coal/petcoke/diesel values, and utilization.
- Ignore values denominated as $/MT or Rs./MT because those are input-cost prices, not cement production.
- If the report gives multiple conflicting explicit values for the same month, do not guess. Return no record for that month and add a conflicts item with month, values, and evidence.
- If there is no explicit month-specific million-tonne cement production value, return {{"records":[],"conflicts":[]}}.
- Evidence must be the shortest exact quote that contains the month and the value.

Report text:
{source_text}
""".strip()

    def _response_text(self, payload: dict) -> str:
        if isinstance(payload.get('output_text'), str):
            return payload['output_text']
        output = payload.get('output') or []
        for item in output:
            for content in item.get('content') or []:
                if content.get('type') in {'output_text', 'text'} and isinstance(content.get('text'), str):
                    return content['text']
        raise ValueError('OpenAI response did not include output text')

    def _is_period_label(self, value: str) -> bool:
        parts = value.split('-')
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            return False
        if not parts[0].isdigit() or not parts[1].isdigit():
            return False
        year = int(parts[0])
        month = int(parts[1])
        return 2000 <= year <= 2100 and 1 <= month <= 12

    def _dedupe_records(self, records: list[dict]) -> list[dict]:
        deduped: dict[str, dict] = {}
        for record in records:
            period = record['month']
            existing = deduped.get(period)
            if existing is None or str(record.get('release_date') or '') > str(existing.get('release_date') or ''):
                deduped[period] = record
        return [deduped[key] for key in sorted(deduped)]

    def _read_url(self, url: str, opener=None) -> bytes:
        opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))
        with opener.open(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': self.source_url}), timeout=45) as response:
            return response.read()

    def _try_read_binary(self, url: str, referer: str) -> bytes | None:
        try:
            with build_opener(HTTPCookieProcessor(CookieJar())).open(
                Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': referer}), timeout=45
            ) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError):
            return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        try:
            from io import BytesIO

            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError('pypdf is required to read ICRA embedded PDF summaries') from error

        reader = PdfReader(BytesIO(pdf_bytes))
        return '\n'.join(page.extract_text() or '' for page in reader.pages)

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r'<script\b.*?</script>', ' ', html, flags=re.S | re.I)
        text = re.sub(r'<style\b.*?</style>', ' ', text, flags=re.S | re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        return self._normalize_space(unescape(text))

    def _normalize_space(self, value: str) -> str:
        return re.sub(r'\s+', ' ', value.replace('\xa0', ' ')).strip()

    def _parse_release_date(self, value: str | None) -> date | None:
        if not value:
            return None
        value = self._normalize_space(value)
        for fmt in ('%d %b %Y', '%d %B %Y'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    def _write_artifact(self, relative_path: str, data: bytes) -> None:
        if self.artifact_dir is None:
            return
        path = self.artifact_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
