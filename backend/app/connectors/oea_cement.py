from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.connectors.live_text import build_fetch_result, extract_links, month_label, normalize_space, parse_date_text, read_text_url, resolve_link
from app.core.models import CanonicalObservation, FetchResult


class OEACoreIndustriesConnector(DatasetConnector, JsonFetchMixin):
    dataset_code = 'oea_core_industries'
    parser_version = 'oea-cement-json-v1'

    def __init__(self, fixture_path: Path | None = None, source_url: str | None = None):
        self.fixture_path = fixture_path
        self.source_url = source_url

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or (self.source_url and self.source_url.endswith('.json')):
            return self._fetch_json()

        if self.source_url is None:
            raise NotImplementedError('Wire this connector to the live OEA/DPIIT source')

        landing_html = read_text_url(self.source_url)
        release_url = self._latest_release_url(landing_html)
        release_text = read_text_url(release_url)
        return build_fetch_result(
            self.dataset_code,
            'oea-cement-live-v1',
            release_url,
            {'records': [self._parse_live_record(release_text)]},
        )

    def _latest_release_url(self, landing_html: str) -> str:
        if self.source_url is None:
            raise ValueError('Missing OEA source URL')
        for href, text in extract_links(landing_html):
            label = normalize_space(f'{href} {text}').lower()
            if 'eight_infra' in label or 'press release' in label:
                return resolve_link(self.source_url, href)
        raise ValueError('No OEA release links found')

    def _parse_live_record(self, release_text: str) -> dict:
        month_match = re.search(r'FOR\s+([A-Z]+),\s*(\d{4})', release_text, re.IGNORECASE)
        if month_match is None:
            raise ValueError('Could not determine OEA report month')
        month = month_label(f"{month_match.group(1)} {month_match.group(2)}")
        release_date_match = re.search(r'([A-Za-z]+\s+\d{1,2},\s*\d{4})', release_text)
        release_date = parse_date_text(release_date_match.group(1)) if release_date_match else None
        cement_match = re.search(r'Feb-26\*\s+([0-9]+(?:\.[0-9]+)?)', release_text, re.IGNORECASE)
        if cement_match is None:
            cement_match = re.search(r'Cement\s+([0-9]+(?:\.[0-9]+)?)', release_text, re.IGNORECASE)
        if cement_match is None:
            raise ValueError('Could not parse OEA cement index')

        return {
            'month': month,
            'cement_output_index': float(cement_match.group(1)),
            'release_date': release_date.isoformat() if release_date else None,
            'is_provisional': 'provisional' in release_text.lower(),
        }

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('OEA cement payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start = date.fromisoformat(f"{record['month']}-01")
            period_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
            release_date = date.fromisoformat(record['release_date']) if record.get('release_date') else None
            is_provisional = bool(record.get('is_provisional', False))

            output_index = record.get('cement_output_index')
            if output_index is not None:
                observations.append(
                    CanonicalObservation(
                        metric_code='cement_output_index',
                        period_label=record['month'],
                        period_start=period_start,
                        period_end=period_end,
                        value=float(output_index),
                        unit='index',
                        source_release_date=release_date,
                        is_preliminary=is_provisional,
                    )
                )

            output_mt = record.get('cement_output_mt')
            if output_mt is not None:
                output_mt_value = float(output_mt)
                observations.append(
                    CanonicalObservation(
                        metric_code='cement_output',
                        period_label=record['month'],
                        period_start=period_start,
                        period_end=period_end,
                        value=output_mt_value,
                        unit='MT',
                        source_release_date=release_date,
                        is_preliminary=is_provisional,
                    )
                )

                annual_capacity_mt = record.get('annual_capacity_mt')
                if annual_capacity_mt:
                    utilization = (output_mt_value / (float(annual_capacity_mt) / 12.0)) * 100.0
                    observations.append(
                        CanonicalObservation(
                            metric_code='cement_utilization_est',
                            period_label=record['month'],
                            period_start=period_start,
                            period_end=period_end,
                            value=utilization,
                            unit='percent',
                            source_release_date=release_date,
                            is_preliminary=is_provisional,
                            notes='Estimated using annual installed capacity divided by 12.',
                        )
                    )

        return observations
