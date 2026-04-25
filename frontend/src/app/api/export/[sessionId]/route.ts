import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/constants";

export async function GET(
  req: NextRequest,
  { params }: { params: { sessionId: string } }
) {
  const res = await fetch(`${BACKEND_URL}/api/export/${params.sessionId}`);
  if (!res.ok) {
    return NextResponse.json({ error: "Export failed" }, { status: res.status });
  }
  const blob = await res.blob();
  const text = await blob.text();
  return new Response(text, {
    headers: {
      "Content-Type": "text/markdown",
      "Content-Disposition": res.headers.get("Content-Disposition") || 'attachment; filename="memo.md"',
    },
  });
}
