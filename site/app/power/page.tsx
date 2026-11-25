import { MetricPanel } from '../components';

export default function PowerPage() {
  return (
    <div className="list">
      <h2 className="section-title">Power</h2>
      <MetricPanel title="Power output" metricCode="power_output_total" transform="level" />
      <MetricPanel title="Power output YoY" metricCode="power_output_total" transform="yoy" />
      <MetricPanel title="Thermal PLF" metricCode="power_utilization_plf" transform="rolling_3p_avg" />
    </div>
  );
}
