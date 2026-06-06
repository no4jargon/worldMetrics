import json
import tempfile
import unittest
from pathlib import Path

from datetime import date

from app.core.models import CanonicalObservation
from app.pipelines.build_snapshots import build_snapshots, build_snapshots_from_observations


class BuildSnapshotsTests(unittest.TestCase):
    def test_build_snapshots_writes_expected_json_payloads_to_target_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            build_snapshots(output_dir=output_dir)

            overview_path = output_dir / 'overview.json'
            series_path = output_dir / 'series.json'
            release_monitor_path = output_dir / 'release-monitor.json'

            self.assertTrue(overview_path.exists())
            self.assertTrue(series_path.exists())
            self.assertTrue(release_monitor_path.exists())

            overview = json.loads(overview_path.read_text())
            self.assertIn('cards', overview)
            self.assertIn('summary', overview)
            self.assertGreaterEqual(len(overview['cards']), 1)

    def test_build_snapshots_includes_yoy_series_for_power_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            build_snapshots(output_dir=output_dir)

            series = json.loads((output_dir / 'series.json').read_text())
            self.assertIn('power_output_total', series)
            self.assertIn('yoy', series['power_output_total'])
            self.assertGreaterEqual(len(series['power_output_total']['yoy']['points']), 1)

    def test_build_snapshots_summary_mentions_inflation_direction(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            build_snapshots(output_dir=output_dir)

            overview = json.loads((output_dir / 'overview.json').read_text())
            self.assertIn('inflation', overview['summary'].lower())

    def test_vahan_retrieval_skill_is_linked_to_two_and_four_wheeler_metrics(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            observations = [
                CanonicalObservation(
                    metric_code='two_wheeler_sales',
                    period_label='2026-01',
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    value=100.0,
                    unit='units',
                    segment='domestic',
                )
            ]

            build_snapshots_from_observations(observations, output_dir=output_dir)

            series = json.loads((output_dir / 'series.json').read_text())
            self.assertEqual('vahan-dashboard', series['two_wheeler_sales']['level']['retrieval_skill'])
            self.assertEqual('vahan-dashboard', series['four_wheeler_sales']['level']['retrieval_skill'])
            self.assertIn('/skill:vahan-dashboard', series['four_wheeler_sales']['level']['status_note'])


if __name__ == '__main__':
    unittest.main()
