import unittest
from datetime import date

from app.connectors.cea_plf import CEAPLFConnector
from app.core.models import FetchResult


class CEAPLFConnectorTests(unittest.TestCase):
    def test_parse_converts_cea_plf_json_payload_to_power_utilization_observations(self):
        connector = CEAPLFConnector()
        raw = FetchResult(
            dataset_code='cea_plf_monthly',
            status='success',
            parser_version='test',
            source_url='https://example.test/cea/plf',
            payload_type='json',
            payload={
                'records': [
                    {'month': '2026-01', 'thermal_plf_percent': 68.3, 'release_date': '2026-02-20'},
                    {'month': '2026-02', 'thermal_plf_percent': 69.1, 'release_date': '2026-03-20'},
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(2, len(observations))
        self.assertEqual('power_utilization_plf', observations[0].metric_code)
        self.assertEqual(68.3, observations[0].value)
        self.assertEqual('percent', observations[0].unit)
        self.assertEqual(date(2026, 2, 28), observations[1].period_end)
        self.assertEqual(date(2026, 3, 20), observations[1].source_release_date)


if __name__ == '__main__':
    unittest.main()
