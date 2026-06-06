import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const statusPath = path.join(process.cwd(), 'data', 'refresh-status.json');
  if (!existsSync(statusPath)) {
    return NextResponse.json(
      { status: 'not_started', message: 'No refresh status file yet.' },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  }

  return NextResponse.json(JSON.parse(readFileSync(statusPath, 'utf8')), {
    headers: { 'Cache-Control': 'no-store' },
  });
}
