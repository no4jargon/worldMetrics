'use client';

import { useDashboardSnapshot } from './live-snapshot-provider';
import type { SeriesPayload } from './lib/live-snapshot';
import { InteractiveCardChart } from './interactive-card-chart';
import type { OverviewCard } from './lib/data';

export function OverviewCardView({ card }: { card: OverviewCard }) {
  return (
    <div className="card">
      <h3>{card.title}</h3>
      {card.source_url ? (
        <a className="badge source-badge" href={card.source_url} target="_blank" rel="noopener noreferrer" title={`Open source for ${card.title}`}>
          {card.source} ↗
        </a>
      ) : (
        <div className="badge">{card.source}</div>
      )}
      <InteractiveCardChart points={card.sparkline} unit={card.unit} />
      <div className="card-field"><span>Unit</span><strong>{card.unit}</strong></div>
      <div className="card-field"><span>Retrieved for</span><strong>{card.latest_retrieved_for ?? card.latest_period ?? '—'}</strong></div>
      <div className="card-field"><span>YoY</span><strong>{card.change_yoy === null ? '—' : `${card.change_yoy}%`}</strong></div>
    </div>
  );
}

export function MetricPanel({ title, metricCode, transform = 'level' }: { title: string; metricCode: string; transform?: string }) {
  const { snapshot } = useDashboardSnapshot();
  const payload: SeriesPayload | null = snapshot.series[metricCode]?.[transform] || null;
  const points = payload?.points || [];
  const isMissing = !payload || payload.status === 'missing' || points.length === 0;

  return (
    <section className="panel">
      <div className="badge">{isMissing ? 'Missing connector/data' : payload?.source || 'Unknown source'}</div>
      <h2>
        {payload?.source_url ? (
          <a href={payload.source_url} target="_blank" rel="noopener noreferrer" title={`Open source for ${title}`}>
            {title} ↗
          </a>
        ) : (
          title
        )}
      </h2>
      <p className="muted">Transform: {transform}</p>
      {isMissing ? (
        <p>{payload?.status_note || 'No series data available for this metric/transform.'}</p>
      ) : (
        <div className="list">
          {points.map((point) => (
            <div key={point.period}>
              <strong>{point.period}</strong>: {point.value}
            </div>
          ))}
        </div>
      )}
      <p className="muted"><a download={`${metricCode}-${transform}.json`} href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(payload, null, 2))}`}>Download current data (JSON)</a></p>
    </section>
  );
}
