import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.mospi_cpi import MoSPICPIConnector


class MoSPICPIConnectorSourceUrlTests(unittest.TestCase):
    def test_fetch_reads_json_payload_from_source_url(self):
        fixture = {
            'records': [
                {
                    'month': '2026-02',
                    'cpi_index': 189.0,
                    'headline_inflation_yoy': 5.0,
                    'release_date': '2026-03-12',
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / 'mospi-cpi.json'
            fixture_path.write_text(json.dumps(fixture))

            connector = MoSPICPIConnector(source_url=fixture_path.as_uri())
            result = connector.fetch()

            self.assertEqual(fixture, result.payload)
            self.assertEqual(fixture_path.as_uri(), result.source_url)


if __name__ == '__main__':
    unittest.main()
