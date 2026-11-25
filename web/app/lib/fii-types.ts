export type FiiFlowRecord = {
  date: string;
  buy: number;
  sell: number;
  net: number;
};

export type FiiFlowsPayload = {
  records: FiiFlowRecord[];
  source_name: string;
  source_url: string;
  scope: string;
  is_provisional: boolean;
  last_checked_at: string | null;
  last_success_at: string | null;
  error: string | null;
  status: 'available' | 'unavailable' | 'refreshing';
  history_note?: string | null;
  history_source_url?: string | null;
  history_source_name?: string | null;
  history_start_month?: string | null;
  history_complete_months?: string[] | null;
  history_incomplete_months?: string[] | null;
  refreshing?: boolean;
};

export type FiiChartPoint = {
  period: string;
  buy: number;
  sell: number;
  net: number;
  days: number;
};

export function normalizeFiiRecords(records: FiiFlowRecord[]): FiiFlowRecord[] {
  const byDate = new Map<string, FiiFlowRecord>();
  for (const record of records) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(record.date)
      || ![record.buy, record.sell, record.net].every(Number.isFinite)) continue;
    const parsedDate = new Date(`${record.date}T00:00:00Z`);
    if (!Number.isFinite(parsedDate.valueOf()) || parsedDate.toISOString().slice(0, 10) !== record.date) continue;
    byDate.set(record.date, record);
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function monthlyFiiFlows(records: FiiFlowRecord[]): FiiChartPoint[] {
  const months = new Map<string, FiiChartPoint>();
  for (const record of normalizeFiiRecords(records)) {
    const period = record.date.slice(0, 7);
    const month = months.get(period) || { period, buy: 0, sell: 0, net: 0, days: 0 };
    month.buy += record.buy;
    month.sell += record.sell;
    month.net += record.net;
    month.days += 1;
    months.set(period, month);
  }
  return [...months.values()].map((month) => ({
    ...month,
    buy: Math.round(month.buy * 100) / 100,
    sell: Math.round(month.sell * 100) / 100,
    net: Math.round(month.net * 100) / 100,
  }));
}

export function indiaToday(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function fiiRefreshDelay(payload: Pick<FiiFlowsPayload, 'status' | 'refreshing'>): number {
  return payload.status === 'refreshing' || payload.refreshing ? 5_000 : 60_000;
}

export function isPartialFiiMonth(month: string, coverage: {
  completeMonths?: string[] | null;
  incompleteMonths?: string[] | null;
  currentMonth?: string;
} = {}): boolean {
  if (coverage.incompleteMonths?.includes(month)) return true;
  if (coverage.completeMonths?.includes(month)) return false;
  // A successful source request does not establish complete monthly coverage.
  // Unknown historical coverage remains partial. Current-month observations
  // already carry the MTD label unless the source identifies missing days.
  return month !== coverage.currentMonth;
}
