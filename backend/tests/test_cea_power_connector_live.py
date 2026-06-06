import tempfile
import unittest
from pathlib import Path

from app.connectors.cea_power import CEAPowerMonthlyConnector


class CEAPowerMonthlyConnectorLiveTests(unittest.TestCase):
    def test_fetch_discovers_latest_executive_summary_and_parses_generation(self):
        listing_html = '''
        <html><body>
          <div><span>20-02-2026</span><a href="Executive_Summary_January_2026_Actual.txt">Executive Summary, January 2026</a></div>
          <div><span>20-03-2026</span><a href="Executive_Summary_February_2026_Actual.txt">Executive Summary, February 2026</a></div>
        </body></html>
        '''
        february_text = '''
        Executive Summary Report February 2026
        1B. Electricity Generation for Feb-2026 (BU)
        All India 142.5
        '''

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'listing.html').write_text(listing_html)
            (tmp / 'Executive_Summary_January_2026_Actual.txt').write_text('Executive Summary Report January 2026\n1B. Electricity Generation for Jan-2026 (BU)\nAll India 141.3')
            (tmp / 'Executive_Summary_February_2026_Actual.txt').write_text(february_text)

            connector = CEAPowerMonthlyConnector(source_url=(tmp / 'listing.html').as_uri())
            result = connector.fetch()

            self.assertEqual('2026-02', result.payload['records'][0]['month'])
            self.assertEqual(142.5, result.payload['records'][0]['generation_bu'])
            self.assertEqual('2026-03-20', result.payload['records'][0]['release_date'])


if __name__ == '__main__':
    unittest.main()
