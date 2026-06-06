from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceConfig:
    dataset_code: str
    listing_url: str
    filters: dict[str, str]
    artifact_mode: str
    extraction_mode: str


DEFAULT_SOURCE_CONFIGS = [
    SourceConfig(
        dataset_code='jll_residential_sales',
        listing_url='https://www.jll.com/en-in/newsroom',
        filters={'title_contains': 'residential'},
        artifact_mode='html',
        extraction_mode='llm_text',
    ),
    SourceConfig(
        dataset_code='vahan_vehicle_registrations',
        listing_url='https://vahan.parivahan.gov.in/vahan4dashboard/',
        filters={'retrieval_skill': 'vahan-dashboard', 'auto_call': 'true', 'view': 'Tabular Summary', 'x_axis': 'Month Wise'},
        artifact_mode='html',
        extraction_mode='agent_skill:vahan-dashboard',
    ),
]


def source_config_by_dataset(dataset_code: str) -> SourceConfig:
    for config in DEFAULT_SOURCE_CONFIGS:
        if config.dataset_code == dataset_code:
            return config
    raise ValueError(f'Unknown dataset code: {dataset_code}')
