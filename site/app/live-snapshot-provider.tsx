'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import type { SnapshotBundle } from './lib/live-snapshot';
import { fetchPublishedSnapshot, SNAPSHOT_CHECK_INTERVAL_MS } from './lib/fetch-snapshot';
import { retainLatestSnapshot } from './lib/snapshot-retention';

type SnapshotContext = {
  snapshot: SnapshotBundle;
  checking: boolean;
  fetchError: boolean;
  checkedAt: string | null;
  now: number | null;
};
const SnapshotContext = createContext<SnapshotContext | null>(null);

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
      try {
        const incoming = await fetchPublishedSnapshot(current.current, { signal: controller.signal, now: new Date(lastAttempt) });
        if (!active) return;
        const next = retainLatestSnapshot(current.current, incoming);
        current.current = next;
        setSnapshot(next);
        setFetchError(false);
      } catch {
        if (active) setFetchError(true);
      } finally {
        inFlight = false;
        if (active) { setChecking(false); setNow(Date.now()); setCheckedAt(new Date().toISOString()); }
      }
    }
    function onVisible() {
      if (document.visibilityState === 'visible' && Date.now() - lastAttempt >= SNAPSHOT_CHECK_INTERVAL_MS) void refresh();
    }
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, SNAPSHOT_CHECK_INTERVAL_MS);
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
