import './globals.css';
import Link from 'next/link';
import type { ReactNode } from 'react';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'World Metrics',
  description: 'India monthly macro-industrial tracker',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>
          <h1>World Metrics</h1>
          <p className="muted">A monthly macro-industrial tracker for India.</p>
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
