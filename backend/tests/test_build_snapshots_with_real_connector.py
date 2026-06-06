import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.mospi_cpi import MoSPICPIConnector
from app.connectors.sample_connectors import (
    CEAPLFConnector,
    CEAPowerMonthlyConnector,
    JLLResidentialConnector,
    OEACoreIndustriesConnector,
)
from app.pipelines.build_snapshots import build_snapshots


class BuildSnapshotsWithRealConnectorTests(unittest.TestCase):
    def test_build_snapshots_accepts_connector_overrides(self):
        fixture = {
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
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / 'mospi-cpi.json'
            fixture_path.write_text(json.dumps(fixture))
            output_dir = Path(tmp_dir) / 'output'

            connectors = [
                CEAPowerMonthlyConnector(),
                CEAPLFConnector(),
                OEACoreIndustriesConnector(),
                JLLResidentialConnector(),
                MoSPICPIConnector(fixture_path=fixture_path),
            ]

            build_snapshots(output_dir=output_dir, connectors=connectors)

            series = json.loads((output_dir / 'series.json').read_text())
            points = series['cpi_headline']['level']['points']
            self.assertEqual('2026-02', points[-1]['period'])
            self.assertEqual(5.0, points[-1]['value'])


if __name__ == '__main__':
    unittest.main()
