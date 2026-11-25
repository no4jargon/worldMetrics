'use client';

import { useMemo, useState, type PointerEvent } from 'react';
import type { OverviewCard } from './lib/data';
import { formatAxisValue, periodTicks, valueTicks } from './lib/chart-axes';

type ChartPoint = { period: string; value: number };
type RangeKey = '10Y' | '5Y' | '3Y' | '1Y';

const RANGE_OPTIONS: Array<{ key: RangeKey; monthly: number; quarterly: number }> = [
  { key: '10Y', monthly: 120, quarterly: 40 },
  { key: '5Y', monthly: 60, quarterly: 20 },
  { key: '3Y', monthly: 36, quarterly: 12 },
  { key: '1Y', monthly: 12, quarterly: 4 },
];

function normalizeChartPoints(points: OverviewCard['sparkline']): ChartPoint[] {
  return points.map((point, index) => (
    typeof point === 'number' ? { period: String(index + 1), value: point } : point
  ));
}

function formatValue(value: number, unit: string) {
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`;
}

function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value) || !Number.isFinite(value)) {
    return '—';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function periodIndex(period: string, fallbackIndex: number, isQuarterly: boolean) {
  const monthly = period.match(/^(\d{4})-(\d{2})$/);
  if (monthly) {
    return Number(monthly[1]) * 12 + Number(monthly[2]) - 1;
  }
  const quarterly = period.match(/^(\d{4})-Q([1-4])$/);
  if (quarterly) {
    return Number(quarterly[1]) * 12 + (Number(quarterly[2]) - 1) * 3;
  }
  return fallbackIndex * (isQuarterly ? 3 : 1);
}

function yearsBetween(from: ChartPoint, to: ChartPoint, fromIndex: number, toIndex: number, isQuarterly: boolean) {
  const months = Math.abs(periodIndex(to.period, toIndex, isQuarterly) - periodIndex(from.period, fromIndex, isQuarterly));
  return months / 12;
}

function selectionStats(
  points: ChartPoint[],
  startIndex: number | null,
  endIndex: number | null,
  isQuarterly: boolean,
) {
  if (startIndex === null || endIndex === null || !points[startIndex] || !points[endIndex]) {
    return null;
  }

  const from = points[startIndex];
  const to = points[endIndex];
  const direct = from.value === 0 ? null : ((to.value / from.value) - 1) * 100;
  const years = yearsBetween(from, to, startIndex, endIndex, isQuarterly);
  const cagr = years <= 0 || from.value <= 0 || to.value <= 0
    ? null
    : (Math.pow(to.value / from.value, 1 / years) - 1) * 100;

  return { from, to, direct, cagr, years };
}

export function InteractiveCardChart({ points, unit }: { points: OverviewCard['sparkline']; unit: string }) {
  const allPoints = useMemo(() => normalizeChartPoints(points), [points]);
  const isQuarterly = allPoints.some((point) => point.period.includes('-Q'));
  const [range, setRange] = useState<RangeKey>('5Y');
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [selectionStartIndex, setSelectionStartIndex] = useState<number | null>(null);
  const [selectionEndIndex, setSelectionEndIndex] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const selectedOption = RANGE_OPTIONS.find((option) => option.key === range) || RANGE_OPTIONS[1];
  const windowSize = isQuarterly ? selectedOption.quarterly : selectedOption.monthly;
  const chartPoints = allPoints.slice(-windowSize);

  if (allPoints.length === 0) {
    return <div className="chart-empty">No chart data</div>;
  }

  const width = 360;
  const height = 164;
  const padding = { top: 16, right: 14, bottom: 34, left: 60 };
  const plotWidth = width - padding.left - padding.right;
  const plotBottom = height - padding.bottom;
  const plotHeight = plotBottom - padding.top;
  const values = chartPoints.map((point) => point.value);
  const scale = valueTicks(values);
  const tickStep = scale.ticks[1] - scale.ticks[0];
  const y = (value: number) => padding.top + (scale.max - value) / (scale.max - scale.min) * plotHeight;
  const xTicks = periodTicks(chartPoints.map((point) => point.period));
  const step = chartPoints.length > 1 ? plotWidth / (chartPoints.length - 1) : 0;
  const coordinates = chartPoints.map((point, index) => {
    const x = chartPoints.length === 1 ? padding.left + plotWidth / 2 : padding.left + index * step;
    return { x, y: y(point.value), point };
  });
  const polyline = coordinates.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const active = hoverIndex === null ? null : coordinates[hoverIndex];
  const selectedStart = selectionStartIndex === null ? null : coordinates[selectionStartIndex];
  const selectedEnd = selectionEndIndex === null ? null : coordinates[selectionEndIndex];
  const selectedStats = isDragging ? selectionStats(chartPoints, selectionStartIndex, selectionEndIndex, isQuarterly) : null;
  const selectionLeft = selectedStart && selectedEnd ? Math.min(selectedStart.x, selectedEnd.x) : 0;
  const selectionWidth = selectedStart && selectedEnd ? Math.abs(selectedEnd.x - selectedStart.x) : 0;
  const tooltipAnchor = selectedEnd || active;
  const tooltipLeft = tooltipAnchor ? Math.min(Math.max((tooltipAnchor.x / width) * 100, 8), 92) : 50;
  const tooltipPullLeft = tooltipAnchor ? tooltipAnchor.x > width * 0.62 : false;

  function nearestIndex(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * width;
    return Math.max(0, Math.min(coordinates.length - 1, Math.round((relativeX - padding.left) / (step || 1))));
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (coordinates.length === 0) return;
    const nearest = nearestIndex(event);
    setHoverIndex(nearest);
    if (isDragging) {
      setSelectionEndIndex(nearest);
    }
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (coordinates.length === 0) return;
    event.preventDefault();
    const nearest = nearestIndex(event);
    setHoverIndex(nearest);
    setSelectionStartIndex(nearest);
    setSelectionEndIndex(nearest);
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function clearSelection() {
    setSelectionStartIndex(null);
    setSelectionEndIndex(null);
    setIsDragging(false);
  }

  function handlePointerUp(event: PointerEvent<SVGSVGElement>) {
    if (!isDragging) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    clearSelection();
  }

  function selectRange(nextRange: RangeKey) {
    setRange(nextRange);
    setHoverIndex(null);
    setSelectionStartIndex(null);
    setSelectionEndIndex(null);
    setIsDragging(false);
  }

  return (
    <div className="interactive-chart">
      <div className="range-switcher" aria-label="Chart range">
        {RANGE_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={option.key === range ? 'active' : ''}
            onClick={() => selectRange(option.key)}
          >
            {option.key}
          </button>
        ))}
      </div>
      <svg
        className="mini-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${range} metric chart. Horizontal axis: reporting period. Vertical axis: ${unit}.`}
        onPointerMove={handlePointerMove}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={clearSelection}
        onPointerLeave={() => {
          setHoverIndex(null);
          if (isDragging) clearSelection();
        }}
      >
        <text x={padding.left - 8} y={10} textAnchor="end" className="chart-axis-unit">{unit === 'percent' ? '%' : unit}</text>
        {scale.ticks.map((value) => (
          <g key={value}>
            <line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} className="chart-grid-line" />
            <line x1={padding.left - 4} x2={padding.left} y1={y(value)} y2={y(value)} className="chart-axis-line" />
            <text x={padding.left - 8} y={y(value)} textAnchor="end" dominantBaseline="middle" className="chart-axis-label chart-y-tick">
              {formatAxisValue(value, unit, tickStep)}
            </text>
          </g>
        ))}
        <path d={`M ${padding.left} ${padding.top} V ${plotBottom} H ${width - padding.right}`} fill="none" className="chart-axis-line" />
        {xTicks.map(({ index, label }, tickIndex) => (
          <g key={index}>
            <line x1={coordinates[index].x} x2={coordinates[index].x} y1={plotBottom} y2={plotBottom + 4} className="chart-axis-line" />
            <text x={coordinates[index].x} y={plotBottom + 19} className="chart-axis-label chart-x-tick"
              textAnchor={xTicks.length === 1 ? 'middle' : tickIndex === 0 ? 'start' : tickIndex === xTicks.length - 1 ? 'end' : 'middle'}>{label}</text>
          </g>
        ))}
        {selectedStart && selectedEnd ? (
          <rect
            x={selectionLeft}
            y={padding.top}
            width={selectionWidth}
            height={plotHeight}
            className="selection-band"
          />
        ) : null}
        <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="2.5" />
        {coordinates.length === 1 ? <circle cx={coordinates[0].x} cy={coordinates[0].y} r="3" fill="currentColor" /> : null}
        {selectedStart ? (
          <line x1={selectedStart.x} x2={selectedStart.x} y1={padding.top} y2={plotBottom} className="selection-line" />
        ) : null}
        {selectedEnd ? (
          <line x1={selectedEnd.x} x2={selectedEnd.x} y1={padding.top} y2={plotBottom} className="selection-line end" />
        ) : null}
        {active ? (
          <>
            <line x1={active.x} x2={active.x} y1={padding.top} y2={plotBottom} className="hover-line" />
            <circle cx={active.x} cy={active.y} r="4" className="hover-dot" />
          </>
        ) : null}
      </svg>
      <div className="chart-readout">
        {active ? `${active.point.period}: ${formatValue(active.point.value, unit)}` : 'Hover for level. Click-drag to compare dates.'}
      </div>
      {selectedStats ? (
        <div
          className="selection-tooltip"
          style={{ left: `${tooltipLeft}%`, transform: tooltipPullLeft ? 'translateX(-100%)' : 'translateX(0)' }}
        >
          <strong>{selectedStats.from.period} → {selectedStats.to.period}</strong>
          <span>Δ {formatPercent(selectedStats.direct)}</span>
          <span>CAGR {formatPercent(selectedStats.cagr)}</span>
        </div>
      ) : null}
    </div>
  );
}
