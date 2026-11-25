import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const target = path.join(root, 'public/data');
await mkdir(target, { recursive: true });
for (const name of ['overview', 'release-monitor', 'fii-flows']) {
  const contents = await readFile(path.join(root, 'data', `${name}.json`), 'utf8');
  if (contents.includes('/Users/')) throw new Error(`Local path in ${name} snapshot`);
  await writeFile(path.join(target, `${name}.json`), contents);
}
const series = JSON.parse(await readFile(path.join(root, 'data/series.json'), 'utf8'));
for (const [metric, transforms] of Object.entries(series)) {
  if (!/^[a-z0-9_]+$/.test(metric)) throw new Error('Invalid metric name');
  const directory = path.join(target, 'series', metric);
  await mkdir(directory, { recursive: true });
  for (const [transform, payload] of Object.entries(transforms)) {
    if (!/^[a-z0-9_]+$/.test(transform)) throw new Error('Invalid transform name');
    const contents = JSON.stringify(payload, null, 2) + '\n';
    if (contents.includes('/Users/')) throw new Error(`Local path in ${metric}`);
    await writeFile(path.join(directory, `${transform}.json`), contents);
  }
}
