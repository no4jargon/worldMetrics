import unittest
from datetime import date

from app.connectors.oea_cement import OEACoreIndustriesConnector
from app.core.models import FetchResult


class OEACoreIndustriesConnectorTests(unittest.TestCase):
    def test_parse_converts_oea_payload_to_cement_output_and_utilization_observations(self):
        connector = OEACoreIndustriesConnector()
        raw = FetchResult(
            dataset_code='oea_core_industries',
            status='success',
            parser_version='test',
            source_url='https://example.test/oea/cement',
            payload_type='json',
            payload={
                'records': [
                    {
                        'month': '2026-01',
                        'cement_output_mt': 33.0,
                        'annual_capacity_mt': 420.0,
                        'release_date': '2026-02-28',
                    },
                    {
                        'month': '2026-02',
                        'cement_output_mt': 34.3,
                        'annual_capacity_mt': 420.0,
                        'release_date': '2026-03-28',
                    },
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(4, len(observations))
        output_obs = [obs for obs in observations if obs.metric_code == 'cement_output']
        utilization_obs = [obs for obs in observations if obs.metric_code == 'cement_utilization_est']

        self.assertEqual('MT', output_obs[0].unit)
        self.assertEqual(33.0, output_obs[0].value)
        self.assertEqual('percent', utilization_obs[0].unit)
        self.assertAlmostEqual((33.0 / (420.0 / 12.0)) * 100.0, utilization_obs[0].value)
        self.assertIn('estimated', (utilization_obs[0].notes or '').lower())
        self.assertEqual(date(2026, 3, 28), utilization_obs[1].source_release_date)


if __name__ == '__main__':
    unittest.main()
