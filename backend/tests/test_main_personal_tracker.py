import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.main import run_personal_tracker


class MainPersonalTrackerTests(unittest.TestCase):
    def test_run_personal_tracker_prints_trace_logs_and_builds_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'jll-listing.html').write_text(
                '<a href="jll-q3.html">Premium housing demand witnessed growth in the first nine months of 2025</a>'
            )
            (tmp / 'jll-q3.html').write_text(
                '<time datetime="2025-10-28">28 October 2025</time><h2>Residential Sales (in units)</h2><table><tr><th>Geography</th><th>Q3 2025</th></tr><tr><td>India</td><td>67,980</td></tr></table>'
            )

            output_dir = tmp / 'output'
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                run_personal_tracker(
                    output_dir=output_dir,
                    source_urls={
                        'jll_residential_sales': (tmp / 'jll-listing.html').as_uri(),
                    },
                )

            logs = stdout.getvalue()
            self.assertIn('jll_residential_sales: selected article', logs)

            overview = json.loads((output_dir / 'overview.json').read_text())
            cards = {card['metric_code']: card for card in overview['cards']}
            self.assertEqual(67980.0, cards['home_sales_jll']['latest_value'])
            self.assertIsNone(cards['two_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['two_wheeler_sales']['retrieval_skill'])
            self.assertIsNone(cards['four_wheeler_sales']['latest_value'])
            self.assertEqual('vahan-dashboard', cards['four_wheeler_sales']['retrieval_skill'])


if __name__ == '__main__':
    unittest.main()
