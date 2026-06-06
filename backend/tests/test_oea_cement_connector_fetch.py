import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.oea_cement import OEACoreIndustriesConnector


class OEACoreIndustriesConnectorFetchTests(unittest.TestCase):
    def test_fetch_reads_json_payload_from_fixture_path(self):
        fixture = {
            'records': [
                {
                    'month': '2026-02',
                    'cement_output_mt': 34.3,
                    'annual_capacity_mt': 420.0,
                    'release_date': '2026-03-28',
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / 'oea-cement.json'
            fixture_path.write_text(json.dumps(fixture))

            connector = OEACoreIndustriesConnector(fixture_path=fixture_path)
            result = connector.fetch()

            self.assertEqual('oea_core_industries', result.dataset_code)
            self.assertEqual('success', result.status)
            self.assertEqual('json', result.payload_type)
            self.assertEqual(fixture, result.payload)
            self.assertEqual(str(fixture_path), result.source_url)


if __name__ == '__main__':
    unittest.main()
