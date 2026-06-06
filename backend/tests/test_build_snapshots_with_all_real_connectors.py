import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.cea_plf import CEAPLFConnector
from app.connectors.cea_power import CEAPowerMonthlyConnector
from app.connectors.jll_residential import JLLResidentialConnector
from app.connectors.mospi_cpi import MoSPICPIConnector
from app.connectors.oea_cement import OEACoreIndustriesConnector
from app.pipelines.build_snapshots import build_snapshots


class BuildSnapshotsWithAllRealConnectorsTests(unittest.TestCase):
    def test_build_snapshots_uses_real_connectors_for_all_specified_metrics(self):
        cea_power_fixture = {
            'records': [
                {'month': '2026-01', 'generation_bu': 141.3, 'release_date': '2026-02-20'},
                {'month': '2026-02', 'generation_bu': 142.5, 'release_date': '2026-03-20'},
            ]
        }
        cea_plf_fixture = {
            'records': [
                {'month': '2026-01', 'thermal_plf_percent': 68.3, 'release_date': '2026-02-20'},
                {'month': '2026-02', 'thermal_plf_percent': 69.1, 'release_date': '2026-03-20'},
            ]
        }
        oea_fixture = {
            'records': [
                {'month': '2026-01', 'cement_output_mt': 33.0, 'annual_capacity_mt': 420.0, 'release_date': '2026-02-28'},
                {'month': '2026-02', 'cement_output_mt': 34.3, 'annual_capacity_mt': 420.0, 'release_date': '2026-03-28'},
            ]
        }
        jll_fixture = {
            'records': [
                {'quarter': '2025-Q4', 'sales_units': 75100, 'segment': 'top_7_cities', 'release_date': '2026-01-20'},
                {'quarter': '2026-Q1', 'sales_units': 76200, 'segment': 'top_7_cities', 'release_date': '2026-04-20'},
            ]
        }
        mospi_fixture = {
            'records': [
                {'month': '2026-01', 'cpi_index': 188.4, 'headline_inflation_yoy': 4.9, 'release_date': '2026-02-12'},
                {'month': '2026-02', 'cpi_index': 189.0, 'headline_inflation_yoy': 5.0, 'release_date': '2026-03-12'},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paths = {
                'cea_power': tmp / 'cea-power.json',
                'cea_plf': tmp / 'cea-plf.json',
                'oea': tmp / 'oea-cement.json',
                'jll': tmp / 'jll-residential.json',
                'mospi': tmp / 'mospi-cpi.json',
            }
            paths['cea_power'].write_text(json.dumps(cea_power_fixture))
            paths['cea_plf'].write_text(json.dumps(cea_plf_fixture))
            paths['oea'].write_text(json.dumps(oea_fixture))
            paths['jll'].write_text(json.dumps(jll_fixture))
            paths['mospi'].write_text(json.dumps(mospi_fixture))
            output_dir = tmp / 'output'

            connectors = [
                CEAPowerMonthlyConnector(fixture_path=paths['cea_power']),
                CEAPLFConnector(fixture_path=paths['cea_plf']),
                OEACoreIndustriesConnector(fixture_path=paths['oea']),
                JLLResidentialConnector(fixture_path=paths['jll']),
                MoSPICPIConnector(fixture_path=paths['mospi']),
            ]

            build_snapshots(output_dir=output_dir, connectors=connectors)

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}
            series = json.loads((output_dir / 'series.json').read_text())

            expected_metrics = {
                'power_output_total',
                'power_utilization_plf',
                'cement_output',
                'cement_utilization_est',
                'home_sales_jll',
                'cpi_headline',
            }

            self.assertTrue(expected_metrics.issubset(cards.keys()))
            self.assertIn('cement_utilization_est', series)
            self.assertEqual(76200.0, cards['home_sales_jll']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])


if __name__ == '__main__':
    unittest.main()
