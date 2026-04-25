import type {
  UploadResponse,
  ProfileResponse,
  AnalyzeResponse,
  ChatMessage,
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

export async function runAnalysis(sessionId: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return handleResponse<AnalyzeResponse>(res);
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
