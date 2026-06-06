from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from app.core.metric_registry import UnitConversionError, canonical_unit_for_metric, convert_value, normalize_unit
from app.extractors.models import ExtractedMetric, ExtractionRun, MetricExtractionRule, TargetConfig


def _number_from_text(value: str) -> float:
    normalized = value.strip().replace(',', '').replace('%', '')
    normalized = re.sub(r'[^0-9.+\-]', '', normalized)
    if normalized in {'', '.', '+', '-'}:
        raise ValueError(f'Invalid numeric value: {value!r}')
    return float(normalized)


def _canonical_metric_value(metric_code: str, value: float, source_unit: str) -> tuple[float, str]:
    canonical_unit = canonical_unit_for_metric(metric_code)
    normalized_source_unit = normalize_unit(source_unit)
    if canonical_unit is None:
        return value, normalized_source_unit
    try:
        return convert_value(value, normalized_source_unit, canonical_unit), canonical_unit
    except UnitConversionError as error:
        raise ValueError(f'wrong unit for {metric_code}: expected {canonical_unit}, got {source_unit}') from error


def _group_or_first(match: re.Match[str], preferred_group: str) -> str:
    groups = match.groupdict()
    if preferred_group in groups and groups[preferred_group] is not None:
        return groups[preferred_group]
    if match.groups():
        return match.group(1)
    return match.group(0)


def _evidence(text: str, match: re.Match[str], window_chars: int) -> str:
    start = max(match.start() - window_chars, 0)
    end = min(match.end() + window_chars, len(text))
    return re.sub(r'\s+', ' ', text[start:end]).strip()


def _extract_optional(regex: str | None, text: str, group: str) -> str | None:
    if regex is None:
        return None
    match = re.search(regex, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if match is None:
        return None
    return _group_or_first(match, group).strip()


def extract_metric_from_text(rule: MetricExtractionRule, text: str, source_url: str) -> ExtractedMetric:
    match = re.search(rule.value_regex, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError(f'Could not extract {rule.metric_code}')

    raw_value = _group_or_first(match, rule.value_group)
    value, unit = _canonical_metric_value(rule.metric_code, _number_from_text(raw_value), rule.unit)
    return ExtractedMetric(
        metric_code=rule.metric_code,
        value=value,
        unit=unit,
        period_label=_extract_optional(rule.period_regex, text, rule.period_group),
        release_date=_extract_optional(rule.release_date_regex, text, rule.release_date_group),
        source_url=source_url,
        evidence=_evidence(text, match, rule.evidence_window_chars),
    )


class PlaywrightMetricExtractor:
    """Renders target pages and extracts metrics from page text.

    Playwright is imported lazily so the normal backend can still run before the
    operator has installed browser binaries with `python -m playwright install chromium`.
    """

    def __init__(self, output_dir: Path, headed: bool = False, timeout_ms: int = 45_000):
        self.output_dir = output_dir
        self.headed = headed
        self.timeout_ms = timeout_ms

    def extract_target(self, target: TargetConfig) -> ExtractionRun:
        try:
            return self._extract_target(target)
        except Exception as error:
            return ExtractionRun(
                target_code=target.code,
                status='failed',
                source_url=target.url,
                error_message=str(error),
            )

    def _extract_target(self, target: TargetConfig) -> ExtractionRun:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as error:
            raise RuntimeError(
                'Playwright is not installed. Run: cd backend && pip install -r requirements.txt && python -m playwright install chromium'
            ) from error

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        artifact_dir = self.output_dir / target.code / timestamp
        artifact_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not self.headed)
            try:
                page = browser.new_page(user_agent='world-metrics-playwright/0.1')
                page.set_default_timeout(self.timeout_ms)
                page.goto(target.url, wait_until=target.wait_until)
                if target.wait_for_selector:
                    page.wait_for_selector(target.wait_for_selector)

                if target.follow_link_text_regex or target.follow_link_href_regex:
                    next_url = self._select_link(page, target)
                    page.goto(next_url, wait_until=target.wait_until)
                    if target.wait_for_selector:
                        page.wait_for_selector(target.wait_for_selector)

                final_url = page.url
                html = page.content()
                text = self._page_text(page)
                (artifact_dir / 'page.html').write_text(html)
                (artifact_dir / 'page.txt').write_text(text)
                if target.screenshot:
                    page.screenshot(path=str(artifact_dir / 'page.png'), full_page=True)

                metrics = []
                for rule in target.metrics:
                    scoped_text = self._scoped_text(page, rule) if rule.selector else text
                    metrics.append(extract_metric_from_text(rule, scoped_text, final_url))

                run = ExtractionRun(
                    target_code=target.code,
                    status='success',
                    source_url=target.url,
                    final_url=final_url,
                    metrics=metrics,
                    artifact_dir=str(artifact_dir),
                )
                (artifact_dir / 'extraction.json').write_text(run.model_dump_json(indent=2))
                return run
            finally:
                browser.close()

    def _page_text(self, page) -> str:
        return page.locator('body').inner_text(timeout=self.timeout_ms)

    def _scoped_text(self, page, rule: MetricExtractionRule) -> str:
        assert rule.selector is not None
        locator = page.locator(rule.selector).first
        return locator.inner_text(timeout=self.timeout_ms)

    def _select_link(self, page, target: TargetConfig) -> str:
        links = page.eval_on_selector_all(
            'a',
            """anchors => anchors.map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.getAttribute('href') || '',
                absoluteHref: a.href || ''
            }))""",
        )
        text_pattern = re.compile(target.follow_link_text_regex, re.IGNORECASE) if target.follow_link_text_regex else None
        href_pattern = re.compile(target.follow_link_href_regex, re.IGNORECASE) if target.follow_link_href_regex else None

        for link in links:
            text = str(link.get('text', ''))
            href = str(link.get('href', ''))
            absolute_href = str(link.get('absoluteHref', '')) or urljoin(target.url, href)
            text_matches = text_pattern.search(text) if text_pattern else True
            href_matches = href_pattern.search(href) or href_pattern.search(absolute_href) if href_pattern else True
            if text_matches and href_matches:
                return absolute_href

        raise ValueError(f'No matching link found for target {target.code}')


def write_runs_json(runs: list[ExtractionRun], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = [run.model_dump(mode='json') for run in runs]
    (output_dir / 'runs.json').write_text(json.dumps(payload, indent=2))
