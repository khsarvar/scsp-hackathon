"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BACKEND_URL } from "@/lib/constants";

type ProviderInfo = {
  id: string;
  label: string;
  configured: boolean;
  models: string[];
};

type Candidate = {
  dataset_id: string;
  title: string;
  description?: string;
  row_count?: number;
  updated_at?: string;
  columns: string[];
  geo_fields: string[];
  date_fields: string[];
  relevance_reason?: string;
};

type PinnedDataset = {
  id: number;
  dataset_id: string;
  title: string;
  profile?: { row_count?: number; col_count?: number; columns?: Array<{ name: string; dtype: string; missing_pct: number }> };
};

type JoinPlan = {
  id: number;
  left_dataset_id: string;
  right_dataset_id: string;
  strategy: string;
  join_type: string;
  keys: Array<{ left: string; right: string; normalized_name: string }>;
  normalizations: string[];
  confidence: number;
  risks?: string;
  status: string;
};

type ActionLog = {
  id: number;
  agent_name: string;
  action_type: string;
  rationale?: string;
  output?: unknown;
  warnings?: string[];
  created_at: string;
};

type StatisticalResult = {
  id: number;
  test_name: string;
  variables: string[];
  assumptions: Record<string, unknown>;
  result: Record<string, unknown>;
  interpretation?: string;
};

type Citation = {
  pmid: string;
  title: string;
  authors?: string;
  journal?: string;
  year?: string;
  url: string;
  relevance_note?: string;
};

type ChatThread = {
  id: string;
  title: string;
};

type RunBundle = {
  run: {
    id: string;
    question: string;
    provider: string;
    model: string;
    status: string;
    discovery_mode?: string;
    discovery_rationale?: string;
  };
  candidates: Candidate[];
  pinned_datasets: PinnedDataset[];
  join_plans: JoinPlan[];
  join_results: Array<{ explanation: string; match_rate: number; duplicate_warnings: string[] }>;
  actions: ActionLog[];
  statistical_results: StatisticalResult[];
  literature: Citation[];
  chat_threads: ChatThread[];
  report_markdown?: string;
};

type ProgressEvent = {
  event: string;
  message: string;
  status?: string;
};

type StreamEvent = {
  event?: string;
  type?: string;
  agent?: string;
  message?: string;
  text?: string;
  summary?: string;
  status?: string;
  name?: string;
  args?: Record<string, unknown>;
  bundle?: RunBundle;
  data?: RunBundle & { unsafe_python_result?: Record<string, unknown> };
};

const DEFAULT_QUESTION =
  "How is flu activity associated with asthma emergency visits across geography and time?";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
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

function fmtRows(value?: number) {
  return typeof value === "number" ? value.toLocaleString() : "unknown";
}

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-7xl px-5 py-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
          {action}
        </div>
        {children}
      </div>
    </section>
  );
}

export default function ResearchWorkbench() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [bundle, setBundle] = useState<RunBundle | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chatText, setChatText] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [pythonCode, setPythonCode] = useState(
    "print(df.head())\nprint(df.dtypes)\n\n# Put anything you want saved/displayed into result\nresult = df.describe(include='all').to_dict()"
  );
  const [pythonResult, setPythonResult] = useState<Record<string, unknown> | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    jsonFetch<{ providers: ProviderInfo[] }>("/api/research/providers")
      .then((data) => {
        setProviders(data.providers);
        const first = data.providers.find((p) => p.configured) || data.providers[0];
        if (first) {
          setProvider(first.id);
          setModel(first.models[0] || "");
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const selectedProvider = providers.find((p) => p.id === provider);
  const configured = !!selectedProvider?.configured;
  const activeThread = bundle?.chat_threads?.[0]?.id || null;

  const runId = bundle?.run.id;
  const pinnedIds = useMemo(
    () => new Set((bundle?.pinned_datasets || []).map((d) => d.dataset_id)),
    [bundle]
  );

  async function guarded<T>(label: string, fn: () => Promise<T>) {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setBusy(null);
    }
  }

  function consumeResearchEvent(parsed: StreamEvent) {
    const eventName = parsed.event || parsed.type || "agent";
    if (eventName === "result") {
      setBundle((parsed.bundle || parsed.data) as RunBundle);
      if (parsed.data?.unsafe_python_result) setPythonResult(parsed.data.unsafe_python_result);
      return;
    }
    if (eventName === "error" || eventName === "_error") {
      setProgressEvents((prev) => [
        ...prev,
        { event: "error", message: parsed.message || "Agent action failed", status: "error" },
      ]);
      throw new Error(parsed.message || "Agent action failed");
    }
    const message =
      parsed.message ||
      parsed.text ||
      parsed.summary ||
      (parsed.name ? `${parsed.name}: ${JSON.stringify(parsed.args || {})}` : "Working");
    setProgressEvents((prev) => [
      ...prev,
      {
        event: parsed.agent || eventName,
        message,
        status: parsed.status || (eventName === "final" ? "complete" : "running"),
      },
    ]);
  }

  async function streamAction(label: string, path: string, body?: unknown) {
    setBusy(label);
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!res.ok) throw new Error(res.statusText);
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No event stream.");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") break;
          consumeResearchEvent(JSON.parse(data) as StreamEvent);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  const startRun = async () => {
    setBusy("Launching agents");
    setError(null);
    setBundle(null);
    setChatMessages([]);
    setProgressEvents([]);
    await streamAction("Launching agents", "/api/research/runs/stream", { question, provider, model });
  };

  const refresh = async () => {
    if (!runId) return;
    const result = await jsonFetch<RunBundle>(`/api/research/runs/${runId}`);
    setBundle(result);
  };

  const pinDataset = async (candidate: Candidate) => {
    if (!runId) return;
    const result = await guarded("Pinning dataset", () =>
      jsonFetch<RunBundle>(`/api/research/runs/${runId}/datasets`, {
        method: "POST",
        body: JSON.stringify({ dataset_id: candidate.dataset_id, title: candidate.title }),
      })
    );
    if (result) setBundle(result);
  };

  const proposeJoins = async () => {
    if (!runId) return;
    await streamAction("Planning joins", `/api/research/runs/${runId}/joins/propose/stream`);
  };

  const applyJoin = async (id: number) => {
    if (!runId) return;
    await streamAction("Applying approved join", `/api/research/runs/${runId}/joins/${id}/apply/stream`);
  };

  const runMethodology = async () => {
    if (!runId) return;
    await streamAction("Running methodology", `/api/research/runs/${runId}/methodology/stream`);
  };

  const executePython = async () => {
    if (!runId) return;
    await streamAction("Executing unsafe Python", `/api/research/runs/${runId}/execute-python/stream`, { code: pythonCode });
  };

  const generateReport = async () => {
    if (!runId) return;
    await streamAction("Generating report", `/api/research/runs/${runId}/report/stream`);
  };

  const startNewChat = async () => {
    if (!runId) return;
    await guarded("Starting new chat", () =>
      jsonFetch<ChatThread>(`/api/research/runs/${runId}/chat/new`, { method: "POST" })
    );
    setChatMessages([]);
    await refresh();
  };

  const sendChat = async () => {
    if (!activeThread || !chatText.trim()) return;
    const message = chatText.trim();
    setChatText("");
    setChatMessages((prev) => [...prev, { role: "user", content: message }, { role: "assistant", content: "" }]);
    setBusy("Chatting");
    try {
      const res = await fetch(`${BACKEND_URL}/api/research/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: activeThread, message }),
      });
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No chat stream.");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") break;
          const parsed = JSON.parse(data);
          if (parsed.delta) {
            setChatMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + parsed.delta };
              return next;
            });
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-4 lg:grid-cols-[1fr_320px]">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-teal-600 text-sm font-bold text-white">
                HL
              </div>
              <div>
                <h1 className="text-lg font-semibold text-slate-900">HealthLab Research Workbench</h1>
                <p className="text-sm text-slate-500">CDC discovery, optional joins, methodology logging, PubMed evidence, and report generation.</p>
              </div>
            </div>
          </div>
          <div className="flex items-center justify-start gap-2 lg:justify-end">
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600">
              {bundle ? bundle.run.status.replaceAll("_", " ") : "new run"}
            </span>
            {busy && <span className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700">{busy}</span>}
          </div>
        </div>
      </header>

      <Section title="Research Setup">
        <div className="grid gap-4 lg:grid-cols-[220px_220px_1fr_auto]">
          <label className="text-xs font-medium text-slate-600">
            Provider
            <select
              value={provider}
              onChange={(e) => {
                const p = providers.find((item) => item.id === e.target.value);
                setProvider(e.target.value);
                setModel(p?.models[0] || "");
              }}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} {p.configured ? "" : "(missing key)"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Model
            <select value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm">
              {(selectedProvider?.models || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Research question
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              className="mt-1 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
            />
          </label>
          <button
            onClick={startRun}
            disabled={!configured || !question.trim() || !!busy}
            className="self-end rounded-md bg-teal-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Start Run
          </button>
        </div>
        {!configured && <p className="mt-2 text-sm text-amber-700">Add the selected provider API key in backend/.env before starting a run.</p>}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        {progressEvents.length > 0 && (
          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50">
            <div className="border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Live Agent Activity
            </div>
            <div className="divide-y divide-slate-200">
              {progressEvents.map((event, index) => (
                <div key={`${event.event}-${index}`} className="grid grid-cols-[120px_1fr_90px] gap-3 px-3 py-2 text-xs">
                  <span className="font-semibold text-slate-700">{event.event}</span>
                  <span className="text-slate-600">{event.message}</span>
                  <span className={event.status === "error" ? "text-red-600" : event.status === "complete" ? "text-teal-700" : "text-amber-700"}>
                    {event.status || "running"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Section>

      {bundle && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <Section
              title="CDC Dataset Candidates"
              action={<span className="text-xs text-slate-500">{bundle.run.discovery_mode?.replaceAll("_", " ")}: {bundle.run.discovery_rationale}</span>}
            >
              <div className="grid gap-3 md:grid-cols-2">
                {bundle.candidates.slice(0, 6).map((candidate) => (
                  <div key={candidate.dataset_id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">{candidate.title}</h3>
                        <p className="mt-1 line-clamp-3 text-xs text-slate-600">{candidate.description || candidate.relevance_reason}</p>
                      </div>
                      <button
                        onClick={() => pinDataset(candidate)}
                        disabled={pinnedIds.has(candidate.dataset_id) || !!busy}
                        className="shrink-0 rounded border border-teal-600 px-2 py-1 text-xs font-semibold text-teal-700 disabled:border-slate-300 disabled:text-slate-400"
                      >
                        {pinnedIds.has(candidate.dataset_id) ? "Pinned" : "Pin"}
                      </button>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>ID {candidate.dataset_id}</span>
                      <span>{fmtRows(candidate.row_count)} rows</span>
                      <span>{candidate.columns.length} columns</span>
                      {candidate.geo_fields.slice(0, 2).map((g) => <span key={g}>geo: {g}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section
              title="Pinned Datasets And Optional Joins"
              action={
                <button
                  onClick={proposeJoins}
                  disabled={bundle.pinned_datasets.length < 2 || !!busy}
                  className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:text-slate-400"
                >
                  Propose Joins
                </button>
              }
            >
              <div className="grid gap-3 md:grid-cols-2">
                {bundle.pinned_datasets.map((ds) => (
                  <div key={ds.id} className="rounded-md border border-slate-200 p-3">
                    <h3 className="text-sm font-semibold">{ds.title}</h3>
                    <p className="text-xs text-slate-500">ID {ds.dataset_id} · {fmtRows(ds.profile?.row_count)} rows · {ds.profile?.col_count || 0} columns</p>
                  </div>
                ))}
                {bundle.pinned_datasets.length === 0 && <p className="text-sm text-slate-500">Pin at least one CDC dataset. Joins are optional.</p>}
              </div>
              {bundle.join_plans.length > 0 && (
                <div className="mt-4 space-y-3">
                  {bundle.join_plans.map((plan) => (
                    <div key={plan.id} className="rounded-md border border-amber-200 bg-amber-50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-slate-900">Join plan #{plan.id}: {plan.strategy}</h3>
                          <p className="mt-1 text-xs text-slate-700">
                            {plan.left_dataset_id} to {plan.right_dataset_id}, {plan.join_type} join, confidence {(plan.confidence * 100).toFixed(0)}%.
                          </p>
                          <p className="mt-1 text-xs text-slate-600">Keys: {plan.keys.map((k) => `${k.left} to ${k.right}`).join(", ")}</p>
                          {plan.risks && <p className="mt-1 text-xs text-amber-800">{plan.risks}</p>}
                        </div>
                        <button
                          onClick={() => applyJoin(plan.id)}
                          disabled={plan.status === "applied" || !!busy}
                          className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white disabled:bg-slate-300"
                        >
                          {plan.status === "applied" ? "Applied" : "Approve"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {bundle.join_results.map((jr, i) => (
                <p key={i} className="mt-3 rounded-md border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">{jr.explanation}</p>
              ))}
            </Section>

            <Section
              title="Methodology And Results"
              action={
                <button
                  onClick={runMethodology}
                  disabled={bundle.pinned_datasets.length === 0 || !!busy}
                  className="rounded-md bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white disabled:bg-slate-300"
                >
                  Run Methodology
                </button>
              }
            >
              <div className="grid gap-3 lg:grid-cols-2">
                {bundle.statistical_results.map((result) => (
                  <div key={result.id} className="rounded-md border border-slate-200 bg-white p-3">
                    <h3 className="text-sm font-semibold text-slate-900">{result.test_name}</h3>
                    <p className="mt-1 text-xs text-slate-500">{result.variables.join(", ")}</p>
                    <pre className="mt-2 max-h-28 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-50">{JSON.stringify(result.result, null, 2)}</pre>
                    <p className="mt-2 text-sm text-slate-700">{result.interpretation}</p>
                  </div>
                ))}
                {bundle.statistical_results.length === 0 && <p className="text-sm text-slate-500">Run methodology after pinning a dataset or approving a join.</p>}
              </div>
              <div className="mt-5">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Action Log</h3>
                <div className="max-h-72 overflow-auto rounded-md border border-slate-200">
                  {bundle.actions.slice().reverse().map((action) => (
                    <div key={action.id} className="border-b border-slate-100 px-3 py-2 text-xs">
                      <span className="font-semibold text-slate-700">{action.agent_name}</span>
                      <span className="mx-2 text-slate-400">{action.action_type}</span>
                      <span className="text-slate-500">{action.created_at}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-red-900">Unsafe Python Execution</h3>
                    <p className="text-xs text-red-700">
                      Runs arbitrary Python inside the backend process. The active dataframe is available as <code>df</code>; assign <code>result</code> to display output.
                    </p>
                  </div>
                  <button
                    onClick={executePython}
                    disabled={bundle.pinned_datasets.length === 0 || !!busy}
                    className="rounded-md bg-red-700 px-3 py-1.5 text-xs font-semibold text-white disabled:bg-slate-300"
                  >
                    Execute
                  </button>
                </div>
                <textarea
                  value={pythonCode}
                  onChange={(e) => setPythonCode(e.target.value)}
                  rows={8}
                  className="w-full resize-y rounded-md border border-red-200 bg-white px-3 py-2 font-mono text-xs text-slate-900"
                  spellCheck={false}
                />
                {pythonResult && (
                  <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-50">
                    {JSON.stringify(pythonResult, null, 2)}
                  </pre>
                )}
              </div>
            </Section>

            <Section
              title="Research Report"
              action={
                <div className="flex gap-2">
                  <button onClick={generateReport} disabled={!!busy} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700">
                    Generate Report
                  </button>
                  {bundle.report_markdown && (
                    <a href={`${BACKEND_URL}/api/research/runs/${bundle.run.id}/report.md`} className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white">
                      Download Markdown
                    </a>
                  )}
                </div>
              }
            >
              {bundle.report_markdown ? (
                <div className="prose-healthlab max-w-none rounded-md border border-slate-200 bg-white p-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{bundle.report_markdown}</ReactMarkdown>
                </div>
              ) : (
                <p className="text-sm text-slate-500">Generate the report after methodology. It will include datasets, joins if any, PubMed evidence, statistical results, and the reproducibility log.</p>
              )}
            </Section>
          </div>

          <aside className="border-l border-slate-200 bg-slate-50">
            <div className="sticky top-0 max-h-screen overflow-y-auto">
              <Section title="PubMed Evidence">
                <div className="space-y-3">
                  {bundle.literature.map((citation) => (
                    <a key={citation.pmid} href={citation.url} target="_blank" className="block rounded-md border border-slate-200 bg-white p-3 hover:border-teal-300">
                      <h3 className="text-sm font-semibold text-slate-900">{citation.title}</h3>
                      <p className="mt-1 text-xs text-slate-500">{citation.journal} · {citation.year || "n.d."} · PMID {citation.pmid}</p>
                    </a>
                  ))}
                  {bundle.literature.length === 0 && <p className="text-sm text-slate-500">No PubMed citations were retrieved.</p>}
                </div>
              </Section>

              <Section
                title="Research Chat"
                action={
                  <button onClick={startNewChat} disabled={!runId || !!busy} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700">
                    Start New Chat
                  </button>
                }
              >
                <div className="flex h-[520px] flex-col rounded-md border border-slate-200 bg-white">
                  <div className="flex-1 space-y-3 overflow-auto p-3">
                    {chatMessages.length === 0 && <p className="text-sm text-slate-500">Ask about the selected datasets, joins, methodology, or report. New chats start clean.</p>}
                    {chatMessages.map((m, i) => (
                      <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
                        <div className={`inline-block max-w-[88%] rounded-md px-3 py-2 text-sm ${m.role === "user" ? "bg-sky-50 text-slate-800" : "bg-slate-100 text-slate-800"}`}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                        </div>
                      </div>
                    ))}
                    <div ref={bottomRef} />
                  </div>
                  <div className="border-t border-slate-200 p-2">
                    <textarea
                      value={chatText}
                      onChange={(e) => setChatText(e.target.value)}
                      rows={2}
                      className="w-full resize-none rounded-md border border-slate-300 px-2 py-2 text-sm"
                      placeholder="Ask the research assistant"
                    />
                    <button onClick={sendChat} disabled={!chatText.trim() || !activeThread || !!busy} className="mt-2 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:bg-slate-300">
                      Send
                    </button>
                  </div>
                </div>
              </Section>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
