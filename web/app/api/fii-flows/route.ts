import { NextResponse } from 'next/server';
import { getFiiFlows } from '../../lib/fii-data';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET() {
  return NextResponse.json(getFiiFlows(), { headers: { 'Cache-Control': 'no-store, max-age=0' } });
}
