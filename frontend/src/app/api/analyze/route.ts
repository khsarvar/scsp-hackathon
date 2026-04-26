import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/constants";

export async function POST(req: NextRequest) {
  const body = await req.json();
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return new Response(
      JSON.stringify({ detail: "Cannot reach backend. Is the FastAPI server running on port 8000?" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
