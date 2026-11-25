import { MetricPanel } from '../components';

export default function ConstructionPage() {
  return (
    <div className="list">
      <h2 className="section-title">Construction</h2>
      <MetricPanel title="Cement output" metricCode="cement_output" transform="level" />
      <MetricPanel title="Cement output YoY" metricCode="cement_output" transform="yoy" />
      <MetricPanel title="Home sales" metricCode="home_sales_jll" transform="level" />
    </div>
  );
}
