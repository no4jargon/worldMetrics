'use client';

import { useDashboardSnapshot } from '../live-snapshot-provider';

function checkTime(value: string | null | undefined) {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value)) + ' IST';
}

export default function ReleaseMonitorPage() {
  const { snapshot } = useDashboardSnapshot();
  const rows = snapshot.release_monitor.map((row) => ({ ...row }));
  const known = new Set(rows.map((row) => String(row.dataset_code)));
  for (const [dataset, source] of Object.entries(snapshot.sources)) {
    if (!known.has(dataset)) rows.push({
      dataset_code: dataset,
      status: source.status,
      last_successful_period: source.last_successful_period,
      last_release_date: source.last_successful_period,
      cadence: dataset.includes('fii') ? 'daily (trading days)' : 'source-dependent',
      error_message: source.error,
    });
  }

  return (
    <div>
      <h2 className="section-title">Release Monitor</h2>
      <p className="muted">Source checks run daily at 20:30 IST. A successful check can retain the same reporting period when no newer release is available.</p>
      <div className="release-table-scroll"><table className="table">
        <thead>
          <tr>
            <th>Dataset</th><th>Status</th><th>Last available period</th><th>Last release date</th>
            <th>Cadence</th><th>Last source check</th><th>Last successful check</th><th>Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const source = snapshot.sources[String(row.dataset_code)];
            return (
              <tr key={String(row.dataset_code)}>
                <td>{row.dataset_code}</td>
                <td>{source?.status || row.status}</td>
                <td>{source?.last_successful_period || row.last_successful_period || '—'}</td>
                <td>{row.last_release_date || '—'}</td>
                <td>{row.cadence || '—'}</td>
                <td>{checkTime(source?.last_checked_at)}</td>
                <td>{checkTime(source?.last_success_at)}</td>
                <td>{source?.error || row.error_message || 'No source error reported.'}</td>
              </tr>
            );
          })}
        </tbody>
      </table></div>
    </div>
  );
}
