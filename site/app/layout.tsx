import './globals.css';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { LiveSnapshotProvider, SnapshotStatus } from './live-snapshot-provider';
import { getBundledSnapshot } from './lib/bundled-snapshot';

export const dynamic = 'force-static';

export const metadata = {
  title: 'World Metrics',
  description: 'India macro-industrial tracker and daily equity flows',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LiveSnapshotProvider initialSnapshot={getBundledSnapshot()}>
        <main>
          <h1>World Metrics</h1>
          <p className="muted">India macro-industrial indicators and daily equity flows.</p>
          <SnapshotStatus />
          <nav>
            <Link href="/">Overview</Link>
            <Link href="/power">Power</Link>
            <Link href="/construction">Construction</Link>
            <Link href="/demand">Demand</Link>
            <Link href="/inflation">Inflation</Link>
            <Link href="/release-monitor">Release Monitor</Link>
          </nav>
          {children}
        </main>
        </LiveSnapshotProvider>
      </body>
    </html>
  );
}
