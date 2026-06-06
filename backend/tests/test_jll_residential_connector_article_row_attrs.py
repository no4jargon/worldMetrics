import unittest

from app.connectors.jll_residential import JLLResidentialConnector


class JLLResidentialConnectorArticleRowAttrsTests(unittest.TestCase):
    def test_parse_live_record_reads_india_row_when_table_row_has_attributes(self):
        article_html = '''
        <html><body>
          <div>{&quot;datePublished&quot;:&quot;28 October 2025&quot;}</div>
          <table>
            <tr><th>Residential Sales (in units)</th><th>Q3 2025</th></tr>
            <tr style="font-weight: bold; background-color: #f3f3f3;">
              <td>India</td>
              <td>67,980</td>
              <td>75,016</td>
            </tr>
          </table>
        </body></html>
        '''
        connector = JLLResidentialConnector(source_url='https://www.jll.com/en-in/newsroom')

        record = connector._parse_live_record(article_html)

        self.assertEqual('2025-Q3', record['quarter'])
        self.assertEqual(67980, record['sales_units'])
        self.assertEqual('2025-10-28', record['release_date'])


if __name__ == '__main__':
    unittest.main()
