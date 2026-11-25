import { getReleaseMonitor } from '../lib/data';
import { getFiiFlows } from '../lib/fii-data';

export default function ReleaseMonitorPage() {
  const rows = getReleaseMonitor();
  const fii = getFiiFlows();
  const latestFiiDate = fii.records.at(-1)?.date;
  rows.push({
    dataset_code: 'nse_fii_equity_flows',
    status: fii.error ? (fii.records.length ? 'cached / refresh failed' : 'failed') : fii.refreshing ? 'refreshing' : fii.status,
    last_successful_period: latestFiiDate || '—',
    last_release_date: latestFiiDate || '—',
    cadence: 'daily (trading days)',
    next_expected_window: 'After the next trading session; publication time varies',
    error_message: fii.error || 'Provisional combined cash-market flows in ₹ crore.',
  });

  return (
    <div>
      <h2 className="section-title">Release Monitor</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Status</th>
            <th>Last successful period</th>
            <th>Last release date</th>
            <th>Cadence</th>
            <th>Next expected window</th>
            <th>Error / note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.dataset_code)}>
              <td>{row.dataset_code}</td>
              <td>{row.status}</td>
              <td>{row.last_successful_period}</td>
              <td>{row.last_release_date}</td>
              <td>{row.cadence}</td>
              <td>{row.next_expected_window}</td>
              <td>{row.error_message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
