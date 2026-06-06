import json
import tempfile
import unittest
from pathlib import Path

from app.main import main


class MainPersonalTrackerCLITests(unittest.TestCase):
    def test_main_personal_tracker_command_uses_default_source_registry_with_fixture_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            fixtures_dir = tmp / 'fixtures'
            fixtures_dir.mkdir()

            (fixtures_dir / 'jll_residential_sales.json').write_text(
                json.dumps({'records': [{'quarter': '2025-Q3', 'sales_units': 67980, 'segment': 'top_7_cities', 'release_date': '2025-10-28'}]})
            )

            output_dir = tmp / 'output'
            main(['personal-tracker', '--output-dir', str(output_dir), '--fixtures-dir', str(fixtures_dir)])

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}
            self.assertEqual(67980.0, cards['home_sales_jll']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])
            self.assertIsNone(cards['four_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['four_wheeler_sales']['retrieval_skill'])


if __name__ == '__main__':
    unittest.main()
