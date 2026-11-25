import { readFileSync } from 'node:fs';
import path from 'node:path';

export type OverviewCard = {
  metric_code: string;
  title: string;
  latest_period: string | null;
  latest_value: number | null;
  unit: string;
  change_prev: number | null;
  change_prev_unit: string;
  change_yoy: number | null;
  change_yoy_unit: string;
  sparkline: Array<number | { period: string; value: number }>;
  source: string;
  release_date: string | null;
  latest_retrieved_for?: string | null;
  segment?: string | null;
  status?: 'available' | 'missing';
  status_note?: string | null;
  retrieval_skill?: string | null;
  source_url?: string | null;
};

type OverviewPayload = { cards: OverviewCard[]; summary: string };
type SeriesPayload = Record<string, Record<string, unknown>>;
type ReleaseMonitorPayload = Array<Record<string, string | number | null>>;

const DATA_DIR = path.join(process.cwd(), 'data');

function readSnapshot<T>(name: string): T {
  return JSON.parse(readFileSync(path.join(DATA_DIR, name), 'utf8')) as T;
}

export function getOverview() {
  return readSnapshot<OverviewPayload>('overview.json');
}

export function getSeries(metricCode: string, transform = 'level') {
  const series = readSnapshot<SeriesPayload>('series.json');
  return series[metricCode]?.[transform] || null;
}

export function getReleaseMonitor() {
  return readSnapshot<ReleaseMonitorPayload>('release-monitor.json');
}

export function getRefreshStatus() {
  return { status: 'success', message: 'Published snapshot updated 18 Nov 2026.' };
}
