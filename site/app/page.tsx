'use client';

import { OverviewCardView } from './components';
import { FiiFlowsCard } from './fii-flows-card';
import { useDashboardSnapshot } from './live-snapshot-provider';

export default function OverviewPage() {
  const { snapshot } = useDashboardSnapshot();
  return (
    <div>
      <h2 className="section-title">Overview</h2>
      <p>{snapshot.overview.summary}</p>
      <div className="card-grid">
        <FiiFlowsCard />
        {snapshot.overview.cards.map((card) => <OverviewCardView key={card.metric_code} card={card} />)}
      </div>
    </div>
  );
}
