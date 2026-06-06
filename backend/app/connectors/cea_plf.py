from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.connectors.live_text import build_fetch_result, extract_links, month_label, normalize_space, parse_date_text, parse_month_year, read_text_url, resolve_link
from app.core.models import CanonicalObservation, FetchResult


class CEAPLFConnector(DatasetConnector, JsonFetchMixin):
    dataset_code = 'cea_plf_monthly'
    parser_version = 'cea-plf-json-v1'

    def __init__(self, fixture_path: Path | None = None, source_url: str | None = None):
        self.fixture_path = fixture_path
        self.source_url = source_url

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or (self.source_url and self.source_url.endswith('.json')):
            return self._fetch_json()

        if self.source_url is None:
            raise NotImplementedError('Wire this connector to the live CEA PLF source')

        listing_html = read_text_url(self.source_url)
        release_url, release_date = self._latest_release(listing_html)
        release_text = read_text_url(release_url)
        record = self._parse_live_record(release_text)
        record['release_date'] = release_date.isoformat() if release_date else None
        return build_fetch_result(
            self.dataset_code,
            'cea-plf-live-v1',
            release_url,
            {'records': [record]},
        )

    def _latest_release(self, listing_html: str) -> tuple[str, date | None]:
        candidates: list[tuple[tuple[int, int], str, date | None]] = []
        for href, text in extract_links(listing_html):
            label = normalize_space(f'{href} {text}')
            parsed = parse_month_year(label)
            if parsed is None or self.source_url is None:
                continue
            prefix = listing_html.split(href, 1)[0][-80:]
            release_date = parse_date_text(prefix)
            candidates.append((parsed, resolve_link(self.source_url, href), release_date))
        if not candidates:
            raise ValueError('No CEA executive summary links found')
        _, url, release_date = max(candidates, key=lambda item: item[0])
        return url, release_date

    def _parse_live_record(self, release_text: str) -> dict:
        month_match = re.search(r'([A-Za-z]+)-?(\d{4})\s+([0-9]+(?:\.[0-9]+)?)', release_text, re.IGNORECASE)
        if month_match is None:
            raise ValueError('Could not determine CEA PLF month/value')
        month = month_label(f"{month_match.group(1)} {month_match.group(2)}")
        return {
            'month': month,
            'thermal_plf_percent': float(month_match.group(3)),
        }

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('CEA PLF payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            release_date = date.fromisoformat(record['release_date']) if record.get('release_date') else None
            observations.append(
                CanonicalObservation(
                    metric_code='power_utilization_plf',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['thermal_plf_percent']),
                    unit='percent',
                    source_release_date=release_date,
                )
            )

        return observations
