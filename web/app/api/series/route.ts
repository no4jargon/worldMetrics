import { NextRequest, NextResponse } from 'next/server';
import { getSeries } from '../../lib/data';

export async function GET(request: NextRequest) {
  const metric = request.nextUrl.searchParams.get('metric');
  const transform = request.nextUrl.searchParams.get('transform') || 'level';

  if (!metric) {
    return NextResponse.json({ error: 'metric is required' }, { status: 400 });
  }

  const payload = getSeries(metric, transform);
  if (!payload) {
    return NextResponse.json({ error: 'series not found' }, { status: 404 });
  }

  return NextResponse.json(payload);
}
