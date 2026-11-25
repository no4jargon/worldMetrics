import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { FiiFlowsPayload } from './fii-types';

export function getFiiFlows(): FiiFlowsPayload {
  const data = JSON.parse(readFileSync(path.join(process.cwd(), 'data', 'fii-flows.json'), 'utf8')) as FiiFlowsPayload;
  return { ...data, refreshing: false };
}
