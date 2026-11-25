/** Shared scales and labels for the small dashboard charts. */
export function valueTicks(values: number[], { includeZero = false, count = 4 }: { includeZero?: boolean; count?: number } = {}) {
  const finite = values.filter(Number.isFinite);
  let min = finite.length ? Math.min(...finite) : 0;
  let max = finite.length ? Math.max(...finite) : 1;
  if (includeZero) { min = Math.min(0, min); max = Math.max(0, max); }
  if (min === max) {
    const padding = Math.abs(min) * 0.05 || 1;
    min -= padding;
    max += padding;
  }
  const roughStep = (max - min) / Math.max(1, count - 1);
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const step = ([1, 2, 2.5, 5, 10].find((n) => n * magnitude >= roughStep) || 10) * magnitude;
  // Round floating point noise away without truncating small decimal scales.
  const clean = (n: number) => Number(n.toPrecision(12));
  const low = Math.floor(min / step);
  const high = Math.ceil(max / step);
  const ticks = Array.from({ length: high - low + 1 }, (_, i) => clean((low + i) * step));
  return { min: ticks[0], max: ticks[ticks.length - 1], ticks };
}

export function formatAxisValue(value: number, unit = '', step?: number) {
  const magnitude = Math.abs(value);
  const scale = magnitude >= 1e9 ? 1e9 : magnitude >= 1e6 ? 1e6 : magnitude >= 1e3 ? 1e3 : 1;
  const suffix = scale === 1e9 ? 'B' : scale === 1e6 ? 'M' : scale === 1e3 ? 'k' : '';
  const precision = step
    ? Math.min(8, Math.max(0, Math.ceil(-Math.log10(Math.abs(step / scale))) + 1))
    : 2;
  const label = (Object.is(value, -0) ? 0 : value / scale).toLocaleString('en-GB', { maximumFractionDigits: precision });
  return `${label}${suffix}${unit === 'percent' || unit === '%' ? '%' : ''}`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function periodTicks(periods: string[], maxTicks = 4): Array<{ index: number; label: string }> {
  if (!periods.length) return [];
  const first = periods[0];
  const last = periods[periods.length - 1];
  const daily = /^\d{4}-\d{2}-\d{2}$/.test(first);
  const monthly = /^\d{4}-\d{2}$/.test(first);
  const quarterly = /^\d{4}-Q[1-4]$/.test(first);
  const spanMonths = (Number(last.slice(0, 4)) - Number(first.slice(0, 4))) * 12
    + (daily || monthly ? Number(last.slice(5, 7)) - Number(first.slice(5, 7)) : 0);
  const annualLabels = (monthly && spanMonths >= 30) || (quarterly && periods.length >= 12);
  const dailyMonthLabels = daily && spanMonths >= 4;
  // Prefer calendar boundaries on long histories, retaining both endpoints.
  let candidates = periods.map((_, index) => index);
  if (annualLabels || dailyMonthLabels) {
    candidates = candidates.filter((index) => index === 0 || index === periods.length - 1
      || (dailyMonthLabels ? periods[index].slice(0, 7) !== periods[index - 1].slice(0, 7)
        : quarterly ? periods[index].endsWith('-Q1') : periods[index].endsWith('-01')));
  }
  // Full daily dates need more space than month or quarter labels.
  const limit = Math.max(2, Math.min(maxTicks, daily && !dailyMonthLabels ? 3 : maxTicks));
  const labelAt = (index: number) => {
    const period = periods[index];
    const shortYear = `’${period.slice(2, 4)}`;
    let label = period;
    if (daily) {
      const month = MONTHS[Number(period.slice(5, 7)) - 1];
      label = dailyMonthLabels ? `${month} ${shortYear}` : `${Number(period.slice(8, 10))} ${month} ${shortYear}`;
    } else if (monthly) {
      label = annualLabels && index !== 0 && index !== periods.length - 1
        ? period.slice(0, 4) : `${MONTHS[Number(period.slice(5, 7)) - 1]} ${shortYear}`;
    } else if (quarterly) {
      label = annualLabels && index !== 0 && index !== periods.length - 1
        ? period.slice(0, 4) : `${period.slice(5)} ${shortYear}`;
    }
    return { index, label };
  };
  // SVG labels use a 12px monospace font in a 286-unit plot. Reduce density
  // until endpoint labels and centered interior labels have breathing room.
  // Sampling again (rather than deleting a tick) keeps the remaining spacing even.
  for (let count = Math.min(limit, candidates.length); count >= 1; count--) {
    const indices = candidates.length <= count ? candidates
      : Array.from({ length: count }, (_, i) => candidates[Math.round(i * (candidates.length - 1) / (count - 1))]);
    const ticks = indices.map(labelAt);
    let previousRight = -Infinity;
    const fits = ticks.every((tick, i) => {
      const x = periods.length > 1 ? tick.index / (periods.length - 1) * 286 : 143;
      const width = tick.label.length * 7.2;
      const left = ticks.length === 1 ? x - width / 2 : i === 0 ? x : i === ticks.length - 1 ? x - width : x - width / 2;
      const separated = left >= previousRight + 8;
      previousRight = left + width;
      return separated;
    });
    if (fits || count <= 2) return ticks;
  }
  return [];
}
