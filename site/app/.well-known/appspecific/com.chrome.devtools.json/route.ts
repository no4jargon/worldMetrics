export const dynamic = 'force-static';

export async function GET() {
  return new Response('{}', {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}
