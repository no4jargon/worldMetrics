import { MetricPanel } from '../components';

export default function DemandPage() {
  return (
    <div className="list">
      <h2 className="section-title">Demand</h2>
      <MetricPanel title="Monthly two-wheeler sales" metricCode="two_wheeler_sales" transform="level" />
      <MetricPanel title="Monthly two-wheeler sales YoY" metricCode="two_wheeler_sales" transform="yoy" />
      <MetricPanel title="Monthly four-wheeler sales" metricCode="four_wheeler_sales" transform="level" />
      <MetricPanel title="Monthly four-wheeler sales YoY" metricCode="four_wheeler_sales" transform="yoy" />
    </div>
  );
}
