from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.connectors.live_text import build_fetch_result, latest_link, month_label, parse_date_text, read_text_url
from app.core.models import CanonicalObservation, FetchResult


class MoSPICPIConnector(DatasetConnector, JsonFetchMixin):
    dataset_code = 'mospi_cpi'
    parser_version = 'mospi-cpi-json-v1'

    def __init__(self, fixture_path: Path | None = None, source_url: str | None = None):
        self.fixture_path = fixture_path
        self.source_url = source_url

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or (self.source_url and self.source_url.endswith('.json')):
            return self._fetch_json()

        if self.source_url is None:
            raise NotImplementedError('Wire this connector to the live MoSPI source')

        listing_html = read_text_url(self.source_url)
        release_url = latest_link(
            listing_html,
            self.source_url,
            lambda text: 'press release' in text.lower() and 'cpi' in text.lower(),
        )
        release_text = read_text_url(release_url)
        return build_fetch_result(
            self.dataset_code,
            'mospi-cpi-live-v1',
            release_url,
            {'records': [self._parse_live_record(release_text)]},
        )

    def _parse_live_record(self, release_text: str) -> dict:
        month_match = re.search(r'FOR\s+([A-Z]+),\s*(\d{4})', release_text, re.IGNORECASE)
        if month_match is None:
            raise ValueError('Could not determine MoSPI report month')
        month = month_label(f"{month_match.group(1)} {month_match.group(2)}")

        release_date = parse_date_text(release_text)
        value_match = re.search(r'All\s+India\s+Combined\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)', release_text, re.IGNORECASE)
        if value_match is None:
            raise ValueError('Could not parse MoSPI CPI values')

        return {
            'month': month,
            'cpi_index': float(value_match.group(1)),
            'headline_inflation_yoy': float(value_match.group(2)),
            'release_date': release_date.isoformat() if release_date else None,
        }

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('MoSPI CPI payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            release_date = date.fromisoformat(record['release_date']) if record.get('release_date') else None

            observations.append(
                CanonicalObservation(
                    metric_code='cpi_index',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['cpi_index']),
                    unit='index',
                    source_release_date=release_date,
                )
            )
            observations.append(
                CanonicalObservation(
                    metric_code='cpi_headline',
                    period_label=record['month'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['headline_inflation_yoy']),
                    unit='percent',
                    source_release_date=release_date,
                )
            )

        return observations
