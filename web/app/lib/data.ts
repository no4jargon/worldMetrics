import { existsSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

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

const WEB_ROOT = process.cwd();
const PROJECT_ROOT = path.resolve(WEB_ROOT, '..');
const DATA_DIR = path.join(WEB_ROOT, 'data');
const OVERVIEW_PATH = path.join(DATA_DIR, 'overview.json');
const SERIES_PATH = path.join(DATA_DIR, 'series.json');
const RELEASE_MONITOR_PATH = path.join(DATA_DIR, 'release-monitor.json');
const REFRESH_METADATA_PATH = path.join(DATA_DIR, 'refresh-metadata.json');
const REFRESH_STATUS_PATH = path.join(DATA_DIR, 'refresh-status.json');
const BACKEND_DIR = path.join(PROJECT_ROOT, 'backend');
const VENV_PYTHON = path.join(BACKEND_DIR, '.venv', 'bin', 'python');

let autoRefreshAttempted = false;

function readJson<T>(filePath: string, fallback: T): T {
  if (!existsSync(filePath)) {
    return fallback;
  }
  return JSON.parse(readFileSync(filePath, 'utf8')) as T;
}

function snapshotsExist() {
  return existsSync(OVERVIEW_PATH) && existsSync(SERIES_PATH) && existsSync(RELEASE_MONITOR_PATH);
}

function snapshotsCoverRequestedWindow() {
  const requestedMonths = Number(process.env.WM_AUTO_REFRESH_MONTHS || '60');
  if (!existsSync(REFRESH_METADATA_PATH)) {
    return false;
  }
  const metadata = readJson<{ months_requested?: number }>(REFRESH_METADATA_PATH, {});
  return Number(metadata.months_requested || 0) >= requestedMonths;
}

function refreshInProgress() {
  const status = readJson<{ status?: string; updated_at?: string }>(REFRESH_STATUS_PATH, {});
  if (status.status !== 'running' || !status.updated_at) {
    return false;
  }
  const updatedAt = Date.parse(status.updated_at);
  if (Number.isNaN(updatedAt)) {
    return false;
  }
  return Date.now() - updatedAt < 60 * 60 * 1000;
}

function ensureSnapshots() {
  if (snapshotsExist() && snapshotsCoverRequestedWindow()) {
    return;
  }
  if (autoRefreshAttempted || refreshInProgress() || process.env.WM_AUTO_REFRESH_ON_OPEN === '0') {
    return;
  }
  autoRefreshAttempted = true;

  mkdirSync(DATA_DIR, { recursive: true });
  writeFileSync(
    REFRESH_STATUS_PATH,
    JSON.stringify(
      {
        status: 'running',
        updated_at: new Date().toISOString(),
        months_requested: Number(process.env.WM_AUTO_REFRESH_MONTHS || '60'),
        end_period: null,
        message: 'Refreshing local metric database in the background.',
      },
      null,
      2,
    ),
  );

  const python = existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python';
  const child = spawn(
    python,
    ['-m', 'app.main', 'refresh-dev', '--months', process.env.WM_AUTO_REFRESH_MONTHS || '60'],
    {
      cwd: BACKEND_DIR,
      detached: true,
      stdio: 'ignore',
      env: { ...process.env, PYTHONPATH: BACKEND_DIR },
    },
  );
  child.on('error', (error) => console.error('WorldMetrics auto-refresh failed to start', error));
  child.unref();
}

export function getOverview() {
  ensureSnapshots();
  return readJson<OverviewPayload>(OVERVIEW_PATH, {
    cards: [],
    summary: 'No local data available. Run backend refresh-dev or check connector errors.',
  });
}

export function getSeries(metricCode: string, transform = 'level') {
  ensureSnapshots();
  const seriesData = readJson<SeriesPayload>(SERIES_PATH, {});
  const metricSeries = seriesData[metricCode] || {};
  return metricSeries[transform] || null;
}

export function getReleaseMonitor() {
  ensureSnapshots();
  return readJson<ReleaseMonitorPayload>(RELEASE_MONITOR_PATH, []);
}

export function getRefreshStatus() {
  ensureSnapshots();
  return readJson<Record<string, string | number | null | undefined>>(REFRESH_STATUS_PATH, {
    status: snapshotsExist() ? 'idle' : 'not_started',
    message: snapshotsExist() ? 'Snapshots are available.' : 'No snapshots available yet.',
  });
}
