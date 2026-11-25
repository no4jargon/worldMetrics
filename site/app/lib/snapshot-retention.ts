import type { SnapshotBundle } from './live-snapshot';

function periodOrder(period: string | null | undefined): number {
  if (!period) return -Infinity;
  const quarter = period.match(/^(\d{4})-Q([1-4])$/);
  if (quarter) return Date.UTC(Number(quarter[1]), (Number(quarter[2]) - 1) * 3, 1);
  if (/^\d{4}$/.test(period)) return Date.UTC(Number(period), 0, 1);
  return Date.parse(`${period.length === 7 ? `${period}-01` : period}T00:00:00Z`);
}

/** Failed cloud checks may still carry data newer than the build-time fallback. */
export function retainLatestSnapshot(current: SnapshotBundle, incoming: SnapshotBundle): SnapshotBundle {
  if (incoming.update_status !== 'failed') return incoming;
  const successTime = (value: string | null) => value ? Date.parse(value) : -Infinity;
  const cards = new Map(incoming.overview.cards.map((card) => [card.metric_code, card]));
  const cardsDoNotRegress = current.overview.cards.every((card) =>
    card.latest_period === null || periodOrder(cards.get(card.metric_code)?.latest_period) >= periodOrder(card.latest_period));
  const seriesDoNotRegress = Object.entries(current.series).every(([metric, transforms]) =>
    Object.entries(transforms).every(([transform, payload]) =>
      periodOrder(incoming.series[metric]?.[transform]?.points?.at(-1)?.period)
        >= periodOrder(payload.points?.at(-1)?.period)));
  const fiiDoesNotRegress = periodOrder(incoming.fii_flows.records.at(-1)?.date)
    >= periodOrder(current.fii_flows.records.at(-1)?.date);
  if (successTime(incoming.last_success_at) >= successTime(current.last_success_at)
    && cardsDoNotRegress && seriesDoNotRegress && fiiDoesNotRegress) return incoming;
  return {
    ...incoming,
    last_success_at: successTime(incoming.last_success_at) >= successTime(current.last_success_at)
      ? incoming.last_success_at : current.last_success_at,
    overview: current.overview,
    series: current.series,
    release_monitor: current.release_monitor,
    fii_flows: current.fii_flows,
  };
}
