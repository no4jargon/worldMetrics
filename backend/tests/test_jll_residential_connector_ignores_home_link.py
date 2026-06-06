import tempfile
import unittest
from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorIgnoresHomeLinkTests(unittest.TestCase):
    def test_fetch_does_not_treat_home_breadcrumb_as_residential_article(self):
        listing_html = '''
        <html><body>
          <a href="/en-in/">Home</a>
          <a href="premium-housing-demand">Premium housing demand witnessed growth in the first nine months of 2025 despite a decline in sales</a>
        </body></html>
        '''
        article_html = '''
        <html><body>
          <div>{&quot;datePublished&quot;:&quot;28 October 2025&quot;}</div>
          <table>
            <tr><th>Residential Sales (in units)</th><th>Q3 2025</th></tr>
            <tr><td>India</td><td>67,980</td></tr>
          </table>
        </body></html>
        '''

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / 'listing.html').write_text(listing_html)
            (tmp / 'premium-housing-demand').write_text(article_html)

            connector = JLLResidentialConnector(source_url=(tmp / 'listing.html').as_uri())
            result = connector.fetch()

            self.assertEqual('2025-Q3', result.payload['records'][0]['quarter'])
            self.assertEqual(67980, result.payload['records'][0]['sales_units'])


if __name__ == '__main__':
    unittest.main()
