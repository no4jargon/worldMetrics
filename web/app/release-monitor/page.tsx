import { getReleaseMonitor } from '../lib/data';

export default function ReleaseMonitorPage() {
  const rows = getReleaseMonitor();

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
