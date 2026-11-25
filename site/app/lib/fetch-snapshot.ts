import { validateSnapshot, type SnapshotBundle } from './live-snapshot';

export const LIVE_SNAPSHOT_URL = 'https://raw.githubusercontent.com/no4jargon/worldMetrics/main/published-data/snapshot.json';
export const SNAPSHOT_API_URL = 'https://api.github.com/repos/no4jargon/worldMetrics/contents/published-data/snapshot.json';
export const SNAPSHOT_CHECK_INTERVAL_MS = 15 * 60 * 1000;
const MAX_SNAPSHOT_BYTES = 3 * 1024 * 1024;

async function readBoundedResponse(response: Response): Promise<string> {
  const declaredSize = Number(response.headers.get('content-length'));
  if (Number.isFinite(declaredSize) && declaredSize > MAX_SNAPSHOT_BYTES) {
    await response.body?.cancel();
    throw new Error('Update exceeds size limit');
  }
  if (!response.body) throw new Error('Update has no body');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0;
  let text = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_SNAPSHOT_BYTES) { await reader.cancel(); throw new Error('Update exceeds size limit'); }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally {
    reader.releaseLock();
  }
}

type FetchOptions = {
  signal?: AbortSignal;
  now?: Date;
  fetcher?: typeof fetch;
  /** Injectable only to make timeout and abort behavior deterministic in tests. */
  timeouts?: readonly [number, number];
};

/** Both public endpoints serve the same atomic bundle; neither needs credentials. */
export async function fetchPublishedSnapshot(previous: SnapshotBundle, {
  signal, now = new Date(), fetcher = fetch, timeouts = [6_000, 10_000],
}: FetchOptions = {}): Promise<SnapshotBundle> {
  const window = Math.floor(now.valueOf() / SNAPSHOT_CHECK_INTERVAL_MS);
  const endpoints = [
    { url: `${LIVE_SNAPSHOT_URL}?window=${window}`, headers: undefined },
    { url: `${SNAPSHOT_API_URL}?ref=main&window=${window}`, headers: { Accept: 'application/vnd.github.raw+json' } },
  ];
  for (const [index, endpoint] of endpoints.entries()) {
    if (signal?.aborted) throw new DOMException('Source check was cancelled', 'AbortError');
    const controller = new AbortController();
    const cancel = () => controller.abort();
    signal?.addEventListener('abort', cancel, { once: true });
    const timeout = setTimeout(cancel, timeouts[index]);
    try {
      const response = await fetcher(endpoint.url, {
        cache: 'no-store', credentials: 'omit', signal: controller.signal, headers: endpoint.headers,
      });
      if (!response.ok) throw new Error('Published update unavailable');
      const text = await readBoundedResponse(response);
      if (controller.signal.aborted) throw new DOMException('Source check was cancelled', 'AbortError');
      return validateSnapshot(JSON.parse(text), now, previous);
    } catch {
      controller.abort();
      if (signal?.aborted) throw new DOMException('Source check was cancelled', 'AbortError');
      // Try the independent public content endpoint after an unavailable,
      // invalid or slow CDN response. The caller reports only a total failure.
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', cancel);
    }
  }
  throw new Error('Published update unavailable from both public endpoints');
}
