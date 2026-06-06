from __future__ import annotations

import json
import re
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from dateutil import parser as date_parser

from app.connectors.base import DatasetConnector
from app.core.metric_registry import canonical_unit_for_metric, canonicalize_observation
from app.core.models import CanonicalObservation, FetchResult

WaitUntil = Literal['commit', 'domcontentloaded', 'load', 'networkidle']


@dataclass(frozen=True)
class MetricExtractionRule:
    """Regex rule for a metric on a rendered page.

    `value_pattern` must contain a named capture `value`. It may also contain
    `unit` and `period` captures. If the value pattern does not capture period,
    configure `period_pattern` with a named `period` capture.
    """

    metric_code: str
    value_pattern: str
    source_unit: str | None = None
    period_pattern: str | None = None
    cadence: Literal['monthly', 'quarterly'] = 'monthly'
    segment: str | None = None
    geography: str = 'India'
    value_multiplier: float = 1.0
    flags: int = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True)
class PlaywrightTargetConfig:
    dataset_code: str
    url: str
    rules: list[MetricExtractionRule]
    wait_until: WaitUntil = 'networkidle'
    wait_for_selector: str | None = None
    click_selectors: list[str] = field(default_factory=list)
    parser_version: str = 'playwright-regex-v1'
    artifact_dir: Path | None = None
    headed: bool = False
    timeout_ms: int = 45_000


class PlaywrightMetricConnector(DatasetConnector):
    """Config-driven connector for JS-rendered websites.

    Use this as the starting point for target websites you provide: first render
    the page with Playwright, then apply explicit extraction rules that map each
    source value/unit to one canonical metric. Parsed observations are
    canonicalized before emission (for example, BU -> GWh for power totals).
    """

    def __init__(self, config: PlaywrightTargetConfig):
        self.config = config
        self.dataset_code = config.dataset_code
        self.parser_version = config.parser_version

    def fetch(self) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as error:
            raise RuntimeError(
                'Playwright is not installed. Run: cd backend && pip install -r requirements.txt '
                '&& python -m playwright install chromium'
            ) from error

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not self.config.headed)
            try:
                page = browser.new_page(user_agent='world-metrics-playwright/0.1')
                page.set_default_timeout(self.config.timeout_ms)
                page.goto(self.config.url, wait_until=self.config.wait_until)
                if self.config.wait_for_selector:
                    page.wait_for_selector(self.config.wait_for_selector)
                for selector in self.config.click_selectors:
                    page.locator(selector).click()
                    page.wait_for_load_state(self.config.wait_until)
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                html = page.content()
                artifact_path = self._write_artifact(html, text)
            finally:
                browser.close()

        return FetchResult(
            dataset_code=self.dataset_code,
            status='success',
            parser_version=self.parser_version,
            source_url=self.config.url,
            payload_type='json',
            payload={'text': text, 'html': html, 'artifact_path': str(artifact_path) if artifact_path else None},
        )

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        if not isinstance(raw.payload, dict):
            raise ValueError('Playwright metric payload must be a dict')
        text = str(raw.payload.get('text') or '')
        observations = [self._parse_rule(text, rule) for rule in self.config.rules]
        return [canonicalize_observation(obs) for obs in observations]

    def _parse_rule(self, text: str, rule: MetricExtractionRule) -> CanonicalObservation:
        value_match = re.search(rule.value_pattern, text, rule.flags)
        if value_match is None:
            raise ValueError(f'Could not extract value for {rule.metric_code}')

        groups = value_match.groupdict()
        value = _parse_number(groups.get('value') or value_match.group(1)) * rule.value_multiplier
        unit = groups.get('unit') or rule.source_unit or canonical_unit_for_metric(rule.metric_code)
        if unit is None:
            raise ValueError(f'No unit configured for {rule.metric_code}')

        period_text = groups.get('period')
        if not period_text and rule.period_pattern:
            period_match = re.search(rule.period_pattern, text, rule.flags)
            if period_match is None:
                raise ValueError(f'Could not extract period for {rule.metric_code}')
            period_text = period_match.groupdict().get('period') or period_match.group(1)
        if not period_text:
            raise ValueError(f'No period captured/configured for {rule.metric_code}')

        period_label, period_start, period_end = _period_bounds(period_text, rule.cadence)
        return CanonicalObservation(
            metric_code=rule.metric_code,
            period_label=period_label,
            period_start=period_start,
            period_end=period_end,
            value=value,
            unit=unit,
            geography=rule.geography,
            segment=rule.segment,
            notes=f'Extracted from {self.config.url}',
            source_url=self.config.url,
        )

    def _write_artifact(self, html: str, text: str) -> Path | None:
        if self.config.artifact_dir is None:
            return None
        self.config.artifact_dir.mkdir(parents=True, exist_ok=True)
        safe_dataset = re.sub(r'[^a-zA-Z0-9_.-]+', '-', self.dataset_code)
        path = self.config.artifact_dir / f'{safe_dataset}.json'
        path.write_text(json.dumps({'url': self.config.url, 'text': text, 'html': html}, indent=2))
        return path


def build_playwright_connectors_from_file(path: Path) -> list[PlaywrightMetricConnector]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError('Playwright target config must be a JSON list')
    return [PlaywrightMetricConnector(_target_config_from_dict(item)) for item in payload]


def _target_config_from_dict(data: dict[str, Any]) -> PlaywrightTargetConfig:
    rules = [MetricExtractionRule(**rule) for rule in data.pop('rules')]
    if data.get('artifact_dir') is not None:
        data['artifact_dir'] = Path(data['artifact_dir'])
    return PlaywrightTargetConfig(rules=rules, **data)


def _parse_number(value: str) -> float:
    cleaned = value.strip().replace(',', '')
    cleaned = re.sub(r'[^0-9.+\-]', '', cleaned)
    if cleaned in {'', '.', '+', '-'}:
        raise ValueError(f'Invalid numeric value: {value!r}')
    return float(cleaned)


def _period_bounds(period_text: str, cadence: str) -> tuple[str, date, date]:
    text = re.sub(r'\s+', ' ', period_text.strip())
    quarter_match = re.search(r'(?:Q(?P<q1>[1-4])\s*[- ]?\s*(?P<y1>20\d{2})|(?P<y2>20\d{2})\s*[- ]?\s*Q(?P<q2>[1-4]))', text, re.IGNORECASE)
    if cadence == 'quarterly' or quarter_match:
        if quarter_match is None:
            raise ValueError(f'Invalid quarterly period: {period_text}')
        quarter = int(quarter_match.group('q1') or quarter_match.group('q2'))
        year = int(quarter_match.group('y1') or quarter_match.group('y2'))
        start_month = ((quarter - 1) * 3) + 1
        end_month = start_month + 2
        end_day = monthrange(year, end_month)[1]
        return f'{year}-Q{quarter}', date(year, start_month, 1), date(year, end_month, end_day)

    if re.fullmatch(r'20\d{2}-\d{2}', text):
        year, month = [int(part) for part in text.split('-')]
    else:
        normalized = re.sub(r'([A-Za-z]+)-?(20\d{2})', r'\1 \2', text)
        parsed = date_parser.parse(normalized, fuzzy=True, default=datetime(1900, 1, 1))
        year, month = parsed.year, parsed.month
    end_day = monthrange(year, month)[1]
    return f'{year:04d}-{month:02d}', date(year, month, 1), date(year, month, end_day)
