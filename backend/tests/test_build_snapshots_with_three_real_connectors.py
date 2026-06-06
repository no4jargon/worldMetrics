import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.cea_power import CEAPowerMonthlyConnector
from app.connectors.mospi_cpi import MoSPICPIConnector
from app.connectors.sample_connectors import (
    CEAPLFConnector,
    JLLResidentialConnector,
    OEACoreIndustriesConnector,
)
from app.pipelines.build_snapshots import build_snapshots


class BuildSnapshotsWithThreeRealConnectorsTests(unittest.TestCase):
    def test_build_snapshots_uses_real_cea_and_mospi_connectors(self):
        cea_fixture = {
            'records': [
                {'month': '2026-01', 'generation_bu': 141.3, 'release_date': '2026-02-20'},
                {'month': '2026-02', 'generation_bu': 142.5, 'release_date': '2026-03-20'},
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
            cea_path = tmp / 'cea-power.json'
            mospi_path = tmp / 'mospi-cpi.json'
            cea_path.write_text(json.dumps(cea_fixture))
            mospi_path.write_text(json.dumps(mospi_fixture))
            output_dir = tmp / 'output'

            connectors = [
                CEAPowerMonthlyConnector(fixture_path=cea_path),
                CEAPLFConnector(),
                OEACoreIndustriesConnector(),
                JLLResidentialConnector(),
                MoSPICPIConnector(fixture_path=mospi_path),
            ]

            build_snapshots(output_dir=output_dir, connectors=connectors)

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}

            self.assertEqual(142500.0, cards['power_output_total']['latest_value'])
            self.assertEqual(5.0, cards['cpi_headline']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])


if __name__ == '__main__':
    unittest.main()
