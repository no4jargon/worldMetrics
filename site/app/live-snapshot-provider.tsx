'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { validateSnapshot, type SnapshotBundle } from './lib/live-snapshot';
import { retainLatestSnapshot } from './lib/snapshot-retention';

export const LIVE_SNAPSHOT_URL = 'https://raw.githubusercontent.com/no4jargon/worldMetrics/main/published-data/snapshot.json';
const CHECK_INTERVAL_MS = 15 * 60 * 1000;
const MAX_SNAPSHOT_BYTES = 3 * 1024 * 1024;

type SnapshotContext = {
  snapshot: SnapshotBundle;
  checking: boolean;
  fetchError: boolean;
  checkedAt: string | null;
  now: number | null;
};
const SnapshotContext = createContext<SnapshotContext | null>(null);

async function readBoundedResponse(response: Response): Promise<string> {
  const declaredSize = Number(response.headers.get('content-length'));
  if (Number.isFinite(declaredSize) && declaredSize > MAX_SNAPSHOT_BYTES) throw new Error('Update exceeds size limit');
  if (!response.body) throw new Error('Update has no body');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0;
  let text = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_SNAPSHOT_BYTES) { await reader.cancel(); throw new Error('Update exceeds size limit'); }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally {
    reader.releaseLock();
  }
}

export function LiveSnapshotProvider({ initialSnapshot, children }: { initialSnapshot: SnapshotBundle; children: ReactNode }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const current = useRef(initialSnapshot);
  const [checking, setChecking] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let lastAttempt = 0;
    let controller: AbortController | null = null;
    async function refresh() {
      if (!active || inFlight || document.visibilityState === 'hidden') return;
      inFlight = true;
      lastAttempt = Date.now();
      setNow(lastAttempt);
      setChecking(true);
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 15_000);
      try {
        // A bounded 15-minute cache key avoids a fresh CDN URL for every render.
        const url = `${LIVE_SNAPSHOT_URL}?window=${Math.floor(lastAttempt / CHECK_INTERVAL_MS)}`;
        const response = await fetch(url, { cache: 'no-store', signal: controller.signal, credentials: 'omit' });
        if (!response.ok) throw new Error('Published update unavailable');
        const incoming = validateSnapshot(JSON.parse(await readBoundedResponse(response)), new Date(), current.current);
        if (!active) return;
        const next = retainLatestSnapshot(current.current, incoming);
        current.current = next;
        setSnapshot(next);
        setFetchError(false);
      } catch {
        if (active) setFetchError(true);
      } finally {
        clearTimeout(timeout);
        inFlight = false;
        if (active) { setChecking(false); setNow(Date.now()); setCheckedAt(new Date().toISOString()); }
      }
    }
    function onVisible() {
      if (document.visibilityState === 'visible' && Date.now() - lastAttempt >= CHECK_INTERVAL_MS) void refresh();
    }
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, CHECK_INTERVAL_MS);
    document.addEventListener('visibilitychange', onVisible);
    return () => { active = false; clearInterval(timer); controller?.abort(); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  return <SnapshotContext.Provider value={{ snapshot, checking, fetchError, checkedAt, now }}>{children}</SnapshotContext.Provider>;
}

export function useDashboardSnapshot() {
  const context = useContext(SnapshotContext);
  if (!context) throw new Error('Dashboard must be inside LiveSnapshotProvider');
  return context;
}

function formatCheck(value: string | null) {
  if (!value) return 'not yet verified';
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' })
    .format(new Date(value)) + ' IST';
}

export function SnapshotStatus() {
  const { snapshot, checking, fetchError, checkedAt, now } = useDashboardSnapshot();
  const lastCheck = snapshot.last_success_at;
  const stale = now !== null && (!lastCheck || now - Date.parse(lastCheck) > 36 * 60 * 60 * 1000);
  let note = snapshot.update_status === 'failed'
    ? 'The scheduled update failed; showing the last available figures.'
    : snapshot.update_status === 'partial' ? 'Some sources could not update; their last available figures are retained.' : 'Latest published source results loaded.';
  if (fetchError) note = 'The latest update could not be downloaded; showing the last available figures.';
  if (checking) note = 'Checking for a newer published update…';
  return (
    <div className="snapshot-notice" aria-live="polite">
      <p><strong>Last successful source check: {formatCheck(lastCheck)}</strong></p>
      <p>Automatic source checks run daily at 20:30 IST. This page checks for new data every 15 minutes while open.</p>
      <p className={fetchError || stale || snapshot.update_status !== 'success' ? 'snapshot-warning' : undefined}>{note}{stale ? ' The last successful check is more than 36 hours old.' : ''}</p>
      <a href="https://github.com/no4jargon/worldMetrics/actions" target="_blank" rel="noopener noreferrer">View source update history</a>
      {checkedAt ? <span className="snapshot-checked"> · Page checked {formatCheck(checkedAt)}</span> : null}
    </div>
  );
}
