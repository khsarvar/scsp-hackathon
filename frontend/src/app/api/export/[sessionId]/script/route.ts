import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/constants";

export async function GET(
  req: NextRequest,
  { params }: { params: { sessionId: string } }
) {
  const res = await fetch(`${BACKEND_URL}/api/export/${params.sessionId}/script`);
  if (!res.ok) {
    return NextResponse.json({ error: "Script export failed" }, { status: res.status });
  }
  const text = await res.text();
  return new Response(text, {
    headers: {
      "Content-Type": "text/x-python",
      "Content-Disposition":
        res.headers.get("Content-Disposition") || 'attachment; filename="healthlab_analysis.py"',
    },
  });
}
