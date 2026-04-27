import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/constants";

export async function GET(
  req: NextRequest,
  { params }: { params: { sessionId: string; filename: string } },
) {
  const res = await fetch(
    `${BACKEND_URL}/api/charts/${params.sessionId}/${encodeURIComponent(params.filename)}`,
  );
  if (!res.ok) {
    return NextResponse.json({ error: "Chart not found" }, { status: res.status });
  }
  const buf = await res.arrayBuffer();
  return new Response(buf, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=300",
    },
  });
}
