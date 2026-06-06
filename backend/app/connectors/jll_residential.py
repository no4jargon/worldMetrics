from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.connectors.base import DatasetConnector
from app.connectors.json_fetch import JsonFetchMixin
from app.connectors.live_text import build_fetch_result, extract_links, normalize_space, parse_date_text, quarter_label, read_text_url, resolve_link
from app.connectors.trace import emit_trace
from app.core.models import CanonicalObservation, FetchResult


def _quarter_bounds(period_label: str) -> tuple[date, date]:
    year = int(period_label[:4])
    quarter = int(period_label[-1])
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    start_month, start_day = starts[quarter]
    end_month, end_day = ends[quarter]
    return date(year, start_month, start_day), date(year, end_month, end_day)


class JLLResidentialConnector(DatasetConnector, JsonFetchMixin):
    dataset_code = 'jll_residential_sales'
    parser_version = 'jll-residential-json-v1'

    def __init__(
        self,
        fixture_path: Path | None = None,
        source_url: str | None = None,
        trace_messages: list[str] | None = None,
        sitemap_url: str | None = None,
    ):
        self.fixture_path = fixture_path
        self.source_url = source_url
        self.trace_messages = trace_messages
        self.sitemap_url = sitemap_url

    def fetch(self) -> FetchResult:
        if self.fixture_path is not None or (self.source_url and self.source_url.endswith('.json')):
            return self._fetch_json()

        if self.source_url is None:
            raise NotImplementedError('Wire this connector to the live JLL source')

        emit_trace(self.trace_messages, self.dataset_code, f'loading listing {self.source_url}')
        listing_html = read_text_url(self.source_url)
        article_url = self._latest_article_url(listing_html)
        emit_trace(self.trace_messages, self.dataset_code, f'selected article {article_url}')
        article_html = read_text_url(article_url)
        return build_fetch_result(
            self.dataset_code,
            'jll-residential-live-v1',
            article_url,
            {'records': [self._parse_live_record(article_html)]},
        )

    def _latest_article_url(self, listing_html: str) -> str:
        candidates: list[tuple[str, str]] = []
        relevant_fallback_urls: list[str] = []
        for href, text in extract_links(listing_html):
            if self.source_url is None:
                continue
            resolved = resolve_link(self.source_url, href)
            label = normalize_space(text)
            lower_label = label.lower()
            lower_url = resolved.lower()
            has_residential_keyword = any(keyword in lower_label for keyword in ('residential', 'housing', 'sales'))
            has_home_phrase = 'home ' in f'{lower_label} ' or ' home' in lower_label
            has_newsroom_url = '/newsroom/' in lower_url
            is_relevant = has_newsroom_url or (len(lower_label.split()) > 2 and (has_residential_keyword or has_home_phrase))
            if is_relevant:
                relevant_fallback_urls.append(resolved)
            quarter = quarter_label(label)
            if quarter is not None and is_relevant:
                candidates.append((quarter, resolved))
        if candidates and len(candidates) == len(relevant_fallback_urls):
            return max(candidates, key=lambda item: item[0])[1]
        if len(relevant_fallback_urls) == 1:
            return relevant_fallback_urls[0]
        if relevant_fallback_urls:
            article_candidates: list[tuple[str, str]] = []
            for url in relevant_fallback_urls:
                article_html = read_text_url(url)
                try:
                    record = self._parse_live_record(article_html)
                except ValueError:
                    continue
                article_candidates.append((record['quarter'], url))
            if article_candidates:
                return max(article_candidates, key=lambda item: item[0])[1]
        return self._latest_article_from_sitemap()

    def _latest_article_from_sitemap(self) -> str:
        sitemap_url = self.sitemap_url or self._default_sitemap_url()
        sitemap_xml = read_text_url(sitemap_url)
        urls = re.findall(r'<loc>(.*?)</loc>', sitemap_xml, re.IGNORECASE)
        candidates: list[tuple[str, str]] = []
        for url in urls:
            url_lower = url.lower()
            if '/newsroom/' not in url_lower:
                continue
            if not any(keyword in url_lower for keyword in ('residential', 'housing', 'home', 'sales')):
                continue
            article_html = read_text_url(url)
            try:
                record = self._parse_live_record(article_html)
            except ValueError:
                continue
            candidates.append((record['quarter'], url))
        if not candidates:
            raise ValueError('No JLL quarterly release links found')
        return max(candidates, key=lambda item: item[0])[1]

    def _default_sitemap_url(self) -> str:
        if self.source_url is None:
            raise ValueError('Missing JLL source URL')
        if '/en-in/' in self.source_url:
            prefix = self.source_url.split('/en-in/', 1)[0]
            return f'{prefix}/en-in/sitemap.xml'
        raise ValueError('Could not derive JLL sitemap URL')

    def _parse_live_record(self, article_html: str) -> dict:
        article_text = re.sub(r'<[^>]+>', ' ', article_html)
        quarter_match = re.search(r'Q([1-4])\s*([0-9]{4})', article_text, re.IGNORECASE)
        if quarter_match is None:
            raise ValueError('Could not determine JLL quarter')
        quarter = f"{quarter_match.group(2)}-Q{quarter_match.group(1)}"

        release_date = parse_date_text(article_html)
        sales_match = re.search(r'<tr[^>]*>\s*<td>\s*India\s*</td>\s*<td>\s*([0-9,]+)\s*</td>', article_html, re.IGNORECASE)
        if sales_match is None:
            raise ValueError('Could not parse JLL India sales row')

        sales_units = int(sales_match.group(1).replace(',', ''))
        emit_trace(self.trace_messages, self.dataset_code, f'found residential sales {sales_units} for {quarter}')

        return {
            'quarter': quarter,
            'sales_units': sales_units,
            'segment': 'top_7_cities',
            'release_date': release_date.isoformat() if release_date else None,
        }

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        payload = raw.payload
        if not isinstance(payload, dict):
            raise ValueError('JLL residential payload must be a dict')

        observations: list[CanonicalObservation] = []
        for record in payload.get('records', []):
            period_start, period_end = _quarter_bounds(record['quarter'])
            release_date = date.fromisoformat(record['release_date']) if record.get('release_date') else None
            observations.append(
                CanonicalObservation(
                    metric_code='home_sales_jll',
                    period_label=record['quarter'],
                    period_start=period_start,
                    period_end=period_end,
                    value=float(record['sales_units']),
                    unit='units',
                    segment=record.get('segment', 'top_7_cities'),
                    source_release_date=release_date,
                )
            )

        return observations
