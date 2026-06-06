import tempfile
import unittest
from pathlib import Path

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorSitemapTests(unittest.TestCase):
    def test_fetch_uses_sitemap_when_newsroom_listing_has_no_article_links(self):
        listing_html = '<html><body><h1>Newsroom</h1></body></html>'
        q1_html = '''
        <html><body>
          <div>{&quot;datePublished&quot;:&quot;09 April 2025&quot;}</div>
          <table>
            <tr><th>Residential Sales (in units)</th><th>Q1 2025</th></tr>
            <tr><td>India</td><td>65,246</td></tr>
          </table>
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
            q1_path = article_dir / 'luxury-home-demand-cushions-market-65250-units-sold-in-q12025'
            q3_path = article_dir / 'premium-housing-demand-witnessed-growth-in-the-first-nine-months-of-2025-despite-a-12-year-on-year-decline-in-overall-unit-sales'
            q1_path.write_text(q1_html)
            q3_path.write_text(q3_html)
            sitemap_xml = f'''
            <urlset>
              <url><loc>{q1_path.as_uri()}</loc></url>
              <url><loc>{q3_path.as_uri()}</loc></url>
            </urlset>
            '''
            (tmp / 'sitemap.xml').write_text(sitemap_xml)

            connector = JLLResidentialConnector(
                source_url=(tmp / 'listing.html').as_uri(),
                sitemap_url=(tmp / 'sitemap.xml').as_uri(),
            )
            result = connector.fetch()

            self.assertEqual('2025-Q3', result.payload['records'][0]['quarter'])
            self.assertEqual(67980, result.payload['records'][0]['sales_units'])
            self.assertEqual('2025-10-28', result.payload['records'][0]['release_date'])


if __name__ == '__main__':
    unittest.main()
