import tempfile
import unittest
from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorSitemapFallbackFromIrrelevantLinksTests(unittest.TestCase):
    def test_fetch_uses_sitemap_when_listing_contains_irrelevant_links_only(self):
        listing_html = '''
        <html><body>
          <a href="/en-in/about-jll">About JLL</a>
          <a href="/en-in/contact">Contact us</a>
        </body></html>
        '''
        q3_html = '''
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
            article_dir = tmp / 'en-in' / 'newsroom'
            article_dir.mkdir(parents=True)
            q3_path = article_dir / 'premium-housing-demand-witnessed-growth-in-the-first-nine-months-of-2025-despite-a-12-year-on-year-decline-in-overall-unit-sales'
            q3_path.write_text(q3_html)
            (tmp / 'sitemap.xml').write_text(f'<urlset><url><loc>{q3_path.as_uri()}</loc></url></urlset>')

            connector = JLLResidentialConnector(
                source_url=(tmp / 'listing.html').as_uri(),
                sitemap_url=(tmp / 'sitemap.xml').as_uri(),
            )
            result = connector.fetch()

            self.assertEqual('2025-Q3', result.payload['records'][0]['quarter'])
            self.assertEqual(67980, result.payload['records'][0]['sales_units'])


if __name__ == '__main__':
    unittest.main()
