import Link from 'next/link';
import { InteractiveCardChart } from './interactive-card-chart';
import { getSeries, type OverviewCard } from './lib/data';

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
  const payload = getSeries(metricCode, transform) as { points?: Array<{ period: string; value: number }>; source?: string; status?: string; status_note?: string | null; retrieval_skill?: string | null; source_url?: string | null } | null;
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
      {payload?.retrieval_skill ? <p className="muted">Auto-called skill: /skill:{payload.retrieval_skill}</p> : null}
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
      <p className="muted"><Link href={`/api/series?metric=${metricCode}&transform=${transform}`}>API payload</Link></p>
    </section>
  );
}
