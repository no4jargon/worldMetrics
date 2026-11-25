import { OverviewCardView } from './components';
import { RefreshStatusPanel } from './refresh-status-panel';
import { getOverview, getRefreshStatus } from './lib/data';
import { FiiFlowsCard } from './fii-flows-card';
import { getFiiFlows } from './lib/fii-data';

export default function OverviewPage() {
  const overview = getOverview();
  const refreshStatus = getRefreshStatus();
  const fiiFlows = getFiiFlows();

  return (
    <div>
      <h2 className="section-title">Overview</h2>
      <RefreshStatusPanel initialStatus={refreshStatus} />
      <p>{overview.summary}</p>
      <div className="card-grid">
        <FiiFlowsCard initialData={fiiFlows} />
        {overview.cards.map((card) => <OverviewCardView key={card.metric_code} card={card} />)}
      </div>
    </div>
  );
}
