import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import type { FiiFlowsPayload } from './fii-types';
import { shouldRefreshFii } from './fii-refresh-policy';

const BACKEND_DIR = path.resolve(process.cwd(), '../backend');
const DATA_DIR = path.resolve(process.env.WM_FII_DATA_DIR || path.join(process.cwd(), 'data'));
const DATA_PATH = path.join(DATA_DIR, 'fii-flows.json');
const VENV_PYTHON = path.join(BACKEND_DIR, '.venv', 'bin', 'python');
let lastAttemptAt = 0;
let refreshInFlight = false;

function emptyPayload(): FiiFlowsPayload {
  return {
    records: [], source_name: 'NSE', source_url: 'https://www.nseindia.com/reports/fii-dii',
    scope: 'NSE, BSE and MSEI cash market', is_provisional: true,
    last_checked_at: null, last_success_at: null, error: null, status: 'unavailable',
  };
}

function readSnapshot(): FiiFlowsPayload {
  try {
    if (!existsSync(DATA_PATH)) return emptyPayload();
    const data = JSON.parse(readFileSync(DATA_PATH, 'utf8')) as FiiFlowsPayload;
    if (!Array.isArray(data.records)) throw new Error('Missing daily records');
    return { ...emptyPayload(), ...data };
  } catch {
    return { ...emptyPayload(), error: 'The saved FII data could not be read. A fresh download will be attempted.' };
  }
}

function recordStartFailure(error: Error) {
  if (existsSync(DATA_PATH)) {
    try {
      const saved = JSON.parse(readFileSync(DATA_PATH, 'utf8'));
      if (!Array.isArray(saved.records)) return;
    } catch {
      // The pipeline preserves and backs up corrupt files before rebuilding.
      // A failed child must not replace those recoverable bytes with an empty cache.
      console.error('World Metrics FII refresh failed with an unreadable saved snapshot', error);
      return;
    }
  }
  const payload = readSnapshot();
  const failed = { ...payload, error: `FII refresh could not start: ${error.message}`, last_checked_at: new Date().toISOString() };
  const tempPath = `${DATA_PATH}.${process.pid}.tmp`;
  try {
    writeFileSync(tempPath, JSON.stringify(failed, null, 2));
    renameSync(tempPath, DATA_PATH);
  } catch (writeError) {
    console.error('World Metrics FII refresh failed', writeError);
  }
}

export function getFiiFlows(): FiiFlowsPayload {
  const data = readSnapshot();
  if (!refreshInFlight && process.env.WM_FII_AUTO_REFRESH !== '0' && shouldRefreshFii(data, new Date(), lastAttemptAt)) {
    lastAttemptAt = Date.now();
    refreshInFlight = true;
    mkdirSync(DATA_DIR, { recursive: true });
    const child = spawn(
      existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python3',
      ['-m', 'app.main', 'refresh-fii', '--output-dir', DATA_DIR],
      { cwd: BACKEND_DIR, detached: true, stdio: 'ignore', env: { ...process.env, PYTHONPATH: BACKEND_DIR } },
    );
    const watchdog = setTimeout(() => {
      child.kill('SIGTERM');
      recordStartFailure(new Error('The source check timed out. The next check will retry.'));
      refreshInFlight = false;
    }, 120_000);
    watchdog.unref();
    child.on('error', (error) => { clearTimeout(watchdog); refreshInFlight = false; recordStartFailure(error); });
    child.on('exit', (code) => {
      clearTimeout(watchdog);
      refreshInFlight = false;
      // The pipeline normally records failures itself. Surface startup/import
      // failures too, without replacing the last successfully downloaded data.
      const checkedAt = Date.parse(readSnapshot().last_checked_at || '');
      if (code && (!Number.isFinite(checkedAt) || checkedAt < lastAttemptAt)) {
        recordStartFailure(new Error('The data collector exited before completing its source check.'));
      }
    });
    child.unref();
  }
  return { ...data, refreshing: refreshInFlight };
}
