import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/constants";

export async function POST(req: NextRequest) {
  const body = await req.json();
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/stats/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return NextResponse.json(
      { detail: "Cannot reach backend. Is the FastAPI server running on port 8000?" },
      { status: 503 }
    );
  }
  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: `Backend error (${res.status}): ${text.slice(0, 300)}` },
      { status: res.status || 500 }
    );
  }
}
