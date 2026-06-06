'use client';

import { useEffect, useState } from 'react';

type RefreshStatus = Record<string, string | number | null | undefined>;

export function RefreshStatusPanel({ initialStatus }: { initialStatus: RefreshStatus }) {
  const [status, setStatus] = useState(initialStatus);

  useEffect(() => {
    let cancelled = false;

    async function loadStatus() {
      try {
        const response = await fetch('/api/refresh-status', { cache: 'no-store' });
        if (!response.ok) return;
        const payload = await response.json();
        if (!cancelled) setStatus(payload);
      } catch {
        // Keep the last known status visible.
      }
    }

    loadStatus();
    const timer = window.setInterval(loadStatus, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (status.status !== 'running' && status.status !== 'failed') {
    return null;
  }

  if (status.status === 'failed') {
    return (
      <div className="panel">
        <div className="badge">Refresh failed</div>
        <p>{status.message || 'Background refresh failed. Check the release monitor or backend logs.'}</p>
      </div>
    );
  }

  const progress = Number(status.progress_percent ?? 0);
  const unit = status.total_years !== undefined ? 'years' : 'months';
  const completed = status.total_years !== undefined ? status.completed_years ?? 0 : status.completed_months ?? 0;
  const total = status.total_years ?? status.total_months ?? status.months_requested ?? '—';
  const current = status.current_year ? ` · current: ${status.current_year}` : status.current_month ? ` · current: ${status.current_month}` : '';
  return (
    <div className="panel">
      <div className="badge">Refresh running</div>
      <p>{status.message || 'Scraping and rebuilding the local metric database in the background.'}</p>
      <div className="progress-bar" aria-label="Refresh progress">
        <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(progress, 100))}%` }} />
      </div>
      <p className="muted">
        {progress}% · {completed}/{total} {unit} checked
        {current}
        {status.records_found !== undefined ? ` · found: ${status.records_found}` : ''}
        {status.skipped_months !== undefined ? ` · skipped: ${status.skipped_months}` : ''}
      </p>
      <p className="muted">Progress updates every 2 seconds.</p>
    </div>
  );
}
