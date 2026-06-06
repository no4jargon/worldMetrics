import unittest
from datetime import date

from app.connectors.cea_power import CEAPowerMonthlyConnector
from app.core.models import FetchResult


class CEAPowerMonthlyConnectorTests(unittest.TestCase):
    def test_parse_converts_cea_json_payload_to_power_output_observations(self):
        connector = CEAPowerMonthlyConnector()
        raw = FetchResult(
            dataset_code='cea_power_monthly',
            status='success',
            parser_version='test',
            source_url='https://example.test/cea/power',
            payload_type='json',
            payload={
                'records': [
                    {
                        'month': '2026-01',
                        'generation_bu': 141.3,
                        'release_date': '2026-02-20',
                    },
                    {
                        'month': '2026-02',
                        'generation_bu': 142.5,
                        'release_date': '2026-03-20',
                    },
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(2, len(observations))
        self.assertEqual('power_output_total', observations[0].metric_code)
        self.assertEqual('2026-01', observations[0].period_label)
        self.assertEqual(141.3, observations[0].value)
        self.assertEqual('BU', observations[0].unit)
        self.assertEqual(date(2026, 2, 28), observations[1].period_end)
        self.assertEqual(date(2026, 3, 20), observations[1].source_release_date)


if __name__ == '__main__':
    unittest.main()
