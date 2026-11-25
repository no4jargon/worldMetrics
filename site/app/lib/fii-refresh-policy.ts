import type { FiiFlowsPayload } from './fii-types';

const MINUTE = 60_000;

export function indiaDate(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

export function shouldRefreshFii(
  data: Pick<FiiFlowsPayload, 'last_checked_at' | 'error'>,
  now = new Date(),
  lastAttemptAt = 0,
): boolean {
  if (now.getTime() - lastAttemptAt < MINUTE) return false;
  const checked = data.last_checked_at ? new Date(data.last_checked_at) : null;
  if (!checked || !Number.isFinite(checked.getTime())) return true;
  const age = now.getTime() - checked.getTime();
  if (age < -5 * MINUTE || indiaDate(checked) !== indiaDate(now)) return true;

  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now);
  const part = (name: string) => parts.find((item) => item.type === name)?.value || '';
  const weekday = !['Sat', 'Sun'].includes(part('weekday'));
  const minutes = Number(part('hour')) * 60 + Number(part('minute'));
  const interval = data.error ? 5 * MINUTE : weekday && minutes >= 15 * 60 + 30 ? 15 * MINUTE : 6 * 60 * MINUTE;
  return age >= interval;
}
