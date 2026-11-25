import assert from 'node:assert/strict';
import test from 'node:test';
import { formatAxisValue, periodTicks, valueTicks } from '../app/lib/chart-axes';

test('value ticks cover decimals, large counts, flat series and signed flows', () => {
  for (const values of [[4.45, 4.82, 6.09], [1500000, 2300000], [71, 71], [0], [-32000, 4200]]) {
    const scale = valueTicks(values, { includeZero: values.some((value) => value <= 0) });
    assert.ok(scale.min < scale.max);
    assert.ok(scale.min <= Math.min(...values));
    assert.ok(scale.max >= Math.max(...values));
    assert.ok(scale.ticks.length >= 2 && scale.ticks.length <= 6);
    const step = scale.ticks[1] - scale.ticks[0];
    const labels = scale.ticks.map((value) => formatAxisValue(value, undefined, step));
    assert.equal(new Set(labels).size, labels.length);
  }
  assert.ok(valueTicks([-32000, 4200], { includeZero: true }).ticks.includes(0));
  assert.equal(formatAxisValue(1500000), '1.5M');
  assert.equal(formatAxisValue(4.5, 'percent'), '4.5%');
});

test('nearby large values and tiny decimals retain distinct labels', () => {
  for (const values of [[100001, 100007], [0.000001, 0.000004]]) {
    const { ticks } = valueTicks(values);
    const labels = ticks.map((value) => formatAxisValue(value, '', ticks[1] - ticks[0]));
    assert.equal(new Set(labels).size, ticks.length);
  }
});

test('period ticks follow daily, monthly, quarterly and annual observations', () => {
  assert.deepEqual(periodTicks([]), []);
  assert.deepEqual(periodTicks(['2026-Q3']), [{ index: 0, label: 'Q3 ’26' }]);
  assert.deepEqual(periodTicks(['2026-Q1', '2026-Q2', '2026-Q3']).map((tick) => tick.label), ['Q1 ’26', 'Q2 ’26', 'Q3 ’26']);
  assert.deepEqual(periodTicks(['2025-12', '2026-01']).map((tick) => tick.label), ['Dec ’25', 'Jan ’26']);
  assert.deepEqual(periodTicks(['2025', '2026']).map((tick) => tick.label), ['2025', '2026']);
  const daily = ['2025-12-30', '2025-12-31', '2026-01-02', '2026-01-05'];
  const ticks = periodTicks(daily);
  assert.ok(ticks.length >= 2 && ticks.length <= 3);
  assert.equal(ticks[0].label, '30 Dec ’25');
  assert.equal(ticks.at(-1)?.label, '5 Jan ’26');
});

test('short histories reduce tick density instead of overlapping endpoint labels', () => {
  const ticks = periodTicks(['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']);
  assert.deepEqual(ticks.map((tick) => tick.index), [0, 2, 4]);
});

test('long histories use bounded calendar ticks and retain both endpoints', () => {
  const months = Array.from({ length: 60 }, (_, i) => `${2021 + Math.floor((i + 10) / 12)}-${String((i + 10) % 12 + 1).padStart(2, '0')}`);
  const ticks = periodTicks(months);
  assert.ok(ticks.length <= 4);
  assert.equal(ticks[0].index, 0);
  assert.equal(ticks.at(-1)?.index, months.length - 1);
  assert.ok(ticks.slice(1, -1).every((tick) => months[tick.index].endsWith('-01') && /^\d{4}$/.test(tick.label)));
});
