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
  median?: number | null;
  std?: number | null;
  is_datetime_like: boolean;
  is_categorical: boolean;
  outliers: OutlierInfo[];
}

export interface DataSource {
  alias: string;
  source_str: string;
  cdc_id?: string | null;
  cdc_url?: string | null;
  soql_filter?: string | null;
  soql_select?: string | null;
  parents?: string[];
}

export interface DataProvenance {
  type: "upload" | "cdc_discover";
  filename?: string | null;
  research_question?: string | null;
  primary_alias?: string | null;
  sources: DataSource[];
}

export interface UploadResponse {
  session_id: string;
  filename: string;
  row_count: number;
  col_count: number;
  columns: string[];
  preview_rows: Record<string, unknown>[];
  file_size_bytes: number;
  provenance?: DataProvenance | null;
}

export interface ProfileResponse {
  session_id: string;
  row_count: number;
  col_count: number;
  duplicate_rows: number;
  columns: ColumnProfile[];
  analysis_plan: string | null;
  charts: ChartSpec[];
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
  chart_type: "line" | "bar" | "scatter" | "histogram" | "box" | "heatmap";
  title: string;
  x_key: string;
  y_keys: string[];
  y_key?: string | null;
  description?: string;
  data: Record<string, unknown>[];
}

export interface CodeStep {
  rationale: string;
  code: string;
  stdout: string;
  stderr: string;
  charts: string[];
  ok: boolean;
}

export interface AnalyzeResponse {
  session_id: string;
  research_question?: string | null;
  cleaning_steps: string[];
  steps: CodeStep[];
  summary: string;
  findings: string;
  limitations: string;
  follow_up: string;
  charts: ChartSpec[];
  stats: StatRow[];
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

export interface DatasetColumn {
  field: string;
  name: string;
  type: string;
}

export interface DatasetRecommendation {
  id: string;
  name: string;
  description: string;
  row_count: number | null;
  categories: string[];
  tags: string[];
  columns: DatasetColumn[];
}

export interface DiscoverCandidate {
  alias: string;
  rows: number;
  cols: number;
  columns: string[];
  is_derived: boolean;
  source_title: string;
  parents: string[];
}

export interface DiscoverResultPayload {
  ok: boolean;
  session_id: string;
  // present when pending_join === false
  filename?: string;
  primary_alias?: string;
  row_count?: number;
  col_count?: number;
  columns?: string[];
  preview_rows?: Record<string, unknown>[];
  file_size_bytes?: number;
  provenance?: DataProvenance | null;
  // present when pending_join === true (HITL checkpoint)
  pending_join?: boolean;
  candidates?: DiscoverCandidate[];
  suggested_alias?: string;
}

// App state
export type AppStep =
  | "idle"
  | "uploading"
  | "recommending"
  | "recommended"
  | "discovering"
  | "join_decision"
  | "preview"
  | "profiling"
  | "charted"
  | "planned"
  | "analyzing"
  | "results"
  | "error";

export interface PipelineConfig {
  runAnalysis: boolean;
  runLiterature: boolean;
}

export type WorkspaceTab = "discover" | "literature" | "plan";

export interface LiteratureArticle {
  pmid: string;
  title: string;
  authors?: string[];
  journal?: string;
  year?: string;
  doi?: string;
  url?: string;
  abstract?: string;
  relevance?: string;
}

export interface LiteratureResult {
  question: string;
  summary: string;
  articles: LiteratureArticle[];
}

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
  codeStepEvents: CodeStep[];
  hypotheses: Hypothesis[];
  lastTestResult: RunTestResponse | null;
  // Catalog recommendations (pre-fetch HITL)
  recommendations: DatasetRecommendation[] | null;
  recommendationQuestion: string | null;
  // HITL join decision (post-fetch)
  discoverCandidates: DiscoverCandidate[] | null;
  discoverSuggestedAlias: string | null;
  // Literature review
  literatureEvents: AgentEvent[];
  literatureResult: LiteratureResult | null;
  // UI
  activeTab: WorkspaceTab;
  // Pipeline opt-ins
  pipelineConfig: PipelineConfig;
}
