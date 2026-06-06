import unittest
from pathlib import Path

from app.connectors.npp_power import NPPMonthlyGenerationConnector, _first_exact_actual_value_for_row
from app.core.models import FetchResult


class NPPMonthlyGenerationConnectorTests(unittest.TestCase):
    def test_parse_all_india_xls_reads_monthly_actual_plf_column(self):
        artifact_path = Path(__file__).resolve().parents[2] / 'artifacts' / 'npp-power' / 'npp-all-india-2026-04.xls'
        if not artifact_path.exists():
            self.skipTest('NPP XLS artifact not available')

        connector = NPPMonthlyGenerationConnector()
        record = connector._parse_all_india_xls(artifact_path.read_bytes(), '2026-04')

        self.assertAlmostEqual(137001.32, record['generation_gwh'], places=2)
        self.assertAlmostEqual(72.16664649624337, record['thermal_plf_percent'], places=6)
        self.assertEqual('2026-05-26', record['release_date'])

    def test_generation_value_uses_first_column_with_exact_actual_cell(self):
        rows = [
            ['', '', '', 'GENERATION (GWH)', '', '', 'PLANT LOAD FACTOR (%)'],
            ['', 'PROGRAM', 'Actual Same Month', 'ACTUAL', 'PROGRAM', 'ACTUAL', 'ACTUAL'],
            ['THERMAL', 20.0, 19.0, 21.0, 70.0, 71.0, 72.0],
            ['TOTAL', 100.0, 99.0, 101.0, '', '', ''],
        ]

        value = _first_exact_actual_value_for_row(rows, 3, '2026-04')

        self.assertEqual(101.0, value)

    def test_parse_converts_npp_json_payload_to_power_observations(self):
        connector = NPPMonthlyGenerationConnector()
        raw = FetchResult(
            dataset_code='npp_monthly_generation',
            status='success',
            parser_version='test',
            source_url='https://example.test/npp',
            payload_type='json',
            payload={
                'records': [
                    {
                        'month': '2026-04',
                        'generation_gwh': 137001.32,
                        'thermal_plf_percent': 72.16664649624337,
                        'release_date': '2026-05-17',
                    }
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(['power_output_total', 'power_utilization_plf'], [obs.metric_code for obs in observations])
        self.assertEqual(137001.32, observations[0].value)
        self.assertEqual('GWh', observations[0].unit)
        self.assertEqual(72.16664649624337, observations[1].value)
        self.assertEqual('percent', observations[1].unit)


if __name__ == '__main__':
    unittest.main()
