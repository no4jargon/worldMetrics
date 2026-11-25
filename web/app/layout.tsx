import './globals.css';
import Link from 'next/link';
import type { ReactNode } from 'react';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'World Metrics',
  description: 'India macro-industrial tracker and daily equity flows',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>
          <h1>World Metrics</h1>
          <p className="muted">India macro-industrial indicators and daily equity flows.</p>
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
      </body>
    </html>
  );
}
