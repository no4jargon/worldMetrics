import tempfile
import unittest
from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorLiveTests(unittest.TestCase):
    def test_fetch_discovers_latest_newsroom_release_and_parses_india_sales_row(self):
        listing_html = '''
        <html><body>
          <a href="q1-2025.html">Luxury home demand cushions market 65250 units sold in Q12025</a>
          <a href="q3-2025.html">Premium housing demand witnessed growth in the first nine months of 2025 despite a 12 year on year decline in overall unit sales</a>
        </body></html>
        '''
        q3_html = '''
        <html><body>
          <time datetime="2025-10-28">28 October 2025</time>
          <h1>Premium housing demand witnessed growth in the first nine months of 2025</h1>
          <h2>Residential Sales (in units)</h2>
          <table>
            <tr><th>Geography</th><th>Q3 2025</th></tr>
            <tr><td>India</td><td>67,980</td></tr>
          </table>
        </body></html>
        '''

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'listing.html').write_text(listing_html)
            (tmp / 'q1-2025.html').write_text('<html><body><time datetime="2025-04-09">09 April 2025</time><h2>Residential Sales (in units)</h2><table><tr><td>India</td><td>65,246</td></tr></table></body></html>')
            (tmp / 'q3-2025.html').write_text(q3_html)

            connector = JLLResidentialConnector(source_url=(tmp / 'listing.html').as_uri())
            result = connector.fetch()

            self.assertEqual('2025-Q3', result.payload['records'][0]['quarter'])
            self.assertEqual(67980, result.payload['records'][0]['sales_units'])
            self.assertEqual('top_7_cities', result.payload['records'][0]['segment'])
            self.assertEqual('2025-10-28', result.payload['records'][0]['release_date'])


if __name__ == '__main__':
    unittest.main()
