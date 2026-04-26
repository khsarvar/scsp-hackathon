import type {
  UploadResponse,
  ProfileResponse,
  AnalyzeResponse,
  ChatMessage,
  HypothesesResponse,
  RunTestResponse,
} from "@/types";

const BASE = "/api";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadCSV(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  return handleResponse<UploadResponse>(res);
}

export async function uploadFromUrl(url: string, filename: string): Promise<UploadResponse> {
  // Fetch the CSV, then upload as a file
  const csvRes = await fetch(url);
  const blob = await csvRes.blob();
  const file = new File([blob], filename, { type: "text/csv" });
  return uploadCSV(file);
}

export async function profileDataset(sessionId: string): Promise<ProfileResponse> {
  const res = await fetch(`${BASE}/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return handleResponse<ProfileResponse>(res);
}

export async function runAnalysis(
  sessionId: string,
  question?: string | null,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question: question ?? null }),
  });
  return handleResponse<AnalyzeResponse>(res);
}

/** URL of an agent-generated chart PNG. */
export function chartUrl(sessionId: string, filename: string): string {
  return `${BASE}/charts/${sessionId}/${encodeURIComponent(filename)}`;
}

export async function sendChatMessage(
  sessionId: string,
  message: string,
  history: ChatMessage[]
): Promise<Response> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, history }),
  });
  if (!res.ok) {
    throw new Error(res.statusText);
  }
  return res;
}

export async function exportMemo(sessionId: string): Promise<Blob> {
  const res = await fetch(`${BASE}/export/${sessionId}`);
  if (!res.ok) {
    throw new Error(res.statusText);
  }
  return res.blob();
}

// ---------- Agentic endpoints ----------

/** Stream the CDC discovery agent. Returns a Response whose body is an SSE stream. */
export async function streamDiscover(question: string): Promise<Response> {
  const res = await fetch(`${BASE}/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res;
}

/** Stream the agentic auto-clean loop. */
export async function streamAgentClean(sessionId: string): Promise<Response> {
  const res = await fetch(`${BASE}/agent_clean`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res;
}

/** Generate testable hypotheses for the current session's primary dataset. */
export async function generateHypotheses(sessionId: string, n = 4): Promise<HypothesesResponse> {
  const res = await fetch(`${BASE}/hypotheses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, n }),
  });
  return handleResponse<HypothesesResponse>(res);
}

/** Run a single statistical test (no LLM). */
export async function runStatsTest(
  sessionId: string,
  test: string,
  args: Record<string, unknown>
): Promise<RunTestResponse> {
  const res = await fetch(`${BASE}/stats/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, test, args }),
  });
  return handleResponse<RunTestResponse>(res);
}

/** Stream the analysis agent's reasoning for a free-form question. */
export async function streamAsk(sessionId: string, question: string): Promise<Response> {
  const res = await fetch(`${BASE}/stats/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res;
}

/** Stream the PubMed literature review agent. */
export async function streamLiterature(
  question: string,
  sessionId: string | null,
): Promise<Response> {
  const res = await fetch(`${BASE}/literature/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res;
}

/** Trigger a Python script download for the session's analysis. */
export function exportScriptUrl(sessionId: string): string {
  return `${BASE}/export/${sessionId}/script`;
}

/** Overwrite the analysis plan with user-edited text. */
export async function updatePlan(
  sessionId: string,
  plan: string,
): Promise<{ session_id: string; analysis_plan: string }> {
  const res = await fetch(`${BASE}/plan`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, plan }),
  });
  return handleResponse(res);
}

/** Ask the AI to revise the plan based on a user instruction. */
export async function refinePlan(
  sessionId: string,
  instruction: string,
): Promise<{ session_id: string; analysis_plan: string }> {
  const res = await fetch(`${BASE}/plan/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, instruction }),
  });
  return handleResponse(res);
}
