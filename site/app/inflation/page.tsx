import { MetricPanel } from '../components';

export default function InflationPage() {
  return (
    <div className="list">
      <h2 className="section-title">Inflation</h2>
      <p className="muted">Base year can change over time. Keep CPI metadata source-aware.</p>
      <MetricPanel title="CPI headline inflation" metricCode="cpi_headline" transform="level" />
      <MetricPanel title="CPI index" metricCode="cpi_index" transform="level" />
    </div>
  );
}
