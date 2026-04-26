export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export const TEAL_PALETTE = [
  "#14b8a6",
  "#0ea5e9",
  "#8b5cf6",
  "#f59e0b",
  "#ef4444",
  "#10b981",
  "#6366f1",
];

export const STEP_LABELS: Record<string, string> = {
  idle: "Waiting for upload",
  uploading: "Uploading...",
  discovering: "Discovering datasets...",
  preview: "Dataset preview",
  profiling: "Profiling dataset...",
  planned: "Analysis plan ready",
  analyzing: "Running analysis...",
  results: "Analysis complete",
  error: "Error",
};
