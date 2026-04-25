export interface OutlierInfo {
  row_index: number;
  value: number;
  method: string;
}

export interface ColumnProfile {
  name: string;
  dtype_inferred: "datetime" | "numeric" | "categorical" | "id";
  missing_count: number;
  missing_pct: number;
  unique_count: number;
  sample_values: string[];
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  std?: number | null;
  is_datetime_like: boolean;
  is_categorical: boolean;
  outliers: OutlierInfo[];
}

export interface UploadResponse {
  session_id: string;
  filename: string;
  row_count: number;
  col_count: number;
  columns: string[];
  preview_rows: Record<string, unknown>[];
  file_size_bytes: number;
}

export interface ProfileResponse {
  session_id: string;
  row_count: number;
  col_count: number;
  duplicate_rows: number;
  columns: ColumnProfile[];
  analysis_plan: string;
}

export interface StatRow {
  column: string;
  count: number;
  mean?: number | null;
  median?: number | null;
  std?: number | null;
  min?: number | null;
  max?: number | null;
  p25?: number | null;
  p75?: number | null;
}

export interface ChartSpec {
  chart_type: "line" | "bar" | "scatter";
  title: string;
  x_key: string;
  y_keys: string[];
  y_key?: string | null;
  data: Record<string, unknown>[];
}

export interface AnalyzeResponse {
  session_id: string;
  cleaning_steps: string[];
  stats: StatRow[];
  charts: ChartSpec[];
  findings: string;
  limitations: string;
  follow_up: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface SessionHistory {
  session_id: string;
  filename: string;
  row_count: number;
  col_count: number;
  created_at: string;
}

// ---------- Agentic upgrades ----------

export type AgentEvent =
  | { type: "thought"; agent: string; text: string }
  | { type: "tool_call"; agent: string; name: string; args: Record<string, unknown>; rationale?: string }
  | { type: "tool_result"; agent: string; name: string; summary: string; result?: unknown }
  | { type: "final"; agent: string; summary?: string; primary_alias?: string }
  | { type: "error"; agent?: string; message: string }
  | { type: "result"; data: Record<string, unknown> }
  | { type: string; [k: string]: unknown };

export interface Hypothesis {
  question: string;
  variables?: string[];
  test_type?: string;
  args?: Record<string, unknown>;
  rationale?: string;
}

export interface HypothesesResponse {
  session_id: string;
  hypotheses: Hypothesis[];
}

export interface AssumptionCheck {
  normality_p?: number[];
  normality_satisfied?: boolean;
}

export interface StatsTestResult {
  test?: string;
  groups?: string[];
  n?: number | number[];
  means?: number[];
  statistic?: number | null;
  p_value?: number;
  cohens_d?: number;
  correlation?: number;
  contingency?: Record<string, Record<string, number>>;
  dof?: number;
  interpretation?: string;
  assumption_check?: AssumptionCheck;
  error?: string;
  [k: string]: unknown;
}

export interface RunTestResponse {
  session_id: string;
  test: string;
  args: Record<string, unknown>;
  result: StatsTestResult;
}

export interface DiscoverResultPayload {
  ok: boolean;
  session_id: string;
  filename: string;
  primary_alias: string;
  row_count: number;
  col_count: number;
  columns: string[];
  preview_rows: Record<string, unknown>[];
  file_size_bytes: number;
}

// App state
export type AppStep =
  | "idle"
  | "uploading"
  | "discovering"
  | "preview"
  | "profiling"
  | "planned"
  | "analyzing"
  | "results"
  | "error";

export interface AppState {
  step: AppStep;
  sessionId: string | null;
  uploadResult: UploadResponse | null;
  profileResult: ProfileResponse | null;
  analysisResult: AnalyzeResponse | null;
  error: string | null;
  history: SessionHistory[];
  // Agentic
  discoverEvents: AgentEvent[];
  cleanEvents: AgentEvent[];
  askEvents: AgentEvent[];
  hypotheses: Hypothesis[];
  lastTestResult: RunTestResponse | null;
}
