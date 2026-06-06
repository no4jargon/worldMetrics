import json
import tempfile
import unittest
from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorFetchTests(unittest.TestCase):
    def test_fetch_reads_json_payload_from_fixture_path(self):
        fixture = {
            'records': [
                {'quarter': '2026-Q1', 'sales_units': 76200, 'segment': 'top_7_cities', 'release_date': '2026-04-20'}
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / 'jll-residential.json'
            fixture_path.write_text(json.dumps(fixture))

            connector = JLLResidentialConnector(fixture_path=fixture_path)
            result = connector.fetch()

            self.assertEqual('jll_residential_sales', result.dataset_code)
            self.assertEqual('success', result.status)
            self.assertEqual('json', result.payload_type)
            self.assertEqual(fixture, result.payload)
            self.assertEqual(str(fixture_path), result.source_url)


if __name__ == '__main__':
    unittest.main()
