from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MetricExtractionRule(BaseModel):
    """Declarative rule for extracting one metric from rendered page text."""

    metric_code: str
    unit: str = Field(description='Source unit. The extractor converts to the canonical unit for metric_code when one is registered.')
    value_regex: str = Field(
        description='Regex used to extract the metric value. Prefer a named group called value.'
    )
    selector: str | None = Field(
        default=None,
        description='Optional CSS selector used to scope text before applying regex.',
    )
    period_regex: str | None = Field(
        default=None,
        description='Optional regex used to extract period_label. Prefer named group period.',
    )
    release_date_regex: str | None = Field(
        default=None,
        description='Optional regex used to extract source release date. Prefer named group release_date.',
    )
    value_group: str = 'value'
    period_group: str = 'period'
    release_date_group: str = 'release_date'
    evidence_window_chars: int = 180


class TargetConfig(BaseModel):
    """A messy website/page to render and extract metrics from."""

    code: str
    url: str
    metrics: list[MetricExtractionRule]
    wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] = 'networkidle'
    wait_for_selector: str | None = None
    follow_link_text_regex: str | None = Field(
        default=None,
        description='If set, render the landing page, choose the first matching anchor by text, and follow it.',
    )
    follow_link_href_regex: str | None = Field(
        default=None,
        description='If set, render the landing page, choose the first matching anchor by href, and follow it.',
    )
    screenshot: bool = False


class ExtractedMetric(BaseModel):
    metric_code: str
    value: float
    unit: str
    period_label: str | None = None
    release_date: str | None = None
    source_url: str
    evidence: str


class ExtractionRun(BaseModel):
    target_code: str
    status: Literal['success', 'failed']
    source_url: str
    final_url: str | None = None
    metrics: list[ExtractedMetric] = Field(default_factory=list)
    artifact_dir: str | None = None
    error_message: str | None = None


def load_target_configs(path: Path) -> list[TargetConfig]:
    import json

    payload = json.loads(path.read_text())
    targets = payload.get('targets', payload) if isinstance(payload, dict) else payload
    if not isinstance(targets, list):
        raise ValueError('targets config must be a list or an object with a targets list')
    return [TargetConfig.model_validate(item) for item in targets]
