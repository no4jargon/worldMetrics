import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldRefreshFii } from '../app/lib/fii-refresh-policy';

test('a new India calendar day refreshes even with a recent previous-day check', () => {
  assert.equal(shouldRefreshFii({ last_checked_at: '2026-10-27T18:25:00Z', error: null }, new Date('2026-10-27T18:35:00Z')), true);
});

test('after close checks retry for a newly published day every fifteen minutes', () => {
  const data = { last_checked_at: '2026-10-28T12:00:00Z', error: null };
  assert.equal(shouldRefreshFii(data, new Date('2026-10-28T12:14:59Z')), false);
  assert.equal(shouldRefreshFii(data, new Date('2026-10-28T12:15:00Z')), true);
});

test('before close and weekends avoid frequent upstream fetches', () => {
  assert.equal(shouldRefreshFii({ last_checked_at: '2026-10-28T04:00:00Z', error: null }, new Date('2026-10-28T05:00:00Z')), false);
  assert.equal(shouldRefreshFii({ last_checked_at: '2026-10-31T11:00:00Z', error: null }, new Date('2026-10-31T12:00:00Z')), false);
});

test('failed fetches retry after five minutes while retaining the previous data', () => {
  const data = { last_checked_at: '2026-10-28T04:00:00Z', error: 'Upstream unavailable' };
  assert.equal(shouldRefreshFii(data, new Date('2026-10-28T04:04:59Z')), false);
  assert.equal(shouldRefreshFii(data, new Date('2026-10-28T04:05:00Z')), true);
});

test('missing or invalid timestamps refresh, and concurrent requests respect cooldown', () => {
  const now = new Date('2026-10-28T12:00:00Z');
  assert.equal(shouldRefreshFii({ last_checked_at: null, error: null }, now), true);
  assert.equal(shouldRefreshFii({ last_checked_at: 'invalid', error: null }, now), true);
  assert.equal(shouldRefreshFii({ last_checked_at: null, error: null }, now, now.getTime() - 30_000), false);
});
