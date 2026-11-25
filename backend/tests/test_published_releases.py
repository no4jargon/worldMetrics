import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError

from app.connectors.icra_cement import ICRAReport
from app.connectors.published_releases import (
    EQUITY_SITEMAP, JLL_SITEMAP, fetch_cement, fetch_cpi, fetch_jll,
    parse_cement, parse_cpi, parse_jll,
    _ICRAListing,
)

CPI = '''PRESS RELEASE OF CONSUMER PRICE INDEX ON BASE 2024=100 FOR OCTOBER, 2026
Posted On: 12 NOV 2026 4:00PM by PIB Delhi
Year-on-year inflation rate based on All India Consumer Price Index (CPI).
September, 2026 (Final) October, 2026 (Provisional)
Rural Urban Combined Rural Urban Combined
Inflation (%) CPI (General) 6.08 4.88 5.54 6.63 5.41 6.09 CFPI 8.06 7.18 7.74 9.09 8.68 8.94
Index CPI (General) 110.11 108.71 109.49 110.73 109.22 110.05 CFPI 112.21 112.10 112.17 113.22 113.24 113.23'''
JLL = '''<html><meta property="article:published_time" content="2026-11-08T19:07:40+05:30">
<p>Home sales across seven major cities according to JLL REIS.</p><table>
<tr><td>Residential Sales (in units)</td><td>Q3 2026 Sales (No of units)</td><td>Q3 2025 sales (No of units)</td><td>Jan-Sep 2026 sales</td></tr>
<tr><td>Bengaluru</td><td>19,208</td><td>15,624</td><td>54,225</td></tr>
<tr><td>India</td><td>76,181</td><td>67,974</td><td>2,14,562</td><td>6%</td></tr></table>
<p>Residential Launches (in units) Q3 2026 Launches Q3 2025 Launches India 92,000 89,000</p></html>'''


def sitemap(*rows):
    return ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(
        '<url><loc>' + url + '</loc><lastmod>' + modified + '</lastmod></url>' for modified, url in rows
    ) + '</urlset>').encode()


class PublishedReleaseTests(unittest.TestCase):
    def test_cpi_reads_combined_column_not_rural_or_food_and_emits_prior_final(self):
        obs = parse_cpi(CPI, 'https://www.pib.gov.in/release')
        values = {(o.metric_code, o.period_label): o for o in obs}
        self.assertEqual(4, len(obs))
        self.assertEqual(5.54, values['cpi_headline', '2026-09'].value)
        self.assertEqual(6.09, values['cpi_headline', '2026-10'].value)
        self.assertEqual(110.05, values['cpi_index', '2026-10'].value)
        self.assertFalse(values['cpi_index', '2026-09'].is_preliminary)
        self.assertTrue(values['cpi_index', '2026-10'].is_preliminary)
        self.assertEqual(date(2026, 11, 12), obs[0].source_release_date)

    def test_cpi_rejects_ambiguous_or_changed_header(self):
        with self.assertRaisesRegex(ValueError, 'columns'):
            parse_cpi(CPI.replace('September, 2026 (Final)', 'August, 2026 (Final)'), 'https://example.test')
        with self.assertRaisesRegex(ValueError, 'six-column'):
            parse_cpi(CPI.replace('6.08 4.88 5.54', '6.08 4.88'), 'https://example.test')

    def test_cpi_discovers_newest_dated_pdf(self):
        calls = []
        def reader(url):
            calls.append(url)
            return CPI.encode()
        listing = {'data': [
            {'title': 'Press release CPI September 2026', 'published_year': '2026-10-12', 'file_one': {'path': 'older.pdf'}},
            {'title': 'Press release CPI October 2026', 'published_year': '2026-11-12', 'file_one': {'path': 'newest.pdf'}},
        ]}
        obs = fetch_cpi(reader=reader, listing_loader=lambda: listing)
        self.assertEqual(['https://www.mospi.gov.in/newest.pdf'], calls)
        self.assertEqual('2026-10', max(o.period_label for o in obs))

    def test_cement_reads_both_explicit_month_word_orders(self):
        for text in [
            'Cement production volumes increased by 12.5% YoY in August 2026 to 39.7 million metric tonnes (MT) and by 10.3% in 5M FY2027 to 212.1 million MT.',
            'Cement production volumes increased by 9.8% year-on-year (YoY) to 39.2 million metric tonnes (MT) in September 2026 and by 10.1% to 251.1 million MT in H1 FY2027.',
        ]:
            obs = parse_cement(text, 'https://www.icra.in/Research/report', date(2026, 10, 28))
            self.assertEqual(1, len(obs))
            self.assertIn(obs[0].value, [39.2, 39.7])
            self.assertEqual('MT', obs[0].unit)

    def test_cement_does_not_infer_month_from_cumulative_totals(self):
        with self.assertRaisesRegex(ValueError, 'explicit'):
            parse_cement('Cement production volumes rose to 251.1 million MT in H1 FY2027. September 2026 volumes rose 9.8%.', 'https://www.icra.in/report', date(2026, 10, 28))

    def test_cement_refuses_conflicting_explicit_levels_for_same_release(self):
        text = 'Cement production volumes in August 2026 to 39.7 million tonnes. Cement production volumes in August 2026 to 40.2 million tonnes.'
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            parse_cement(text, 'https://www.icra.in/report', date(2026, 9, 30))

    def test_cement_listing_404_uses_fresh_current_www_browser_listing(self):
        attempts = []
        report = ICRAReport('99999', 'Cement volumes October 2026',
                            'https://www.icra.in/Research/ViewResearchReport/99999', '24 Nov 2026', 1)
        class Listing:
            def __init__(self, **kwargs):
                self.url = kwargs['source_url']
            def _fetch_report_listing(self):
                attempts.append(self.url)
                raise HTTPError(self.url, 404, 'Not Found', {}, None)
        with patch('app.connectors.published_releases._ICRAListing', Listing), patch(
                'app.connectors.published_releases._cement_reports_browser', return_value=[report]) as browser:
            obs = fetch_cement(reader=lambda url: b'Cement production volumes in October 2026 to 40.5 million metric tonnes.')
        self.assertEqual(['https://www.icra.in/Research/ResearchDetails/1'], attempts)
        browser.assert_called_once()
        self.assertEqual('2026-10', obs[0].period_label)
        self.assertEqual(report.report_url, obs[0].source_url)

    def test_cement_report_404_tries_same_discovered_report_on_official_alternate(self):
        report = ICRAReport('99999', 'October cement',
                            'https://www.icra.in/Research/ViewResearchReport/99999', '24 Nov 2026', 1)
        def reader(url):
            if url.startswith('https://www.'):
                raise HTTPError(url, 404, 'Not Found', {}, None)
            return b'Cement production volumes to 40.5 million tonnes in October 2026.'
        obs = fetch_cement(reader=reader, reports_loader=lambda: [report])
        self.assertEqual('https://beta.icra.in/Research/ViewResearchReport/99999', obs[0].source_url)

    def test_icra_alternate_ajax_keeps_cookie_and_token_on_its_own_origin(self):
        seen = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, _limit): return b'<table>fresh listing</table>'
        class Opener:
            def open(self, request, timeout):
                seen.append(request)
                self.assert_timeout = timeout
                return Response()
        listing = _ICRAListing(source_url='https://beta.icra.in/Research/ResearchDetails/1')
        listing._post_listing_page(Opener(), 'session-csrf-value', 1)
        self.assertTrue(seen[0].full_url.startswith('https://beta.icra.in/Research/GetSectorResearchReportDetails'))
        self.assertEqual('https://beta.icra.in', seen[0].get_header('Origin'))
        self.assertIn(b'__RequestVerificationToken=session-csrf-value', seen[0].data)

    def test_icra_current_www_failures_keep_primary_error_before_browser_error(self):
        with patch.object(_ICRAListing, '_fetch_report_listing', side_effect=ValueError(
                'ICRA GET https://www.icra.in/Research/ResearchDetails/1: HTTP 404')), patch(
                'app.connectors.published_releases._cement_reports_browser', side_effect=ValueError('browser current listing also unavailable')):
            with self.assertRaisesRegex(ValueError, r'WWW listing unavailable: ICRA GET https://www.icra.in/Research/ResearchDetails/1: HTTP 404; browser'):
                fetch_cement(reader=lambda url: self.fail('Must not read reports without live discovery'))

    def test_icra_empty_current_listing_does_not_use_stale_beta_listing(self):
        with patch.object(_ICRAListing, '_fetch_report_listing', return_value=([], [])) as http, patch(
                'app.connectors.published_releases._cement_reports_browser', side_effect=ValueError('No current reports')):
            with self.assertRaisesRegex(ValueError, 'WWW HTTP listing returned no reports'):
                fetch_cement(reader=lambda url: self.fail('No cached report-ID fallback is allowed'))
        http.assert_called_once()

    def test_jll_uses_quarter_sales_table_not_ytd_or_launches(self):
        obs = parse_jll(JLL, 'https://www.equitybulls.com/news/report')
        self.assertEqual({'2026-Q3': 76181, '2025-Q3': 67974}, {o.period_label: o.value for o in obs})
        self.assertEqual(date(2026, 11, 8), obs[0].source_release_date)
        self.assertTrue(all('EquityBulls' in o.notes for o in obs))

    def test_jll_requires_attribution_and_national_scope_for_prose(self):
        with self.assertRaisesRegex(ValueError, 'attribute'):
            parse_jll(JLL.replace('JLL', 'Other'), 'https://example.test')
        text = '<meta property="article:published_time" content="2026-06-15">JLL Residential sales rose 8% to 70,631 units in Q1 2026.'
        with self.assertRaisesRegex(ValueError, 'scope'):
            parse_jll(text, 'https://www.jll.com/insights/report')
        obs = parse_jll(text + ' Across India top seven cities.', 'https://www.jll.com/insights/report')
        self.assertEqual(70631, obs[0].value)

    def test_jll_discovers_newest_sitemap_shards_and_dedupes_revisions(self):
        source = 'https://www.equitybulls.com/news/378755/indias-housing-market'
        pages = {
            JLL_SITEMAP: sitemap(),
            EQUITY_SITEMAP: sitemap(('', 'https://www.equitybulls.com/sitemap-news-1.xml'), ('', 'https://www.equitybulls.com/sitemap-news-38.xml')),
            'https://www.equitybulls.com/sitemap-news-38.xml': sitemap(('2026-11-08', source)),
            'https://www.equitybulls.com/sitemap-news-1.xml': sitemap(),
            source: JLL.encode(),
        }
        obs = fetch_jll(reader=pages.__getitem__)
        self.assertEqual(76181, next(o.value for o in obs if o.period_label == '2026-Q3'))

    def test_discovery_failures_raise_instead_of_emitting_guesses(self):
        def fail(_url):
            raise ValueError('Source unavailable')
        with self.assertRaisesRegex(ValueError, 'No national JLL'):
            fetch_jll(reader=fail)
        with self.assertRaisesRegex(ValueError, 'no reports'):
            fetch_cement(reader=fail, reports_loader=lambda: [])


if __name__ == '__main__':
    unittest.main()
