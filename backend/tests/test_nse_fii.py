from datetime import date
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.connectors.nse_fii import (
    NSE_FII_DATA_URL, NSE_FII_HOLIDAYS_URL, fetch_fii_records, parse_groww_fii_payload,
    parse_nse_fii_payload, _missing_sessions,
)


TODAY = date(2026, 10, 28)


def nse_payload(net='4,240.39'):
    return [
        {'category': 'DII', 'date': '27-Oct-2026', 'buyValue': '15702.74', 'sellValue': '16952.77', 'netValue': '-1250.03'},
        {'category': 'FII/FPI', 'date': '27-Oct-2026', 'buyValue': '24,517.65', 'sellValue': '20,277.26', 'netValue': net},
    ]


def groww_payload(day='2026-10-27', *, buy=24517.65, sell=20277.26, net=4240.39):
    return {'errors': None, 'data': {'data': [
        {'date': day, 'fii': {'grossBuy': buy, 'grossSell': sell, 'netBuySell': net},
         'dii': {'grossBuy': 1, 'grossSell': 2, 'netBuySell': -1}},
    ]}}


class NseFiiTests(unittest.TestCase):
    def test_selects_fii_and_preserves_rupees_crore(self):
        records = parse_nse_fii_payload(nse_payload(), today=TODAY)
        self.assertEqual(records, [{'date': '2026-10-27', 'buy': 24517.65, 'sell': 20277.26, 'net': 4240.39}])

    def test_negative_flow_and_parentheses(self):
        payload = [{'category': 'FII/FPI', 'date': '2026-10-26', 'buyValue': 9324.90, 'sellValue': 10787.39, 'netValue': '(1,462.49)'}]
        self.assertEqual(parse_nse_fii_payload(payload, today=TODAY)[0]['net'], -1462.49)

    def test_rejects_missing_fii_instead_of_returning_dii_or_zero(self):
        with self.assertRaisesRegex(ValueError, 'no FII'):
            parse_nse_fii_payload(nse_payload()[:1], today=TODAY)

    def test_rejects_nonfinite_values_and_unbalanced_totals(self):
        for bad_value in ('NaN', 'inf', None, True, 'not a number', '4000'):
            with self.subTest(bad_value=bad_value), self.assertRaises(ValueError):
                parse_nse_fii_payload(nse_payload(bad_value), today=TODAY)

    def test_rejects_future_or_invalid_dates(self):
        for invalid in ('29-Oct-2026', '2026-02-30', ''):
            payload = nse_payload()
            payload[1]['date'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_nse_fii_payload(payload, today=TODAY)

    def test_rejects_negative_gross_values(self):
        payload = nse_payload()
        payload[1].update(buyValue=-5, sellValue=2, netValue=-7)
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            parse_nse_fii_payload(payload, today=TODAY)

    def test_groww_reads_fii_only_and_requires_month_sized_request(self):
        records = parse_groww_fii_payload(groww_payload(), start=date(2026, 10, 1), end=TODAY, today=TODAY)
        self.assertEqual(records[0]['net'], 4240.39)
        with self.assertRaisesRegex(ValueError, 'one calendar month'):
            parse_groww_fii_payload(groww_payload(), start=date(2026, 9, 1), end=TODAY, today=TODAY)

    def test_groww_rejects_out_of_requested_month(self):
        with self.assertRaisesRegex(ValueError, 'outside requested month'):
            parse_groww_fii_payload(groww_payload(), start=date(2026, 9, 1), end=date(2026, 9, 30), today=TODAY)

    def test_merges_verified_history_sorted_and_keeps_month_coverage(self):
        def fetch(url, timeout):
            if url == NSE_FII_DATA_URL:
                return nse_payload()
            if url == NSE_FII_HOLIDAYS_URL:
                return {'CM': [{'tradingDate': '26-Jan-2026'}]}
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query['segment'], ['Cash Market'])
            self.assertEqual(query['period'], ['custom'])
            start = query['startDate'][0]
            if start == '2026-10-01':
                return groww_payload()
            return groww_payload('2026-09-01', buy=100, sell=150, net=-50)
        with patch('app.connectors.nse_fii._fetch_json', side_effect=fetch):
            result = fetch_fii_records(history_months=2, today=TODAY)
        self.assertEqual([r['date'] for r in result['records']], ['2026-09-01', '2026-10-27'])
        self.assertTrue(result['history_verified'])
        self.assertEqual(result['history_complete_months'], [])
        self.assertEqual(result['history_missing_months'], ['2026-09', '2026-10'])
        self.assertEqual(result['history_requested_start'], '2026-09-01')
        self.assertIn('groww.in', result['history_source_url'])
        self.assertIn('NSE, BSE and MSEI', result['scope'])

    def test_missing_session_check_skips_weekends_and_official_holidays(self):
        records = [{'date': '2026-10-01'}, {'date': '2026-10-05'}]
        self.assertEqual(_missing_sessions(records, date(2026, 10, 1), date(2026, 10, 5), {date(2026, 10, 2)}), [])
        self.assertEqual(_missing_sessions(records, date(2026, 10, 1), date(2026, 10, 6), {date(2026, 10, 2)}), ['2026-10-06'])

    def test_unknown_holiday_calendar_year_does_not_claim_full_month(self):
        def fetch(url, timeout):
            if url == NSE_FII_DATA_URL:
                return nse_payload()
            if url == NSE_FII_HOLIDAYS_URL:
                return {'CM': [{'tradingDate': '26-Jan-2025'}]}
            return groww_payload()
        with patch('app.connectors.nse_fii._fetch_json', side_effect=fetch):
            result = fetch_fii_records(history_months=1, today=TODAY)
        self.assertEqual(result['history_complete_months'], [])
        self.assertEqual(result['history_missing_months'], ['2026-10'])

    def test_mismatching_history_is_not_imported(self):
        def fetch(url, timeout):
            return nse_payload() if url == NSE_FII_DATA_URL else groww_payload(buy=10, sell=5, net=5)
        with patch('app.connectors.nse_fii._fetch_json', side_effect=fetch):
            result = fetch_fii_records(history_months=1, today=TODAY)
        self.assertEqual(result['records'][0]['net'], 4240.39)
        self.assertFalse(result['history_verified'])
        self.assertIsNone(result['history_source_url'])
        self.assertIn('not match', result['history_errors'][0])

    def test_failed_history_does_not_discard_latest_official_record(self):
        def fetch(url, timeout):
            if url == NSE_FII_DATA_URL:
                return nse_payload()
            raise TimeoutError('history timed out')
        with patch('app.connectors.nse_fii._fetch_json', side_effect=fetch):
            result = fetch_fii_records(history_months=1, today=TODAY)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['date'], '2026-10-27')
        self.assertIn('history timed out', result['history_errors'][0])

    def test_failed_official_fetch_raises_for_last_good_snapshot_preservation(self):
        with patch('app.connectors.nse_fii._fetch_json', side_effect=TimeoutError('NSE unavailable')):
            with self.assertRaisesRegex(TimeoutError, 'NSE unavailable'):
                fetch_fii_records(today=TODAY)

    def test_history_can_be_disabled_for_latest_only_refresh(self):
        with patch('app.connectors.nse_fii._fetch_json', return_value=nse_payload()) as fetch:
            result = fetch_fii_records(history_months=0, today=TODAY)
        fetch.assert_called_once_with(NSE_FII_DATA_URL, 20)
        self.assertEqual(len(result['records']), 1)

    def test_invalid_history_window_and_timeout(self):
        for months in (-1, 121, True, 1.5):
            with self.subTest(months=months), self.assertRaises(ValueError):
                fetch_fii_records(history_months=months, today=TODAY)
        with self.assertRaises(ValueError):
            fetch_fii_records(timeout=float('nan'), today=TODAY)


if __name__ == '__main__':
    unittest.main()
