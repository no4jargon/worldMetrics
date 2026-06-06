from __future__ import annotations

from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector
from app.live.source_registry import DEFAULT_SOURCE_CONFIGS


ConnectorConfig = dict[str, Path | str]


def _fixture_path(config: ConnectorConfig, dataset_code: str) -> Path | None:
    value = config.get(dataset_code)
    return value if isinstance(value, Path) else None


def _source_url(config: ConnectorConfig, dataset_code: str) -> str | None:
    value = config.get(dataset_code)
    return value if isinstance(value, str) else None


def _default_sources() -> dict[str, str]:
    return {config.dataset_code: config.listing_url for config in DEFAULT_SOURCE_CONFIGS}


def build_personal_tracker_connectors(
    fixture_paths: ConnectorConfig | None = None,
    source_urls: ConnectorConfig | None = None,
    trace_messages: list[str] | None = None,
) -> list:
    fixture_paths = fixture_paths or {}
    merged_source_urls = _default_sources()
    merged_source_urls.update(source_urls or {})
    return [
        JLLResidentialConnector(
            fixture_path=_fixture_path(fixture_paths, 'jll_residential_sales'),
            source_url=_source_url(merged_source_urls, 'jll_residential_sales'),
            trace_messages=trace_messages,
        ),
    ]
