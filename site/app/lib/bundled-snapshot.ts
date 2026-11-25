import { getOverview, getReleaseMonitor } from './data';
import { getFiiFlows } from './fii-data';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { SnapshotBundle } from './live-snapshot';

/** Build-time fallback only. The browser replaces it with validated published data. */
export function getBundledSnapshot(): SnapshotBundle {
  const fii = getFiiFlows();
  const generatedAt = fii.last_checked_at || '2026-11-18T12:04:46Z';
  const releaseMonitor = getReleaseMonitor();
  const sources: SnapshotBundle['sources'] = {};
  for (const row of releaseMonitor) {
    sources[String(row.dataset_code)] = {
      status: String(row.status || 'unavailable'),
      // Historical bundle did not retain per-source check timestamps.
      last_checked_at: null,
      last_success_at: null,
      last_successful_period: typeof row.last_successful_period === 'string' ? row.last_successful_period : null,
      error: typeof row.error_message === 'string' ? row.error_message : null,
    };
  }
  sources.nse_fii_equity_flows = {
    status: fii.error ? 'failed' : 'success',
    last_checked_at: fii.last_checked_at,
    last_success_at: fii.last_success_at,
    last_successful_period: fii.records.at(-1)?.date || null,
    error: fii.error,
  };
  return {
    schema_version: 1,
    generated_at: generatedAt,
    last_attempt_at: generatedAt,
    last_success_at: fii.last_success_at,
    update_status: 'partial',
    overview: getOverview(),
    series: JSON.parse(readFileSync(path.join(process.cwd(), 'data', 'series.json'), 'utf8')),
    release_monitor: releaseMonitor,
    fii_flows: fii,
    sources,
  };
}
