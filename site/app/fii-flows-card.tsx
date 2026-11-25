'use client';

import { useId, useMemo, useState } from 'react';
import { formatAxisValue, periodTicks, valueTicks } from './lib/chart-axes';
import { useDashboardSnapshot } from './live-snapshot-provider';
import {
  isPartialFiiMonth, monthlyFiiFlows, normalizeFiiRecords,
  type FiiChartPoint,
} from './lib/fii-types';

type View = 'daily' | 'monthly';
type Range = '1M' | '3M' | '1Y' | 'All';

const numberFormat = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});
const monthFormat = new Intl.DateTimeFormat('en-GB', {
  month: 'short', year: 'numeric', timeZone: 'UTC',
});

function formatPeriod(period: string) {
  return period.length === 7
    ? monthFormat.format(new Date(`${period}-01T00:00:00Z`))
    : dateFormat.format(new Date(`${period}T00:00:00Z`));
}

function formatNet(value: number) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${numberFormat.format(Math.abs(value))}`;
}

function periodInRange(period: string, latest: string, range: Range) {
  if (range === 'All') return true;
  const months = range === '1M' ? 1 : range === '3M' ? 3 : 12;
  const end = new Date(`${latest.length === 7 ? `${latest}-01` : latest}T00:00:00Z`);
  const point = new Date(`${period.length === 7 ? `${period}-01` : period}T00:00:00Z`);
  // Monthly views include N calendar months. Daily views use a rolling date
  // window, without assuming a fixed number of trading days in a month.
  if (period.length === 10) {
    const threshold = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - months, 1));
    const lastDay = new Date(Date.UTC(threshold.getUTCFullYear(), threshold.getUTCMonth() + 1, 0)).getUTCDate();
    threshold.setUTCDate(Math.min(end.getUTCDate(), lastDay));
    return point >= threshold;
  }
  const firstMonth = end.getUTCFullYear() * 12 + end.getUTCMonth() - months + 1;
  return point.getUTCFullYear() * 12 + point.getUTCMonth() >= firstMonth;
}

function checkedTime(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Not checked yet';
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata',
  }).format(new Date(value)) + ' IST';
}

export function FiiFlowsCard() {
  const { snapshot } = useDashboardSnapshot();
  const data = snapshot.fii_flows;
  const [view, setView] = useState<View>('daily');
  const [range, setRange] = useState<Range>('1M');
  const [hovered, setHovered] = useState<string | null>(null);
  const titleId = useId();
  const chartTitleId = useId();
  const chartDescId = useId();
  const partialPatternId = useId();

  const records = useMemo(() => normalizeFiiRecords(data.records), [data.records]);
  const allPoints = useMemo<FiiChartPoint[]>(() => view === 'monthly'
    ? monthlyFiiFlows(records)
    : records.map((record) => ({ period: record.date, buy: record.buy, sell: record.sell, net: record.net, days: 1 })), [records, view]);
  const latest = records.at(-1);
  const lastPoint = allPoints.at(-1);
  const points = lastPoint ? allPoints.filter((point) => periodInRange(point.period, lastPoint.period, range)) : [];
  const selected = points.find((point) => point.period === hovered) || points.at(-1);
  const currentMonth = (data.last_success_at || snapshot.generated_at).slice(0, 7);
  const isMtd = (point: FiiChartPoint) => view === 'monthly' && point.period === currentMonth;
  const isPartialHistory = (point: FiiChartPoint) => view === 'monthly'
    && isPartialFiiMonth(point.period, {
      completeMonths: data.history_complete_months,
      incompleteMonths: data.history_incomplete_months,
      currentMonth,
    });
  const periodNote = (point: FiiChartPoint) => [
    isMtd(point) ? 'month to date' : null,
    isPartialHistory(point) ? 'partial history' : null,
  ].filter(Boolean).join(' · ');
  const publicationStatus = latest ? `Latest available published total · ${formatPeriod(latest.date)}` : 'No published totals available.';

  const width = 360;
  const height = 164;
  const padding = { top: 16, right: 14, bottom: 34, left: 60 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const { min, max, ticks: gridValues } = valueTicks(points.map((point) => point.net), { includeZero: true, count: 4 });
  const tickStep = gridValues.length > 1 ? gridValues[1] - gridValues[0] : 1;
  const dateTicks = periodTicks(points.map((point) => point.period), 4);
  const spread = max - min || 1;
  const y = (value: number) => padding.top + (max - value) / spread * plotHeight;
  const zeroY = y(0);
  const step = points.length ? plotWidth / points.length : plotWidth;
  const barWidth = Math.max(1, Math.min(38, step * 0.72));
  const plotBottom = height - padding.bottom;
  const x = (index: number) => padding.left + (index + 0.5) * step;

  return (
    <section className="card fii-card" aria-labelledby={titleId}>
      <div className="fii-heading">
        <div>
          <h3 id={titleId}>FII equity flows</h3>
        </div>
        <a className="badge source-badge" href={data.source_url} target="_blank" rel="noopener noreferrer">
          {data.source_name}{data.is_provisional ? ' · provisional' : ''} ↗
        </a>
      </div>

      <div className="fii-controls">
        <div className="range-switcher fii-view" role="group" aria-label="FII chart frequency">
          {(['daily', 'monthly'] as const).map((option) => (
            <button key={option} type="button" className={view === option ? 'active' : ''} aria-pressed={view === option}
              onClick={() => {
                setView(option);
                setHovered(null);
                if (view !== option) setRange(option === 'monthly' ? 'All' : '1M');
              }}>
              {option === 'daily' ? 'Daily' : 'Monthly'}
            </button>
          ))}
        </div>
        <div className="range-switcher" role="group" aria-label="FII chart date range">
          {(['1M', '3M', '1Y', 'All'] as const).map((option) => (
            <button key={option} type="button" className={range === option ? 'active' : ''} aria-pressed={range === option}
              onClick={() => { setRange(option); setHovered(null); }}>{option}</button>
          ))}
        </div>
      </div>

      {selected ? (
        <div className="fii-latest">
          <strong className={`metric ${selected.net < 0 ? 'fii-outflow' : 'fii-inflow'}`}>{formatNet(selected.net)} <span>₹ crore</span></strong>
          <span className="muted">{formatPeriod(selected.period)}{periodNote(selected) ? ` · ${periodNote(selected)}` : ''}</span>
        </div>
      ) : null}

      <p className="fii-publication" aria-live="polite" title={publicationStatus}>
        Latest available published data
      </p>
      {points.length ? (
        <>
          <svg className="fii-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${chartTitleId} ${chartDescId}`}
            onPointerLeave={() => setHovered(null)}>
            <title id={chartTitleId}>{`${view === 'daily' ? 'Daily' : 'Monthly'} net FII equity flows in ₹ crore`}</title>
            <desc id={chartDescId}>{`Bars above zero show net buying; bars below zero show net selling. ${points.length} observations from ${formatPeriod(points[0].period)} to ${formatPeriod(points[points.length - 1].period)}. Exact values are in the data table below.`}</desc>
            <defs>
              <pattern id={partialPatternId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="7" stroke="#fff4cc" strokeWidth="2" opacity="0.6" />
              </pattern>
            </defs>
            {gridValues.map((value) => (
              <g key={value}>
                <line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} className={value === 0 ? 'fii-zero-line' : 'chart-grid-line'} />
                <line x1={padding.left - 4} x2={padding.left} y1={y(value)} y2={y(value)} className="chart-axis-line" />
                <text x={padding.left - 8} y={y(value)} textAnchor="end" dominantBaseline="middle" className="chart-axis-label chart-y-tick">{formatAxisValue(value, undefined, tickStep)}</text>
              </g>
            ))}
            <text x={padding.left - 8} y={10} textAnchor="end" className="chart-axis-unit">₹ crore</text>
            <line x1={padding.left} x2={padding.left} y1={padding.top} y2={plotBottom} className="chart-axis-line" />
            <line x1={padding.left} x2={width - padding.right} y1={plotBottom} y2={plotBottom} className="chart-axis-line" />
            {points.map((point, index) => {
              const barX = padding.left + index * step + (step - barWidth) / 2;
              const barY = Math.min(y(point.net), zeroY);
              return (
                <g key={point.period}>
                  <rect x={barX} y={barY} width={barWidth} height={Math.max(1, Math.abs(y(point.net) - zeroY))}
                    className={`${point.net < 0 ? 'fii-bar-out' : 'fii-bar-in'}${selected?.period === point.period ? ' fii-bar-selected' : ''}`}>
                    <title>{`${formatPeriod(point.period)}${periodNote(point) ? ` (${periodNote(point)})` : ''}: ${formatNet(point.net)} ₹ crore`}</title>
                  </rect>
                  {isPartialHistory(point) ? <rect x={barX} y={barY} width={barWidth}
                    height={Math.max(1, Math.abs(y(point.net) - zeroY))} fill={`url(#${partialPatternId})`} pointerEvents="none" /> : null}
                  <rect x={padding.left + index * step} y={padding.top} width={step} height={plotHeight}
                    fill="transparent" onPointerEnter={() => setHovered(point.period)} onPointerMove={() => setHovered(point.period)} />
                </g>
              );
            })}
            {dateTicks.map((tick, index) => (
              <g key={tick.index}>
                <line x1={x(tick.index)} x2={x(tick.index)} y1={plotBottom} y2={plotBottom + 4} className="chart-axis-line" />
                <text x={x(tick.index)} y={plotBottom + 18} textAnchor={dateTicks.length === 1 ? 'middle' : index === 0 ? 'start' : index === dateTicks.length - 1 ? 'end' : 'middle'} className="chart-axis-label chart-x-tick">{tick.label}</text>
              </g>
            ))}
          </svg>
        </>
      ) : <div className="chart-empty fii-empty">No published FII totals available.</div>}

      {data.error ? <p className="fii-warning" role="status">{records.length ? 'Showing saved figures; see the source note below.' : 'Source unavailable; showing the latest available figures.'}</p> : null}
      <details className="fii-details">
        <summary>Details &amp; data</summary>
        <p className="muted fii-note">{publicationStatus}</p>
        {points.length ? (
        <>
          <div className="fii-readout" aria-live="polite">
            {selected ? <><strong>{formatPeriod(selected.period)}{periodNote(selected) ? ` · ${periodNote(selected)}` : ''}</strong><span>Net <b className={selected.net < 0 ? 'fii-outflow' : 'fii-inflow'}>{formatNet(selected.net)}</b></span><span>Buy {numberFormat.format(selected.buy)}</span><span>Sell {numberFormat.format(selected.sell)}</span><span>₹ crore</span></> : null}
          </div>
          <p className="muted fii-note">Positive = net buying; negative = net selling. {view === 'monthly' ? 'Monthly totals sum available daily records; the latest month may be incomplete as of its source check.' : 'One observation per published trading day. Weekends, holidays and unpublished days are not filled with zero.'}</p>
          {points.some(isPartialHistory) ? <p className="muted fii-note">Hatched bars show partial historical totals with missing or unverified sessions.</p> : null}
          <div className="fii-data-table">
            <div className="fii-table-scroll">
              <table className="table">
                <caption>FII equity flows in ₹ crore{view === 'monthly' ? ', summed from available daily records' : ''}</caption>
                <thead><tr><th scope="col">{view === 'daily' ? 'Date' : 'Month'}</th><th scope="col">Buy</th><th scope="col">Sell</th><th scope="col">Net</th>{view === 'monthly' ? <th scope="col">Days reported</th> : null}</tr></thead>
                <tbody>{[...points].reverse().map((point) => (
                  <tr key={point.period}><th scope="row">{formatPeriod(point.period)}{periodNote(point) ? ` · ${periodNote(point)}` : ''}</th><td>{numberFormat.format(point.buy)}</td><td>{numberFormat.format(point.sell)}</td><td><span className={point.net < 0 ? 'fii-outflow' : 'fii-inflow'}>{formatNet(point.net)}</span></td>{view === 'monthly' ? <td>{point.days}</td> : null}</tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </>
        ) : null}
      <p className="muted fii-note"><a download="fii-flows.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(data, null, 2))}`}>Download current FII data (JSON)</a></p>
      {data.history_note ? <p className="muted fii-note">{data.history_note}</p> : null}
      {data.history_source_url ? <p className="muted fii-note"><a href={data.history_source_url} target="_blank" rel="noopener noreferrer">Historical daily figures: {data.history_source_name || 'data source'} ↗</a></p> : null}
      <div className="fii-footer"><span>{data.scope}</span><span>Checked {checkedTime(data.last_checked_at)}</span></div>
      </details>
    </section>
  );
}
