import tempfile
import unittest
from pathlib import Path

from app.connectors.mospi_cpi import MoSPICPIConnector


class MoSPICPIConnectorLiveTests(unittest.TestCase):
    def test_fetch_discovers_latest_release_and_parses_cpi_from_listing_html(self):
        listing_html = '''
        <html><body>
          <a href="cpi-jan-2026.txt">Press Relase of CPI for Jan26</a>
          <a href="cpi-feb-2026.txt">Press Release of CPI February 2026</a>
        </body></html>
        '''
        february_release = '''
        PRESS RELEASE OF CONSUMER PRICE INDEX ON BASE 2024=100 FOR FEBRUARY, 2026
        Date: 12th March, 2026
        Annexure I
        All India Combined 104.57 3.21
        '''

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'listing.html').write_text(listing_html)
            (tmp / 'cpi-jan-2026.txt').write_text('PRESS RELEASE OF CPI FOR JANUARY, 2026\nDate: 12th February, 2026\nAll India Combined 104.11 4.05')
            (tmp / 'cpi-feb-2026.txt').write_text(february_release)

            connector = MoSPICPIConnector(source_url=(tmp / 'listing.html').as_uri())
            result = connector.fetch()

            self.assertEqual('success', result.status)
            self.assertEqual('2026-02', result.payload['records'][0]['month'])
            self.assertEqual(104.57, result.payload['records'][0]['cpi_index'])
            self.assertEqual(3.21, result.payload['records'][0]['headline_inflation_yoy'])
            self.assertEqual('2026-03-12', result.payload['records'][0]['release_date'])


if __name__ == '__main__':
    unittest.main()
