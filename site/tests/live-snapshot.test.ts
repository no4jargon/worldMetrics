import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { validateSnapshot, type SnapshotBundle } from '../app/lib/live-snapshot';
import { retainLatestSnapshot } from '../app/lib/snapshot-retention';

const NOW = new Date('2026-11-25T10:00:00Z');

function fixture(): SnapshotBundle {
  const read = (name: string) => JSON.parse(readFileSync(path.join(process.cwd(), 'data', `${name}.json`), 'utf8'));
  const monitor = read('release-monitor');
  const sources = Object.fromEntries(monitor.map((row: Record<string, string | number | null>) => [row.dataset_code, {
    status: row.status,
    last_checked_at: '2026-11-18T13:00:00Z',
    last_success_at: row.status === 'success' ? '2026-11-18T13:00:00Z' : null,
    last_successful_period: row.last_successful_period,
    error: row.error_message,
  }]));
  return {
    schema_version: 1,
    generated_at: '2026-11-18T13:00:00Z',
    last_attempt_at: '2026-11-18T13:00:00Z',
    last_success_at: '2026-11-18T13:00:00Z',
    update_status: 'partial',
    overview: read('overview'),
    series: read('series'),
    release_monitor: monitor,
    fii_flows: read('fii-flows'),
    sources,
  };
}

test('accepts the complete bundled legacy data, including sparse and unavailable series', () => {
  const data = fixture();
  assert.equal(validateSnapshot(data, NOW), data);
  data.update_status = 'failed';
  assert.equal(validateSnapshot(data, NOW).update_status, 'failed');
});

test('rejects future reporting periods and invalid calendar dates', () => {
  for (const label of ['2026-12', '2027-Q1', '2027', '2026-11-26', '2026-02-30', '2026-13', '2026-Q5']) {
    const data = fixture();
    data.overview.cards[0].latest_period = label;
    assert.throws(() => validateSnapshot(data, NOW), /period|future|calendar/);
  }
  const data = fixture();
  data.generated_at = '2026-02-30T00:00:00Z';
  assert.throws(() => validateSnapshot(data, NOW), /generated_at is invalid/);
});

test('rejects future metadata and bundles older than the accepted generation or attempt', () => {
  const previous = fixture();
  const future = fixture();
  future.generated_at = '2026-11-25T10:06:00Z';
  assert.throws(() => validateSnapshot(future, NOW), /future/);
  const older = fixture();
  older.generated_at = '2026-11-17T13:00:00Z';
  older.last_attempt_at = '2026-11-17T13:00:00Z';
  older.last_success_at = '2026-11-17T13:00:00Z';
  assert.throws(() => validateSnapshot(older, NOW, previous), /older/);
  const olderAttempt = fixture();
  olderAttempt.generated_at = '2026-11-19T13:00:00Z';
  olderAttempt.last_attempt_at = '2026-11-17T13:00:00Z';
  olderAttempt.last_success_at = null;
  assert.throws(() => validateSnapshot(olderAttempt, NOW, previous), /older/);
});

test('rejects nonfinite points, unsafe links, repeated periods and inconsistent FII totals', () => {
  const changes: Array<(data: SnapshotBundle) => void> = [
    (data) => { data.overview.cards[0].latest_value = Infinity; },
    (data) => { data.overview.cards[0].source_url = 'javascript:alert(1)'; },
    (data) => { data.series.power_output_total.level.points![1].value = NaN; },
    (data) => { data.series.power_output_total.level.points![1].period = data.series.power_output_total.level.points![0].period; },
    (data) => { data.fii_flows.records[0].net += 1; },
    (data) => { data.fii_flows.records[0].buy = -10; },
    (data) => { data.fii_flows.records[1].date = data.fii_flows.records[0].date; },
    (data) => { data.fii_flows.records.at(-1)!.date = '2026-11-26'; },
  ];
  for (const change of changes) {
    const data = fixture();
    change(data);
    assert.throws(() => validateSnapshot(data, NOW), /Invalid published data/);
  }
});

test('rejects oversized arrays and prototype-style keys before accepting data', () => {
  const data = fixture();
  data.fii_flows.records = Array.from({ length: 20_001 }, () => data.fii_flows.records[0]);
  assert.throws(() => validateSnapshot(data, NOW), /size limit/);
  const unsafe = fixture();
  Object.defineProperty(unsafe.series, '__proto__', { value: {}, enumerable: true });
  assert.throws(() => validateSnapshot(unsafe, NOW), /unsafe key/);
});


test('a failed remote check can deliver newer retained figures than the initial fallback', () => {
  const current = fixture();
  const incoming = fixture();
  incoming.generated_at = '2026-11-25T09:00:00Z';
  incoming.last_attempt_at = incoming.generated_at;
  incoming.last_success_at = '2026-11-24T15:00:00Z';
  incoming.update_status = 'failed';
  incoming.overview.cards[0].latest_value = 999;
  assert.equal(retainLatestSnapshot(current, validateSnapshot(incoming, NOW, current)), incoming);
});

test('a failed update cannot regress the last successful check or reporting periods', () => {
  const current = fixture();
  const incoming = fixture();
  incoming.update_status = 'failed';
  incoming.generated_at = '2026-11-25T09:00:00Z';
  incoming.last_attempt_at = incoming.generated_at;
  incoming.last_success_at = '2026-11-17T09:00:00Z';
  incoming.overview.cards[0].latest_value = 999;
  let retained = retainLatestSnapshot(current, incoming);
  assert.equal(retained.overview, current.overview);
  assert.equal(retained.last_success_at, current.last_success_at);
  assert.equal(retained.update_status, 'failed');
  incoming.last_success_at = '2026-11-24T15:00:00Z';
  incoming.overview.cards[0].latest_period = '2026-08';
  retained = retainLatestSnapshot(current, incoming);
  assert.equal(retained.overview, current.overview);
});
