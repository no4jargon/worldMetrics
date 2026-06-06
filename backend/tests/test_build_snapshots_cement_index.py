import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.oea_cement import OEACoreIndustriesConnector
from app.pipelines.build_snapshots import build_snapshots


class BuildSnapshotsCementIndexTests(unittest.TestCase):
    def test_build_snapshots_includes_cement_output_index_when_public_oea_payload_has_no_tonnage(self):
        fixture = {
            'records': [
                {'month': '2026-01', 'cement_output_index': 228.4, 'release_date': '2026-02-20'},
                {'month': '2026-02', 'cement_output_index': 235.2, 'release_date': '2026-03-20', 'is_provisional': True},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            fixture_path = tmp / 'oea-cement-index.json'
            fixture_path.write_text(json.dumps(fixture))
            output_dir = tmp / 'output'

            build_snapshots(output_dir=output_dir, connectors=[OEACoreIndustriesConnector(fixture_path=fixture_path)])

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}
            series = json.loads((output_dir / 'series.json').read_text())

            self.assertIn('cement_output_index', cards)
            self.assertEqual(235.2, cards['cement_output_index']['latest_value'])
            self.assertIn('cement_output_index', series)


if __name__ == '__main__':
    unittest.main()
