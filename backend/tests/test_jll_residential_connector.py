import unittest
from datetime import date

from app.connectors.jll_residential import JLLResidentialConnector
from app.core.models import FetchResult


class JLLResidentialConnectorTests(unittest.TestCase):
    def test_parse_converts_jll_payload_to_home_sales_observations(self):
        connector = JLLResidentialConnector()
        raw = FetchResult(
            dataset_code='jll_residential_sales',
            status='success',
            parser_version='test',
            source_url='https://example.test/jll/residential',
            payload_type='json',
            payload={
                'records': [
                    {'quarter': '2025-Q4', 'sales_units': 75100, 'segment': 'top_7_cities', 'release_date': '2026-01-20'},
                    {'quarter': '2026-Q1', 'sales_units': 76200, 'segment': 'top_7_cities', 'release_date': '2026-04-20'},
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(2, len(observations))
        self.assertEqual('home_sales_jll', observations[0].metric_code)
        self.assertEqual('2025-Q4', observations[0].period_label)
        self.assertEqual(75100, observations[0].value)
        self.assertEqual('units', observations[0].unit)
        self.assertEqual('top_7_cities', observations[0].segment)
        self.assertEqual(date(2026, 3, 31), observations[1].period_end)
        self.assertEqual(date(2026, 4, 20), observations[1].source_release_date)


if __name__ == '__main__':
    unittest.main()
