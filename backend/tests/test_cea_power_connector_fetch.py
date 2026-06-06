import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.cea_power import CEAPowerMonthlyConnector


class CEAPowerMonthlyConnectorFetchTests(unittest.TestCase):
    def test_fetch_reads_json_payload_from_fixture_path(self):
        fixture = {
            'records': [
                {
                    'month': '2026-02',
                    'generation_bu': 142.5,
                    'release_date': '2026-03-20',
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / 'cea-power.json'
            fixture_path.write_text(json.dumps(fixture))

            connector = CEAPowerMonthlyConnector(fixture_path=fixture_path)
            result = connector.fetch()

            self.assertEqual('cea_power_monthly', result.dataset_code)
            self.assertEqual('success', result.status)
            self.assertEqual('json', result.payload_type)
            self.assertEqual(fixture, result.payload)
            self.assertEqual(str(fixture_path), result.source_url)


if __name__ == '__main__':
    unittest.main()
