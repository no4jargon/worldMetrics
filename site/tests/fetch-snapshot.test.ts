import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fetchPublishedSnapshot, LIVE_SNAPSHOT_URL, SNAPSHOT_API_URL } from '../app/lib/fetch-snapshot';
import type { SnapshotBundle } from '../app/lib/live-snapshot';

const NOW = new Date('2026-11-25T10:00:00Z');
function fixture(): SnapshotBundle {
  const read = (name: string) => JSON.parse(readFileSync(path.join(process.cwd(), 'data', `${name}.json`), 'utf8'));
  return {
    schema_version: 1, generated_at: '2026-11-18T13:00:00Z', last_attempt_at: '2026-11-18T13:00:00Z',
    last_success_at: '2026-11-18T13:00:00Z', update_status: 'partial', overview: read('overview'),
    series: read('series'), release_monitor: read('release-monitor'), fii_flows: read('fii-flows'), sources: {},
  };
}

function published(data = fixture()) { return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } }); }

test('uses raw public data without credentials or a second request when valid', async () => {
  const calls: Array<[string, RequestInit | undefined]> = [];
  const fetcher: typeof fetch = async (url, init) => { calls.push([String(url), init]); return published(); };
  const data = await fetchPublishedSnapshot(fixture(), { now: NOW, fetcher });
  assert.equal(data.schema_version, 1);
  assert.equal(calls.length, 1);
  assert.ok(calls[0][0].startsWith(`${LIVE_SNAPSHOT_URL}?window=`));
  assert.equal(calls[0][1]?.credentials, 'omit');
  assert.equal(calls[0][1]?.cache, 'no-store');
});

test('falls back to the public content API after missing, invalid or oversized raw data', async () => {
  for (const bad of [() => new Response('', { status: 503 }), () => new Response('{"schema_version":2}'),
    () => new Response('x', { headers: { 'Content-Length': String(4 * 1024 * 1024) } })]) {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetcher: typeof fetch = async (url, init) => { calls.push([String(url), init]); return calls.length === 1 ? bad() : published(); };
    await fetchPublishedSnapshot(fixture(), { now: NOW, fetcher });
    assert.equal(calls.length, 2);
    assert.ok(calls[1][0].startsWith(`${SNAPSHOT_API_URL}?ref=main&window=`));
    assert.equal(new Headers(calls[1][1]?.headers).get('Accept'), 'application/vnd.github.raw+json');
    assert.equal(new URL(calls[0][0]).searchParams.get('window'), new URL(calls[1][0]).searchParams.get('window'));
    assert.equal(calls[1][1]?.credentials, 'omit');
  }
});

test('raw timeout aborts only that endpoint and the API request has an independent signal', async () => {
  const signals: AbortSignal[] = [];
  const fetcher: typeof fetch = async (_url, init) => {
    const signal = init!.signal!;
    signals.push(signal);
    if (signals.length === 1) return new Promise<Response>((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('timed out')), { once: true }));
    return published();
  };
  await fetchPublishedSnapshot(fixture(), { now: NOW, fetcher, timeouts: [5, 50] });
  assert.equal(signals.length, 2);
  assert.equal(signals[0].aborted, true);
  assert.equal(signals[1].aborted, false);
  await new Promise((resolve) => setTimeout(resolve, 55));
  assert.equal(signals[1].aborted, false, 'successful request timer was cleared');
});

test('unmount cancellation aborts the active endpoint without starting a fallback', async () => {
  const controller = new AbortController();
  let calls = 0;
  const fetcher: typeof fetch = async (_url, init) => {
    calls++;
    return new Promise<Response>((_resolve, reject) => init!.signal!.addEventListener('abort', () => reject(new Error('cancelled')), { once: true }));
  };
  const pending = fetchPublishedSnapshot(fixture(), { now: NOW, fetcher, signal: controller.signal, timeouts: [100, 100] });
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(calls, 1);
});

test('reports total failure only after both endpoints fail validation or transport', async () => {
  let calls = 0;
  const fetcher: typeof fetch = async () => { calls++; return new Response('{}'); };
  await assert.rejects(fetchPublishedSnapshot(fixture(), { now: NOW, fetcher }), /both public endpoints/);
  assert.equal(calls, 2);
});
