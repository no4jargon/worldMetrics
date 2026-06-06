import json
import tempfile
import unittest
from pathlib import Path

from app.main import run_real


class MainRealSourceUrlTests(unittest.TestCase):
    def test_run_real_builds_snapshots_from_source_url_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            fixtures = {
                'npp.json': {
                    'records': [
                        {'month': '2026-02', 'generation_gwh': 142500.0, 'thermal_plf_percent': 69.1, 'release_date': '2026-03-20'}
                    ]
                },
                'oea.json': {
                    'records': [
                        {'month': '2026-02', 'cement_output_index': 235.2, 'release_date': '2026-03-20'}
                    ]
                },
                'jll.json': {
                    'records': [
                        {'quarter': '2025-Q3', 'sales_units': 67980, 'segment': 'top_7_cities', 'release_date': '2025-10-28'}
                    ]
                },
                'mospi.json': {
                    'records': [
                        {'month': '2026-02', 'cpi_index': 104.57, 'headline_inflation_yoy': 3.21, 'release_date': '2026-03-12'}
                    ]
                },
            }
            for filename, payload in fixtures.items():
                (tmp / filename).write_text(json.dumps(payload))

            output_dir = tmp / 'output'
            run_real(
                output_dir=output_dir,
                source_urls={
                    'npp_monthly_generation': (tmp / 'npp.json').as_uri(),
                    'oea_core_industries': (tmp / 'oea.json').as_uri(),
                    'jll_residential_sales': (tmp / 'jll.json').as_uri(),
                    'mospi_cpi': (tmp / 'mospi.json').as_uri(),
                },
            )

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}

            self.assertEqual(142500.0, cards['power_output_total']['latest_value'])
            self.assertEqual(69.1, cards['power_utilization_plf']['latest_value'])
            self.assertEqual(235.2, cards['cement_output_index']['latest_value'])
            self.assertEqual(67980.0, cards['home_sales_jll']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])
            self.assertEqual(3.21, cards['cpi_headline']['latest_value'])


if __name__ == '__main__':
    unittest.main()
