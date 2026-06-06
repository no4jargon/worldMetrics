export const dynamic = 'force-dynamic';

export async function GET() {
  return new Response('{}', {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}
