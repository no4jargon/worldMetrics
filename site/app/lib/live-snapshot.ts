import type { OverviewCard } from './data';
import type { FiiFlowsPayload } from './fii-types';

export type SeriesPayload = {
  points?: Array<{ period: string; value: number }>;
  source?: string;
  unit?: string;
  status?: string;
  status_note?: string | null;
  retrieval_skill?: string | null;
  source_url?: string | null;
  [key: string]: unknown;
};

export type SourceStatus = {
  status: string;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_successful_period: string | null;
  error: string | null;
};

export type SnapshotBundle = {
  schema_version: 1;
  generated_at: string;
  last_attempt_at: string;
  last_success_at: string | null;
  update_status: 'success' | 'partial' | 'failed';
  overview: { cards: OverviewCard[]; summary: string };
  series: Record<string, Record<string, SeriesPayload>>;
  release_monitor: Array<Record<string, string | number | null>>;
  fii_flows: FiiFlowsPayload;
  sources: Record<string, SourceStatus>;
};

type JsonObject = Record<string, unknown>;
const CLOCK_TOLERANCE_MS = 5 * 60_000;

function fail(message: string): never {
  throw new Error(`Invalid published data: ${message}`);
}

function object(value: unknown, field: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${field} must be an object`);
  return value as JsonObject;
}

function text(value: unknown, field: string, nullable = false, limit = 32_000): void {
  if (nullable && value === null) return;
  if (typeof value !== 'string' || value.length > limit) fail(`${field} must be text`);
}

function numeric(value: unknown, field: string, nullable = false): void {
  if (nullable && value === null) return;
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${field} must be finite`);
}

function array(value: unknown, field: string, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) fail(`${field} exceeds its size limit`);
  return value;
}

function timestamp(value: unknown, field: string, now: number, nullable = false): number | null {
  if (nullable && value === null) return null;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) fail(`${field} must be an ISO timestamp`);
  const parsed = Date.parse(value);
  // Date.parse normalizes impossible calendar dates, so check the date itself too.
  const day = value.slice(0, 10);
  const date = new Date(`${day}T00:00:00Z`);
  if (!Number.isFinite(parsed) || !Number.isFinite(date.valueOf()) || date.toISOString().slice(0, 10) !== day) fail(`${field} is invalid`);
  if (parsed > now + CLOCK_TOLERANCE_MS) fail(`${field} is in the future`);
  return parsed;
}

function indiaDate(now: Date): string {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = (part: string) => parts.find((item) => item.type === part)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function period(value: unknown, field: string, today: string, nullable = false): { key: number; kind: string } | null {
  if (nullable && value === null) return null;
  if (typeof value !== 'string') fail(`${field} must be a reporting period`);
  const match = value.match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?|-Q([1-4]))?$/);
  if (!match) fail(`${field} has an invalid reporting period`);
  const year = Number(match[1]);
  const month = match[4] ? (Number(match[4]) - 1) * 3 + 1 : Number(match[2] || 1);
  const day = Number(match[3] || 1);
  if (year < 1900 || month < 1 || month > 12) fail(`${field} has an invalid calendar date`);
  const canonical = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const parsed = new Date(`${canonical}T00:00:00Z`);
  if (!Number.isFinite(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== canonical) fail(`${field} has an invalid calendar date`);
  if (canonical > today) fail(`${field} is in the future`);
  return { key: parsed.valueOf(), kind: match[4] ? 'quarter' : match[3] ? 'day' : match[2] ? 'month' : 'year' };
}

function points(value: unknown, field: string, today: string, allowNumbers = false): void {
  const rows = array(value, field, 20_000);
  let previous = -Infinity;
  let cadence: string | undefined;
  let numericRows: boolean | undefined;
  for (const item of rows) {
    const isNumeric = typeof item === 'number';
    if (numericRows !== undefined && numericRows !== isNumeric) fail(`${field} mixes dated and undated points`);
    numericRows = isNumeric;
    if (allowNumbers && isNumeric) { numeric(item, field); continue; }
    const row = object(item, field);
    const stamp = period(row.period, `${field}.period`, today)!;
    numeric(row.value, `${field}.value`);
    if (cadence && stamp.kind !== cadence) fail(`${field} mixes reporting frequencies`);
    if (stamp.key <= previous) fail(`${field} is duplicated or out of order`);
    cadence = stamp.kind;
    previous = stamp.key;
  }
}

function safeUrl(value: unknown, field: string): void {
  if (value === null || value === undefined) return;
  if (typeof value !== 'string' || value.length > 4096) fail(`${field} must be a URL`);
  let url: URL;
  try { url = new URL(value); } catch { fail(`${field} must be an absolute URL`); }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) fail(`${field} has an unsafe URL`);
}

/** Reject non-JSON values, excessive nesting, unsafe link fields and non-finite extras. */
function inspect(value: unknown): void {
  let nodes = 0;
  const seen = new Set<object>();
  function visit(item: unknown, field: string, depth: number): void {
    if (++nodes > 300_000 || depth > 20) fail('bundle exceeds its structural limit');
    if (typeof item === 'number') { numeric(item, field); return; }
    if (typeof item === 'string') { text(item, field); return; }
    if (item === null || typeof item === 'boolean') return;
    if (typeof item !== 'object') fail(`${field} is not JSON data`);
    if (seen.has(item)) fail('bundle contains a cyclic value');
    seen.add(item);
    if (Array.isArray(item)) {
      if (item.length > 20_000) fail(`${field} exceeds its size limit`);
      item.forEach((child) => visit(child, field, depth + 1));
    } else {
      for (const [key, child] of Object.entries(item)) {
        if (['__proto__', 'constructor', 'prototype'].includes(key)) fail(`${field} contains an unsafe key`);
        if (key.endsWith('_url')) safeUrl(child, `${field}.${key}`);
        visit(child, `${field}.${key}`, depth + 1);
      }
    }
    seen.delete(item);
  }
  visit(value, 'snapshot', 0);
}

/** Validate the entire atomic bundle before it can replace the on-screen figures. */
export function validateSnapshot(value: unknown, now = new Date(), previous?: SnapshotBundle): SnapshotBundle {
  if (!Number.isFinite(now.valueOf())) fail('validation clock is invalid');
  inspect(value);
  const root = object(value, 'snapshot');
  const today = indiaDate(now);
  if (root.schema_version !== 1) fail('unsupported schema version');
  if (!['success', 'partial', 'failed'].includes(String(root.update_status))) fail('unsupported update status');
  const generated = timestamp(root.generated_at, 'generated_at', now.valueOf())!;
  const attempted = timestamp(root.last_attempt_at, 'last_attempt_at', now.valueOf())!;
  const successful = timestamp(root.last_success_at, 'last_success_at', now.valueOf(), true);
  if (attempted > generated + CLOCK_TOLERANCE_MS || (successful !== null && successful > attempted + CLOCK_TOLERANCE_MS)) fail('update timestamps are inconsistent');
  if (previous && (generated < Date.parse(previous.generated_at) || attempted < Date.parse(previous.last_attempt_at))) fail('bundle is older than the last accepted update');

  const overview = object(root.overview, 'overview');
  text(overview.summary, 'overview.summary');
  const cards = array(overview.cards, 'overview.cards', 100);
  if (!cards.length) fail('overview contains no metric cards');
  const codes = new Set<string>();
  for (const item of cards) {
    const card = object(item, 'card');
    for (const field of ['metric_code', 'title', 'unit', 'source', 'change_prev_unit', 'change_yoy_unit']) text(card[field], `card.${field}`, false, 512);
    if (!/^[a-z0-9_]+$/.test(card.metric_code as string) || codes.has(card.metric_code as string)) fail('metric cards have invalid or repeated codes');
    codes.add(card.metric_code as string);
    period(card.latest_period, 'card.latest_period', today, true);
    for (const field of ['latest_value', 'change_prev', 'change_yoy']) numeric(card[field], `card.${field}`, true);
    if ((card.latest_period === null) !== (card.latest_value === null)) fail('metric period and value disagree');
    for (const field of ['release_date', 'latest_retrieved_for']) if (card[field] !== undefined) period(card[field], `card.${field}`, today, true);
    for (const field of ['status', 'status_note', 'segment', 'retrieval_skill']) if (card[field] !== undefined) text(card[field], `card.${field}`, true);
    safeUrl(card.source_url, 'card.source_url');
    points(card.sparkline, 'card.sparkline', today, true);
  }

  const series = object(root.series, 'series');
  if (Object.keys(series).length > 100) fail('too many metric series');
  for (const [metric, rawTransforms] of Object.entries(series)) {
    if (!/^[a-z0-9_]+$/.test(metric)) fail('invalid series metric code');
    const transforms = object(rawTransforms, 'series transforms');
    if (Object.keys(transforms).length > 32) fail('too many transforms');
    for (const [transform, rawPayload] of Object.entries(transforms)) {
      if (!/^[a-z0-9_]+$/.test(transform)) fail('invalid transform name');
      const payload = object(rawPayload, 'series payload');
      if (payload.points !== undefined) points(payload.points, 'series.points', today);
      for (const field of ['source', 'unit', 'status', 'status_note', 'retrieval_skill']) if (payload[field] !== undefined) text(payload[field], `series.${field}`, true);
      safeUrl(payload.source_url, 'series.source_url');
    }
  }

  const monitor = array(root.release_monitor, 'release_monitor', 200);
  for (const item of monitor) {
    const row = object(item, 'release monitor row');
    text(row.dataset_code, 'release monitor dataset_code', false, 512);
    for (const [key, val] of Object.entries(row)) {
      if (val !== null && typeof val !== 'string' && typeof val !== 'number') fail('release monitor row has an invalid field');
      if (['last_successful_period', 'last_release_date'].includes(key)) period(val, `release_monitor.${key}`, today, true);
    }
  }

  const fii = object(root.fii_flows, 'fii_flows');
  for (const field of ['source_name', 'source_url', 'scope']) text(fii[field], `fii_flows.${field}`, false, 4096);
  safeUrl(fii.source_url, 'fii_flows.source_url');
  if (typeof fii.is_provisional !== 'boolean' || !['available', 'unavailable', 'refreshing'].includes(String(fii.status))) fail('FII metadata is invalid');
  timestamp(fii.last_checked_at, 'fii_flows.last_checked_at', now.valueOf(), true);
  timestamp(fii.last_success_at, 'fii_flows.last_success_at', now.valueOf(), true);
  text(fii.error, 'fii_flows.error', true);
  let previousDay = -Infinity;
  for (const item of array(fii.records, 'fii_flows.records', 20_000)) {
    const row = object(item, 'FII record');
    if (typeof row.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) fail('FII record requires a trading date');
    const stamp = period(row.date, 'FII record date', today)!;
    if (stamp.key <= previousDay) fail('FII records are duplicated or out of order');
    previousDay = stamp.key;
    for (const field of ['buy', 'sell', 'net']) numeric(row[field], `FII.${field}`);
    if ((row.buy as number) < 0 || (row.sell as number) < 0 || Math.abs((row.buy as number) - (row.sell as number) - (row.net as number)) > 0.051) fail('FII purchase/sale/net totals disagree');
  }
  for (const [key, val] of Object.entries(fii)) {
    if (['coverage_start', 'coverage_end', 'history_requested_start', 'history_last_requested_start', 'history_start_month'].includes(key)) period(val, `fii_flows.${key}`, today, true);
    if (['history_complete_months', 'history_incomplete_months', 'history_missing_months', 'history_missing_dates'].includes(key) && val !== null) {
      for (const label of array(val, `fii_flows.${key}`, 20_000)) period(label, `fii_flows.${key}`, today);
    }
  }

  const sources = object(root.sources, 'sources');
  if (Object.keys(sources).length > 100) fail('too many data sources');
  for (const [dataset, rawSource] of Object.entries(sources)) {
    if (!/^[a-z0-9_]+$/.test(dataset)) fail('invalid source dataset');
    const source = object(rawSource, 'source status');
    text(source.status, 'source.status', false, 64);
    timestamp(source.last_checked_at, 'source.last_checked_at', now.valueOf(), true);
    timestamp(source.last_success_at, 'source.last_success_at', now.valueOf(), true);
    period(source.last_successful_period, 'source.last_successful_period', today, true);
    text(source.error, 'source.error', true);
  }
  return value as SnapshotBundle;
}
