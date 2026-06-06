from __future__ import annotations

from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector
from app.connectors.mospi_cpi import MoSPICPIConnector
from app.connectors.npp_power import NPP_MONTHLY_GENERATION_URL, NPPMonthlyGenerationConnector
from app.connectors.oea_cement import OEACoreIndustriesConnector
from app.connectors.vahan_skill import VAHAN_DASHBOARD_URL, VAHANDashboardSkillConnector


ConnectorConfig = dict[str, Path | str]


def _fixture_path(config: ConnectorConfig, dataset_code: str) -> Path | None:
    value = config.get(dataset_code)
    return value if isinstance(value, Path) else None


def _source_url(config: ConnectorConfig, dataset_code: str) -> str | None:
    value = config.get(dataset_code)
    return value if isinstance(value, str) else None


def build_real_connectors(
    fixture_paths: ConnectorConfig | None = None,
    source_urls: ConnectorConfig | None = None,
    live_vahan: bool = False,
    vahan_years: list[int] | None = None,
    vahan_progress_callback=None,
) -> list:
    fixture_paths = fixture_paths or {}
    source_urls = source_urls or {}
    return [
        NPPMonthlyGenerationConnector(
            fixture_path=_fixture_path(fixture_paths, 'npp_monthly_generation'),
            source_url=_source_url(source_urls, 'npp_monthly_generation') or NPP_MONTHLY_GENERATION_URL,
        ),
        OEACoreIndustriesConnector(
            fixture_path=_fixture_path(fixture_paths, 'oea_core_industries'),
            source_url=_source_url(source_urls, 'oea_core_industries'),
        ),
        JLLResidentialConnector(
            fixture_path=_fixture_path(fixture_paths, 'jll_residential_sales'),
            source_url=_source_url(source_urls, 'jll_residential_sales'),
        ),
        VAHANDashboardSkillConnector(
            fixture_path=_fixture_path(fixture_paths, 'vahan_vehicle_registrations'),
            source_url=_source_url(source_urls, 'vahan_vehicle_registrations') or VAHAN_DASHBOARD_URL,
            live=live_vahan,
            years=vahan_years,
            progress_callback=vahan_progress_callback,
        ),
        MoSPICPIConnector(
            fixture_path=_fixture_path(fixture_paths, 'mospi_cpi'),
            source_url=_source_url(source_urls, 'mospi_cpi'),
        ),
    ]
