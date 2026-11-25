import fcntl
import json
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from app.main import main
from app.pipelines.fii_refresh import FII_FILENAME, refresh_fii_flows


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def record(day, net=10.0):
    return {'date': day, 'buy': 100.0 + max(net, 0), 'sell': 100.0 + max(-net, 0), 'net': net}


class FiiRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name)
        self.path = self.output / FII_FILENAME

    def tearDown(self):
        self.directory.cleanup()

    def refresh(self, rows, **metadata):
        return refresh_fii_flows(self.output, fetcher=lambda: {'records': rows, **metadata}, now=NOW)

    def test_merges_trading_dates_and_upserts_revisions(self):
        self.refresh([record('2026-09-30'), record('2026-10-27', -5)])
        result = self.refresh([record('2026-10-27', -8), record('2026-10-28', 0)])
        self.assertEqual([row['date'] for row in result['records']], ['2026-09-30', '2026-10-27', '2026-10-28'])
        self.assertEqual([row['net'] for row in result['records']], [10, -8, 0])
        self.assertEqual(json.loads(self.path.read_text()), result)
        self.assertEqual(result['coverage_start'], '2026-09-30')
        self.assertEqual(result['coverage_end'], '2026-10-28')
        self.assertEqual(result['refresh_status'], 'success')

    def test_fetch_failure_keeps_history_and_last_success(self):
        original = self.refresh([record('2026-10-27')])

        def failing_fetch():
            raise TimeoutError('Source timed out')

        result = refresh_fii_flows(self.output, fetcher=failing_fetch,
                                   now=datetime(2026, 10, 29, 12, tzinfo=timezone.utc))
        self.assertEqual(result['records'], original['records'])
        self.assertEqual(result['last_success_at'], original['last_success_at'])
        self.assertNotEqual(result['last_checked_at'], original['last_checked_at'])
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['refresh_status'], 'failed')
        self.assertEqual(result['error'], 'Source timed out')

    def test_malformed_batch_cannot_partially_replace_history(self):
        original = self.refresh([record('2026-10-27', -3)])
        for invalid in (dict(record('2026-10-28'), net=float('nan')),
                        dict(record('2026-10-28'), net=999),
                        record('2026-10-29'),
                        dict(record('2026-10-28'), buy=True)):
            with self.subTest(invalid=invalid):
                result = self.refresh([record('2026-10-27', 99), invalid])
                self.assertEqual(result['refresh_status'], 'failed')
                self.assertEqual(result['records'], original['records'])

    def test_empty_source_is_failure_and_does_not_invent_current_day(self):
        result = self.refresh([])
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['refresh_status'], 'failed')
        self.assertIsNone(result['last_success_at'])
        self.assertEqual(result['records'], [])
        self.assertNotIn('coverage_end', result)

    def test_persists_history_attribution_across_latest_only_fetch(self):
        self.refresh([record('2026-10-26')], history_source_url='https://example.com/history',
                     history_note='Historical daily mirror, checked against NSE.')
        result = self.refresh([record('2026-10-27')], source='NSE',
                              data_url='https://www.nseindia.com/api/fiidiiTradeReact')
        self.assertEqual(result['source_name'], 'NSE')
        self.assertEqual(result['history_source_url'], 'https://example.com/history')
        self.assertIn('checked against NSE', result['history_note'])
        self.assertIn('/api/', result['data_url'])

    def test_narrow_refresh_preserves_old_partial_months_and_coverage_metadata(self):
        self.refresh([record('2025-12-03'), record('2026-09-30')],
                     history_complete_months=['2026-09'], history_start_month='2026-09',
                     history_incomplete_months=['2025-12', '2026-01'],
                     history_missing_dates=['2025-12-04', '2026-01-02'],
                     history_requested_start='2025-11-01',
                     history_calendar_url='https://example.com/calendar',
                     history_errors=['2025-12: source gaps'])
        result = self.refresh([record('2026-10-27')], history_complete_months=['2026-09'],
                              history_start_month='2026-09', history_incomplete_months=[],
                              history_missing_dates=[], history_requested_start='2026-09-01')
        self.assertEqual(result['history_incomplete_months'], ['2025-12', '2026-01'])
        self.assertEqual(result['history_missing_dates'], ['2025-12-04', '2026-01-02'])
        self.assertEqual(result['history_requested_start'], '2025-11-01')
        self.assertEqual(result['history_last_requested_start'], '2026-09-01')
        self.assertEqual(result['history_calendar_url'], 'https://example.com/calendar')
        self.assertEqual(result['history_errors'], ['2025-12: source gaps'])

    def test_cached_sessions_can_fill_a_narrow_sources_missing_days(self):
        self.refresh([record('2026-09-29'), record('2026-09-30')],
                     history_complete_months=['2026-09'])
        result = self.refresh([record('2026-10-27')], history_complete_months=[],
                              history_incomplete_months=['2026-09'], history_missing_dates=['2026-09-30'])
        self.assertEqual(result['history_complete_months'], ['2026-09'])
        self.assertEqual(result['history_incomplete_months'], [])
        self.assertEqual(result['history_missing_dates'], [])

    def test_filling_known_gaps_repairs_partial_month_but_unknown_gaps_remain_partial(self):
        self.refresh([record('2026-09-29')], history_incomplete_months=['2026-08', '2026-09'],
                     history_missing_dates=['2026-09-30'])
        result = self.refresh([record('2026-09-30'), record('2026-10-27')])
        self.assertEqual(result['history_complete_months'], ['2026-09'])
        self.assertEqual(result['history_incomplete_months'], ['2026-08'])

    def test_new_unresolved_missing_date_revokes_prior_complete_month(self):
        self.refresh([record('2026-09-30')], history_complete_months=['2026-09'])
        result = self.refresh([record('2026-10-27')], history_incomplete_months=['2026-09'],
                              history_missing_dates=['2026-09-29'])
        self.assertEqual(result['history_complete_months'], [])
        self.assertEqual(result['history_incomplete_months'], ['2026-09'])

    def test_explicit_null_history_source_does_not_erase_retained_mirror_provenance(self):
        note = 'Historical daily observations mirrored by Groww and checked against NSE.'
        self.refresh([record('2026-09-30')], history_source_url='https://example.com/groww',
                     history_source_name='Groww', history_note=note, history_verified=True,
                     history_calendar_url='https://example.com/calendar')
        result = self.refresh([record('2026-10-27')], history_source_url=None, history_source_name=None,
                              history_calendar_url=None, history_verified=False,
                              history_note='History accumulates from daily NSE observations.',
                              history_errors=['History mirror rejected'])
        self.assertEqual(result['history_source_url'], 'https://example.com/groww')
        self.assertEqual(result['history_source_name'], 'Groww')
        self.assertEqual(result['history_calendar_url'], 'https://example.com/calendar')
        self.assertTrue(result['history_verified'])
        self.assertIn(note, result['history_note'])
        self.assertIn('previously cached history is retained', result['history_note'])
        self.assertNotIn('History accumulates from daily NSE observations', result['history_note'])

    def test_default_source_fetches_full_initial_history_then_recent_revision_window(self):
        source = types.ModuleType('app.connectors.nse_fii')
        source.fetch_fii_records = Mock(return_value={'records': [record('2026-10-27')]})
        with patch.dict('sys.modules', {'app.connectors.nse_fii': source}):
            refresh_fii_flows(self.output, now=NOW)
            source.fetch_fii_records.assert_called_with(history_months=12)
            refresh_fii_flows(self.output, now=NOW)
            source.fetch_fii_records.assert_called_with(history_months=2)
            refresh_fii_flows(self.output, now=datetime(2027, 1, 5, tzinfo=timezone.utc))
            source.fetch_fii_records.assert_called_with(history_months=5)

    def test_india_day_controls_date_validation(self):
        # 20:00 UTC on the 27th is already the 28th in India.
        result = refresh_fii_flows(self.output, fetcher=lambda: {'records': [record('2026-10-28')]},
                                   now=datetime(2026, 10, 27, 20, tzinfo=timezone.utc))
        self.assertEqual(result['refresh_status'], 'success')

    def test_concurrent_refresh_skips_without_touching_snapshot(self):
        self.refresh([record('2026-10-27')])
        before = self.path.read_bytes()
        with (self.output / '.fii-refresh.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.refresh([record('2026-10-28')])
        self.assertEqual(result['refresh_status'], 'skipped')
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_snapshot_is_backed_up_exactly_before_successful_source_recovery(self):
        broken = b'{broken JSON\xff'
        self.path.write_bytes(broken)
        result = self.refresh([record('2026-10-28')])
        backup = self.output / result['recovered_from_corrupt_snapshot']
        self.assertEqual(backup.read_bytes(), broken)
        self.assertEqual(json.loads(self.path.read_text())['records'], [record('2026-10-28')])
        # A second corruption creates separate evidence and does not clobber it.
        self.path.write_bytes(b'another broken snapshot')
        second = self.refresh([record('2026-10-28')])
        self.assertNotEqual(result['recovered_from_corrupt_snapshot'], second['recovered_from_corrupt_snapshot'])
        self.assertEqual(backup.read_bytes(), broken)

    def test_corrupt_snapshot_and_source_failure_preserve_original_bytes(self):
        broken = b'{broken JSON\xff'
        self.path.write_bytes(broken)
        result = self.refresh([])
        self.assertEqual(result['refresh_status'], 'failed')
        self.assertIn('Existing snapshot could not be read', result['error'])
        self.assertEqual(self.path.read_bytes(), broken)
        self.assertEqual(list(self.output.glob('fii-flows.corrupt-*.json')), [])

    def test_cli_reads_fixture_and_returns_failure_exit_for_invalid_data(self):
        fixture = self.output / 'fixture.json'
        fixture.write_text(json.dumps({'records': [record('2026-01-01')]}))
        main(['refresh-fii', '--output-dir', str(self.output), '--fixture', str(fixture)])
        self.assertEqual(json.loads(self.path.read_text())['records'][0]['date'], '2026-01-01')
        fixture.write_text(json.dumps({'records': []}))
        with self.assertRaises(SystemExit) as caught:
            main(['refresh-fii', '--output-dir', str(self.output), '--fixture', str(fixture)])
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(len(json.loads(self.path.read_text())['records']), 1)


if __name__ == '__main__':
    unittest.main()
