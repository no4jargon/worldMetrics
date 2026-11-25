import json
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.core.models import CanonicalObservation, FetchResult
from app.pipelines.build_snapshots import build_snapshots_from_observations
from app.pipelines.cloud_refresh import (
    FII_DATASET, SourceDeadline, _connector_runner, _recent_months, load_history, main, refresh_cloud_data,
)


NOW = datetime(2026, 11, 25, 14, 30, tzinfo=timezone.utc)
OLD_SUCCESS = '2026-11-18T11:34:18+00:00'
SOURCE_URL = 'https://example.gov.in/published-report'


def observation(metric, period, value, *, segment=None, release=None):
    from app.pipelines.cloud_refresh import _bounds
    start, end = _bounds(period)
    unit = 'percent' if metric == 'cpi_headline' else 'GWh' if metric == 'power_output_total' else 'units'
    return CanonicalObservation(metric, period, start, end, value, unit,
                                segment=segment, source_release_date=release, source_url=SOURCE_URL)


def failed():
    raise RuntimeError('Source unavailable')


def good_fii(**_kwargs):
    return {'refresh_status': 'success', 'records': [
        {'date': '2026-11-24', 'buy': 8.0, 'sell': 6.0, 'net': 2.0},
    ], 'source_url': 'https://www.nseindia.com/reports/fii-dii'}


def bad_fii(**_kwargs):
    raise RuntimeError('FII source unavailable')


class CloudRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def seed(self, observations, *, canonical=False):
        build_snapshots_from_observations(observations, output_dir=self.data)
        if canonical:
            self.write('canonical-observations.json', [obs.to_dict() for obs in observations])
        self.write('fii-flows.json', {
            'records': [{'date': '2026-11-17', 'buy': 10.0, 'sell': 7.0, 'net': 3.0}],
            'last_success_at': OLD_SUCCESS, 'last_checked_at': OLD_SUCCESS,
            'refresh_status': 'success', 'status': 'available', 'error': None,
        })
        self.write('snapshot.json', {'last_success_at': OLD_SUCCESS, 'sources': {
            'npp_monthly_generation': {'status': 'success', 'last_success_at': OLD_SUCCESS},
            FII_DATASET: {'status': 'success', 'last_success_at': OLD_SUCCESS},
        }})

    def write(self, name, payload):
        (self.data / name).write_text(json.dumps(payload))

    def read(self, name):
        return json.loads((self.data / name).read_text())

    def test_narrow_refresh_revises_existing_period_and_preserves_older_history(self):
        self.seed([
            observation('two_wheeler_sales', '2025-01', 100, segment='domestic'),
            observation('two_wheeler_sales', '2026-10', 200, segment='domestic'),
        ], canonical=True)
        result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
            'vahan_vehicle_registrations': lambda: [observation('two_wheeler_sales', '2026-10', 222)],
        })
        self.assertEqual('success', result['update_status'])
        history = self.read('canonical-observations.json')
        self.assertEqual([100, 222], [item['value'] for item in history])
        self.assertEqual(['domestic', 'domestic'], [item['segment'] for item in history])
        self.assertEqual(['2026-11-17', '2026-11-24'], [item['date'] for item in result['fii_flows']['records']])
        self.assertEqual('2026-10', result['sources']['vahan_vehicle_registrations']['last_successful_period'])
        # The next run loads canonical history and performs the same idempotent upsert.
        second = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
            'vahan_vehicle_registrations': lambda: [observation('two_wheeler_sales', '2026-10', 222)],
        })
        self.assertEqual(result['series'], second['series'])
        self.assertEqual(2, len(self.read('canonical-observations.json')))

    def test_partial_failure_retains_figures_and_last_success_for_failed_source(self):
        self.seed([observation('power_output_total', '2026-09', 143562.33)])
        result = refresh_cloud_data(self.data, now=NOW, fii_refresher=bad_fii, collectors={
            'npp_monthly_generation': failed,
            'mospi_cpi': lambda: [observation('cpi_headline', '2026-10', 6.09, release=date(2026, 11, 12))],
        })
        self.assertEqual('partial', result['update_status'])
        self.assertEqual(OLD_SUCCESS, result['sources']['npp_monthly_generation']['last_success_at'])
        self.assertEqual(NOW.isoformat(), result['sources']['mospi_cpi']['last_success_at'])
        self.assertEqual(NOW.isoformat(), result['last_success_at'])
        self.assertEqual(OLD_SUCCESS, result['sources'][FII_DATASET]['last_success_at'])
        self.assertEqual(143562.33, result['series']['power_output_total']['level']['points'][0]['value'])
        power = next(card for card in result['overview']['cards'] if card['metric_code'] == 'power_output_total')
        self.assertIn('retained', power['status_note'])
        self.assertEqual(1, len(result['fii_flows']['records']))
        self.assertIsNotNone(result['sources'][FII_DATASET]['error'])

    def test_all_sources_failed_does_not_advance_last_success_or_erase_data(self):
        self.seed([observation('power_output_total', '2026-09', 143562.33)], canonical=True)
        result = refresh_cloud_data(self.data, now=NOW, fii_refresher=bad_fii, collectors={'npp_monthly_generation': failed})
        self.assertEqual('failed', result['update_status'])
        self.assertEqual(OLD_SUCCESS, result['last_success_at'])
        self.assertEqual(NOW.isoformat(), result['last_attempt_at'])
        self.assertEqual(1, len(self.read('canonical-observations.json')))
        self.assertEqual(result, self.read('snapshot.json'))
        self.assertEqual('2026-11-17', result['fii_flows']['records'][0]['date'])

    def test_invalid_release_rejects_entire_source_without_affecting_other_sources(self):
        invalid = [
            observation('cpi_headline', '2026-10', float('nan')),
            observation('cpi_headline', '2026-11', 6.5),
            observation('cpi_headline', '2026-10', 6.5, release=date(2026, 11, 26)),
            observation('cpi_headline', '2026-10', True),
        ]
        for record in invalid:
            with self.subTest(value=record.value, period=record.period_label):
                self.seed([observation('cpi_headline', '2026-09', 5.54)], canonical=True)
                result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
                    'mospi_cpi': lambda: [record],
                })
                self.assertEqual('partial', result['update_status'])
                self.assertEqual('failed', result['sources']['mospi_cpi']['status'])
                self.assertEqual([{'period': '2026-09', 'value': 5.54}], result['series']['cpi_headline']['level']['points'])

    def test_seed_bootstrap_retains_segments_and_quarterly_history(self):
        self.seed([
            observation('home_sales_jll', '2026-Q1', 70631),
            observation('home_sales_jll', '2026-Q2', 67751),
        ])
        seeded = load_history(self.data)
        self.assertEqual([None, None], [item.segment for item in seeded])
        self.assertTrue(all(item.source_url == SOURCE_URL for item in seeded))
        result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
            'jll_residential_sales': lambda: [observation('home_sales_jll', '2026-Q3', 76181, segment='top_7_cities')],
        })
        self.assertEqual(3, len(result['series']['home_sales_jll']['level']['points']))
        latest = next(card for card in result['overview']['cards'] if card['metric_code'] == 'home_sales_jll')
        self.assertEqual('2026-Q3', latest['latest_period'])
        self.assertEqual(76181, latest['latest_value'])
        self.assertIsNone(latest['segment'])

    def test_empty_source_result_is_a_failure_not_a_successful_refresh(self):
        self.seed([observation('cpi_headline', '2026-09', 5.54)])
        result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={'mospi_cpi': lambda: []})
        self.assertEqual('partial', result['update_status'])
        self.assertEqual('failed', result['sources']['mospi_cpi']['status'])
        self.assertIsNone(result['sources']['mospi_cpi']['last_success_at'])

    def test_fii_invalid_arithmetic_retains_previous_sessions(self):
        self.seed([])
        def invalid(**_kwargs):
            return {'refresh_status': 'success', 'records': [{'date': '2026-11-24', 'buy': 8, 'sell': 6, 'net': 99}]}
        result = refresh_cloud_data(self.data, now=NOW, collectors={}, fii_refresher=invalid)
        self.assertEqual('failed', result['update_status'])
        self.assertEqual(OLD_SUCCESS, result['last_success_at'])
        self.assertEqual([{'date': '2026-11-17', 'buy': 10.0, 'sell': 7.0, 'net': 3.0}], result['fii_flows']['records'])

    def test_source_deadline_isolated_from_other_collectors(self):
        self.seed([])
        def timeout():
            raise SourceDeadline('Source deadline exceeded')
        result = refresh_cloud_data(self.data, now=NOW, collectors={'npp_monthly_generation': timeout}, fii_refresher=good_fii)
        self.assertEqual('partial', result['update_status'])
        self.assertIn('deadline', result['sources']['npp_monthly_generation']['error'])
        self.assertEqual('success', result['sources'][FII_DATASET]['status'])

    def test_vahan_connection_reset_then_valid_fetch_advances_source_success(self):
        self.seed([observation('two_wheeler_sales', '2026-09', 200, segment='domestic')])
        connector = Mock()
        connector.fetch.side_effect = [URLError(ConnectionResetError('Connection reset by peer')),
                                      FetchResult('vahan_vehicle_registrations', 'success', 'test', SOURCE_URL, 'json', {})]
        connector.parse.return_value = [observation('two_wheeler_sales', '2026-10', 250, segment='domestic')]
        with patch('app.pipelines.cloud_refresh.time.sleep') as sleep:
            result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
                'vahan_vehicle_registrations': _connector_runner(connector, network_attempts=3),
            })
        self.assertEqual(2, connector.fetch.call_count)
        connector.parse.assert_called_once()
        sleep.assert_called_once_with(1)
        self.assertEqual('success', result['update_status'])
        self.assertEqual(NOW.isoformat(), result['sources']['vahan_vehicle_registrations']['last_success_at'])
        self.assertEqual([200, 250], [point['value'] for point in result['series']['two_wheeler_sales']['level']['points']])

    def test_network_retry_budget_exhaustion_retains_verified_history(self):
        self.seed([observation('two_wheeler_sales', '2026-09', 200, segment='domestic')])
        connector = Mock()
        connector.fetch.side_effect = ConnectionResetError('Connection reset by peer')
        with patch('app.pipelines.cloud_refresh.time.sleep') as sleep:
            result = refresh_cloud_data(self.data, now=NOW, fii_refresher=good_fii, collectors={
                'vahan_vehicle_registrations': _connector_runner(connector, network_attempts=3),
            })
        self.assertEqual(3, connector.fetch.call_count)
        self.assertEqual([1, 2], [call.args[0] for call in sleep.call_args_list])
        connector.parse.assert_not_called()
        self.assertEqual('partial', result['update_status'])
        self.assertEqual('2026-09', result['sources']['vahan_vehicle_registrations']['last_successful_period'])
        self.assertEqual([{'period': '2026-09', 'value': 200}], result['series']['two_wheeler_sales']['level']['points'])

    def test_http_client_errors_and_parser_failures_are_not_retried(self):
        raw = FetchResult('vahan_vehicle_registrations', 'success', 'test', SOURCE_URL, 'json', {})
        connector = Mock()
        connector.fetch.side_effect = HTTPError(SOURCE_URL, 403, 'Forbidden', {}, None)
        with patch('app.pipelines.cloud_refresh.time.sleep') as sleep:
            with self.assertRaises(HTTPError):
                _connector_runner(connector, network_attempts=3)()
        self.assertEqual(1, connector.fetch.call_count)
        sleep.assert_not_called()
        connector = Mock()
        connector.fetch.return_value = raw
        connector.parse.side_effect = ValueError('Expected registration table missing')
        with patch('app.pipelines.cloud_refresh.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'table missing'):
                _connector_runner(connector, network_attempts=3)()
        self.assertEqual(1, connector.fetch.call_count)
        sleep.assert_not_called()

    def test_http_server_error_is_retried_but_source_deadline_is_not(self):
        raw = FetchResult('vahan_vehicle_registrations', 'success', 'test', SOURCE_URL, 'json', {})
        connector = Mock()
        connector.fetch.side_effect = [HTTPError(SOURCE_URL, 503, 'Unavailable', {}, None), raw]
        connector.parse.return_value = [observation('two_wheeler_sales', '2026-10', 250)]
        with patch('app.pipelines.cloud_refresh.time.sleep'):
            result = _connector_runner(connector, network_attempts=3)()
        self.assertEqual(250, result[0].value)
        self.assertEqual(2, connector.fetch.call_count)
        connector = Mock()
        connector.fetch.side_effect = SourceDeadline('Time budget exhausted')
        with patch('app.pipelines.cloud_refresh.time.sleep') as sleep:
            with self.assertRaises(SourceDeadline):
                _connector_runner(connector, network_attempts=3)()
        self.assertEqual(1, connector.fetch.call_count)
        sleep.assert_not_called()

    def test_legacy_aggregate_timestamp_keeps_latest_actual_prior_source_success(self):
        self.seed([])
        previous = self.read('snapshot.json')
        newer_success = '2026-11-24T15:00:00+00:00'
        previous['sources'][FII_DATASET]['last_success_at'] = newer_success
        self.write('snapshot.json', previous)
        result = refresh_cloud_data(self.data, now=NOW, collectors={}, fii_refresher=bad_fii)
        self.assertEqual('failed', result['update_status'])
        self.assertEqual(newer_success, result['last_success_at'])
        self.assertEqual(newer_success, result['sources'][FII_DATASET]['last_success_at'])

    def test_failed_fii_collector_cannot_write_unvalidated_public_records(self):
        self.seed([])
        paths = []
        def failing_writer(*, output_dir, now):
            paths.append(output_dir)
            (output_dir / 'fii-flows.json').write_text(json.dumps({'records': []}))
            (output_dir / '.fii-refresh.lock').touch()
            raise RuntimeError('Source failed midway')
        result = refresh_cloud_data(self.data, now=NOW, collectors={}, fii_refresher=failing_writer)
        self.assertNotEqual(self.data, paths[0])
        self.assertEqual('2026-11-17', result['fii_flows']['records'][0]['date'])
        self.assertFalse((self.data / '.fii-refresh.lock').exists())

    def test_snapshot_build_failure_leaves_public_files_unchanged(self):
        self.seed([observation('power_output_total', '2026-09', 143562.33)], canonical=True)
        previous = {path.name: path.read_bytes() for path in self.data.iterdir()}
        def writer(*, output_dir, now):
            payload = good_fii()
            (output_dir / 'fii-flows.json').write_text(json.dumps(payload))
            return payload
        with patch('app.pipelines.cloud_refresh.build_snapshots_from_observations', side_effect=ValueError('Invalid output')):
            with self.assertRaisesRegex(ValueError, 'Invalid output'):
                refresh_cloud_data(self.data, now=NOW, collectors={}, fii_refresher=writer)
        self.assertEqual(previous, {path.name: path.read_bytes() for path in self.data.iterdir()})

    def test_cli_nonzero_for_partial_and_failed_attempts(self):
        for status in ['success', 'partial', 'failed']:
            with patch('app.pipelines.cloud_refresh.refresh_cloud_data', return_value={
                'update_status': status, 'last_attempt_at': NOW.isoformat(), 'last_success_at': OLD_SUCCESS, 'sources': {},
            }):
                self.assertEqual(0 if status == 'success' else 1, main(['--data-dir', str(self.data)]))

    def test_month_window_rolls_back_across_year_boundary(self):
        self.assertEqual(['2025-11', '2025-12', '2026-01'], _recent_months(date(2026, 1, 5)))


if __name__ == '__main__':
    unittest.main()
