import json
import tempfile
import unittest
from pathlib import Path

from app.main import run_real


class MainRealTests(unittest.TestCase):
    def test_run_real_builds_snapshot_files_from_fixture_backed_real_connectors(self):
        fixtures = {
            'npp_monthly_generation': {
                'records': [
                    {'month': '2026-01', 'generation_gwh': 141300.0, 'thermal_plf_percent': 68.3, 'release_date': '2026-02-20'},
                    {'month': '2026-02', 'generation_gwh': 142500.0, 'thermal_plf_percent': 69.1, 'release_date': '2026-03-20'},
                ]
            },
            'oea_core_industries': {
                'records': [
                    {'month': '2026-01', 'cement_output_mt': 33.0, 'annual_capacity_mt': 420.0, 'release_date': '2026-02-28'},
                    {'month': '2026-02', 'cement_output_mt': 34.3, 'annual_capacity_mt': 420.0, 'release_date': '2026-03-28'},
                ]
            },
            'jll_residential_sales': {
                'records': [
                    {'quarter': '2025-Q4', 'sales_units': 75100, 'segment': 'top_7_cities', 'release_date': '2026-01-20'},
                    {'quarter': '2026-Q1', 'sales_units': 76200, 'segment': 'top_7_cities', 'release_date': '2026-04-20'},
                ]
            },
            'mospi_cpi': {
                'records': [
                    {'month': '2026-01', 'cpi_index': 188.4, 'headline_inflation_yoy': 4.9, 'release_date': '2026-02-12'},
                    {'month': '2026-02', 'cpi_index': 189.0, 'headline_inflation_yoy': 5.0, 'release_date': '2026-03-12'},
                ]
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            fixture_paths = {}
            for dataset_code, payload in fixtures.items():
                path = tmp / f'{dataset_code}.json'
                path.write_text(json.dumps(payload))
                fixture_paths[dataset_code] = path

            output_dir = tmp / 'output'
            run_real(output_dir=output_dir, fixture_paths=fixture_paths)

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}
            self.assertEqual(142500.0, cards['power_output_total']['latest_value'])
            self.assertEqual(69.1, cards['power_utilization_plf']['latest_value'])
            self.assertEqual(34.3, cards['cement_output']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])


if __name__ == '__main__':
    unittest.main()
