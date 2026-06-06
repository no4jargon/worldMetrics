import tempfile
import unittest
from pathlib import Path

from app.connectors.oea_cement import OEACoreIndustriesConnector


class OEACoreIndustriesConnectorLiveTests(unittest.TestCase):
    def test_fetch_discovers_latest_release_and_parses_cement_index(self):
        landing_html = '''
        <html><body>
          <a href="Eight_Infra_Feb_2026.txt">Press Release</a>
          <a href="Core_Industries_2011_12_20260320.xlsx">Download Data</a>
        </body></html>
        '''
        release_text = '''
        INDEX OF EIGHT CORE INDUSTRIES FOR FEBRUARY, 2026
        March 20, 2026
        January 2026 is final and February 2026 is provisional.
        Annex II Performance of Eight Core Industries Monthly Index & Growth Rate
        Month Cement
        Feb-26* 235.2
        '''

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'landing.html').write_text(landing_html)
            (tmp / 'Eight_Infra_Feb_2026.txt').write_text(release_text)
            (tmp / 'Core_Industries_2011_12_20260320.xlsx').write_text('placeholder')

            connector = OEACoreIndustriesConnector(source_url=(tmp / 'landing.html').as_uri())
            result = connector.fetch()

            self.assertEqual('2026-02', result.payload['records'][0]['month'])
            self.assertEqual(235.2, result.payload['records'][0]['cement_output_index'])
            self.assertEqual('2026-03-20', result.payload['records'][0]['release_date'])
            self.assertTrue(result.payload['records'][0]['is_provisional'])


if __name__ == '__main__':
    unittest.main()
