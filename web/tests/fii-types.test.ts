import assert from 'node:assert/strict';
import test from 'node:test';
import {
  fiiRefreshDelay, indiaToday, isPartialFiiMonth, monthlyFiiFlows,
  normalizeFiiRecords, type FiiFlowRecord,
} from '../app/lib/fii-types';

test('monthly totals preserve net selling and sum actual observations without zero-filled days', () => {
  const records: FiiFlowRecord[] = [
    { date: '2026-09-30', buy: 10.1, sell: 15.2, net: -5.1 },
    { date: '2026-10-01', buy: 10.11, sell: 15.22, net: -5.11 },
    { date: '2026-10-05', buy: 10.12, sell: 1.23, net: 8.89 },
  ];
  assert.deepEqual(monthlyFiiFlows(records), [
    { period: '2026-09', buy: 10.1, sell: 15.2, net: -5.1, days: 1 },
    { period: '2026-10', buy: 20.23, sell: 16.45, net: 3.78, days: 2 },
  ]);
});

test('revised trading-day figures replace prior figures before monthly summation', () => {
  const records: FiiFlowRecord[] = [
    { date: '2026-10-05', buy: 100, sell: 200, net: -100 },
    { date: '2026-10-01', buy: 300, sell: 100, net: 200 },
    { date: '2026-10-05', buy: 120, sell: 200, net: -80 },
  ];
  assert.deepEqual(normalizeFiiRecords(records).map(({ date, net }) => ({ date, net })), [
    { date: '2026-10-01', net: 200 },
    { date: '2026-10-05', net: -80 },
  ]);
  assert.deepEqual(monthlyFiiFlows(records), [
    { period: '2026-10', buy: 420, sell: 300, net: 120, days: 2 },
  ]);
});

test('invalid calendar dates and nonfinite figures are excluded', () => {
  assert.deepEqual(normalizeFiiRecords([
    { date: '2026-02-30', buy: 1, sell: 0, net: 1 },
    { date: '2026-19-01', buy: 1, sell: 0, net: 1 },
    { date: '2026-10-01', buy: Infinity, sell: 0, net: 1 },
    { date: 'not-published', buy: 0, sell: 0, net: 0 },
  ]), []);
});

test('publication date rolls over at midnight in India rather than UTC', () => {
  assert.equal(indiaToday(new Date('2026-10-27T18:29:59Z')), '2026-10-27');
  assert.equal(indiaToday(new Date('2026-10-27T18:30:00Z')), '2026-10-28');
  assert.equal(indiaToday(new Date('2026-12-31T18:30:00Z')), '2027-01-01');
});

test('first load and background refresh poll promptly until the source settles', () => {
  assert.equal(fiiRefreshDelay({ status: 'refreshing' }), 5_000);
  assert.equal(fiiRefreshDelay({ status: 'available', refreshing: true }), 5_000);
  assert.equal(fiiRefreshDelay({ status: 'available', refreshing: false }), 60_000);
  assert.equal(fiiRefreshDelay({ status: 'unavailable' }), 60_000);
});

test('known full-month history is complete even when its first trading day follows a weekend', () => {
  const records = [{ date: '2026-08-03', buy: 10, sell: 20, net: -10 }];
  assert.equal(monthlyFiiFlows(records)[0].period, '2026-08');
  assert.equal(isPartialFiiMonth('2026-08', { completeMonths: ['2026-08'] }), false);
  assert.equal(isPartialFiiMonth('2026-08'), true);
});

test('missing days in a middle month remain partial even when surrounding months are complete', () => {
  const coverage = {
    completeMonths: ['2026-01', '2026-03'],
    incompleteMonths: ['2026-02'],
    currentMonth: '2026-10',
  };
  assert.equal(isPartialFiiMonth('2026-01', coverage), false);
  assert.equal(isPartialFiiMonth('2026-02', coverage), true);
  assert.equal(isPartialFiiMonth('2026-03', coverage), false);
  assert.equal(isPartialFiiMonth('2026-04', coverage), true);
});

test('current month carries MTD alone unless the source identifies missing history', () => {
  assert.equal(isPartialFiiMonth('2026-10', { currentMonth: '2026-10' }), false);
  assert.equal(isPartialFiiMonth('2026-10', {
    currentMonth: '2026-10', incompleteMonths: ['2026-10'],
  }), true);
});
