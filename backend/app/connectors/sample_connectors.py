from __future__ import annotations

from datetime import date

from app.connectors.base import DatasetConnector
from app.core.models import CanonicalObservation, FetchResult
from app.sample_data.series import SAMPLE_SERIES


class SampleConnector(DatasetConnector):
    def __init__(self, dataset_code: str, metric_codes: list[str]):
        self.dataset_code = dataset_code
        self.metric_codes = metric_codes

    def fetch(self) -> FetchResult:
        payload = {code: SAMPLE_SERIES[code] for code in self.metric_codes}
        return FetchResult(
            dataset_code=self.dataset_code,
            status='success',
            parser_version='sample-v1',
            source_url='local://sample_data',
            payload_type='json',
            payload=payload,
        )

    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        observations: list[CanonicalObservation] = []
        payload = raw.payload
        assert isinstance(payload, dict)

        for metric_code, points in payload.items():
            for point in points:
                observations.append(
                    CanonicalObservation(
                        metric_code=metric_code,
                        period_label=point['period_label'],
                        period_start=date.fromisoformat(point['period_start']),
                        period_end=date.fromisoformat(point['period_end']),
                        value=point['value'],
                        unit=point['unit'],
                        segment=point.get('segment'),
                        source_release_date=date.fromisoformat(point['source_release_date']) if point.get('source_release_date') else None,
                        is_preliminary=point.get('is_preliminary', False),
                        notes=point.get('notes'),
                    )
                )
        return observations


class CEAPowerMonthlyConnector(SampleConnector):
    def __init__(self):
        super().__init__('cea_power_monthly', ['power_output_total'])


class CEAPLFConnector(SampleConnector):
    def __init__(self):
        super().__init__('cea_plf_monthly', ['power_utilization_plf'])


class OEACoreIndustriesConnector(SampleConnector):
    def __init__(self):
        super().__init__('oea_core_industries', ['cement_output'])


class JLLResidentialConnector(SampleConnector):
    def __init__(self):
        super().__init__('jll_residential_sales', ['home_sales_jll'])


class MoSPICPIConnector(SampleConnector):
    def __init__(self):
        super().__init__('mospi_cpi', ['cpi_index', 'cpi_headline'])
