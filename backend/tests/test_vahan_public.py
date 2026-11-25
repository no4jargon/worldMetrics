import json
import unittest
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.connectors.vahan_public import (
    API_URL, CATEGORY_GROUPS, fetch_vahan_public, parse_vahan_public, public_request_url,
)


# Shape and sample counts observed in the official portal's public comparison
# endpoint on 2026-11-25. Arrays are ordered Jan–Dec by its published JavaScript.
TWO_WHEELERS = {
    '2026': [1925351, 1774397, 2028493, 1991825, 1862957, 1844025, 1832176, 1729048, 1804000, 2332786, 2734615],
    '2025': [1593124, 1413324, 1577270, 1752023, 1717174, 1509244, 1418778, 1433222, 1346162, 3240674, 2646012, 1395550],
    '2024': [1527091, 1509824, 1598852, 1702587, 1599363, 1437434, 1516348, 1398296, 1262857, 2136737, 2714990, 1259019],
}
FOUR_WHEELERS = {
    '2026': [630404, 473794, 518267, 472432, 467434, 489654, 508416, 467097, 481950, 561085, 395835],
    '2025': [558880, 366482, 419372, 411392, 372716, 371864, 406733, 402015, 366509, 627928, 524291, 492200],
    '2024': [484114, 404915, 394896, 389517, 369511, 350967, 396383, 372292, 335090, 551314, 408504, 392979],
}
TODAY = date(2026, 11, 25)


class Response:
    status = 200

    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self, size):
        return self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class VahanPublicTests(unittest.TestCase):
    def test_observed_shape_returns_only_requested_completed_months(self):
        rows = parse_vahan_public(TWO_WHEELERS, 'two_wheeler_sales', [2025, 2026], TODAY)
        self.assertEqual(22, len(rows))
        self.assertEqual('2025-01', rows[0].period_label)
        self.assertEqual('2026-10', rows[-1].period_label)
        self.assertEqual(2332786, rows[-1].value)
        self.assertEqual('domestic', rows[-1].segment)
        self.assertEqual('units', rows[-1].unit)
        self.assertEqual(date(2026, 10, 31), rows[-1].period_end)
        self.assertTrue(all(row.is_preliminary for row in rows))
        self.assertTrue(all(row.source_url.startswith(API_URL) for row in rows))
        self.assertEqual('2026-01', parse_vahan_public(TWO_WHEELERS, 'two_wheeler_sales', [2026], TODAY)[0].period_label)

    def test_current_and_future_month_slots_are_excluded(self):
        payload = {'2026': list(range(1, 13)), '2027': [10] * 12}
        rows = parse_vahan_public(payload, 'four_wheeler_sales', [2026], date(2026, 3, 1))
        self.assertEqual(['2026-01', '2026-02'], [r.period_label for r in rows])
        self.assertEqual([], parse_vahan_public(payload, 'four_wheeler_sales', [2026], date(2026, 1, 1)))

    def test_null_and_trailing_missing_months_do_not_become_zeros(self):
        rows = parse_vahan_public({'2026': [0, None, 123]}, 'two_wheeler_sales', [2026], TODAY)
        self.assertEqual([('2026-01', 0), ('2026-03', 123)], [(r.period_label, r.value) for r in rows])

    def test_missing_requested_year_fails_without_substituting_cached_period(self):
        with self.assertRaisesRegex(ValueError, 'omitted requested years'):
            parse_vahan_public({'2025': [1] * 12}, 'two_wheeler_sales', [2026], TODAY)

    def test_invalid_response_shapes_counts_and_years_fail(self):
        bad_payloads = [[], {}, {'unknown': [1]}, {'2026': '123'}, {'2026': [1] * 13}]
        bad_payloads.extend({'2026': [value]} for value in [-1, 1.5, True, '123', float('nan'), float('inf')])
        for payload in bad_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_vahan_public(payload, 'two_wheeler_sales', [2026], TODAY)
        for years in [[], [True], [2027], ['2026']]:
            with self.subTest(years=years), self.assertRaises(ValueError):
                parse_vahan_public(TWO_WHEELERS, 'two_wheeler_sales', years, TODAY)

    def test_request_preserves_exact_legacy_category_union_and_national_filters(self):
        for metric, categories in CATEGORY_GROUPS.items():
            query = parse_qs(urlparse(public_request_url(metric, [2025, 2026])).query, keep_blank_values=True)
            self.assertEqual([','.join(categories)], query['vehicleSubCategories'])
            self.assertEqual([''], query['stateCode'])
            self.assertEqual(['0'], query['rtoCode'])
            self.assertEqual(['0'], query['timePeriod'])
            self.assertEqual(['2025'], query['fromYear'])
            self.assertEqual(['2026'], query['toYear'])
            self.assertEqual([''], query['vehicleCategoryGroup'])

    @patch('app.connectors.vahan_public._india_today', return_value=TODAY)
    @patch('app.connectors.vahan_public.urlopen')
    def test_fetch_validates_both_categories_before_returning_merge_batch(self, open_mock, _today):
        open_mock.side_effect = [Response(TWO_WHEELERS), Response(FOUR_WHEELERS)]
        rows = fetch_vahan_public()
        self.assertEqual(44, len(rows))
        self.assertEqual(561085, rows[-1].value)
        self.assertEqual('four_wheeler_sales', rows[-1].metric_code)
        self.assertEqual(2, open_mock.call_count)
        self.assertTrue(all(row.period_label <= '2026-10' for row in rows))
        # Revisions are keyed by the caller's cache merge; the collector never
        # deletes cached older years or pads omitted trailing months.
        cached = {('two_wheeler_sales', '2024-12'): 1259019}
        cached.update({(row.metric_code, row.period_label): row.value for row in rows})
        self.assertEqual(1259019, cached[('two_wheeler_sales', '2024-12')])
        self.assertEqual(2332786, cached[('two_wheeler_sales', '2026-10')])
        open_mock.side_effect = [Response(TWO_WHEELERS), Response({'2025': [1] * 12})]
        with self.assertRaises(ValueError):
            fetch_vahan_public()
        open_mock.side_effect = [Response(TWO_WHEELERS), Response({'2025': [None] * 12, '2026': []})]
        with self.assertRaisesRegex(ValueError, 'no completed months for four_wheeler_sales'):
            fetch_vahan_public()


if __name__ == '__main__':
    unittest.main()
