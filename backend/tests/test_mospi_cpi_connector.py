import unittest
from datetime import date

from app.connectors.mospi_cpi import MoSPICPIConnector
from app.core.models import FetchResult


class MoSPICPIConnectorTests(unittest.TestCase):
    def test_parse_converts_mospi_json_payload_to_canonical_observations(self):
        connector = MoSPICPIConnector()
        raw = FetchResult(
            dataset_code='mospi_cpi',
            status='success',
            parser_version='test',
            source_url='https://example.test/mospi/cpi',
            payload_type='json',
            payload={
                'records': [
                    {
                        'month': '2026-01',
                        'cpi_index': 188.4,
                        'headline_inflation_yoy': 4.9,
                        'release_date': '2026-02-12',
                    },
                    {
                        'month': '2026-02',
                        'cpi_index': 189.0,
                        'headline_inflation_yoy': 5.0,
                        'release_date': '2026-03-12',
                    },
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(4, len(observations))

        cpi_index = [obs for obs in observations if obs.metric_code == 'cpi_index']
        cpi_headline = [obs for obs in observations if obs.metric_code == 'cpi_headline']

        self.assertEqual(['2026-01', '2026-02'], [obs.period_label for obs in cpi_index])
        self.assertEqual(['2026-01', '2026-02'], [obs.period_label for obs in cpi_headline])
        self.assertEqual(188.4, cpi_index[0].value)
        self.assertEqual(5.0, cpi_headline[1].value)
        self.assertEqual(date(2026, 2, 1), cpi_index[1].period_start)
        self.assertEqual(date(2026, 2, 28), cpi_index[1].period_end)
        self.assertEqual(date(2026, 3, 12), cpi_headline[1].source_release_date)
        self.assertEqual('percent', cpi_headline[1].unit)


if __name__ == '__main__':
    unittest.main()
