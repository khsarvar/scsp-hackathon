"use client";

import { useState, useMemo } from "react";
import clsx from "clsx";
import DropZone from "@/components/upload/DropZone";
import { useSession } from "@/hooks/useSession";
import { profileDataset, streamDiscover, streamLiterature } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import type {
  AgentEvent,
  DiscoverResultPayload,
  LiteratureResult,
  UploadResponse,
} from "@/types";

export default function LeftSidebar() {
  const { state, dispatch } = useSession();

  const discoveredDatasets = useMemo(() => {
    let primaryAlias: string | null = null;

    // dataset_id → { title, description } from get_dataset_schema results
    const schemaByDatasetId: Record<string, { title: string; description: string }> = {};
    // alias → { datasetId, where } from fetch_dataset tool_call args
    const fetchArgsByAlias: Record<string, { datasetId: string; where?: string }> = {};

    for (const ev of state.discoverEvents) {
      const e = ev as Record<string, unknown>;

      if (e.type === "final" && e.agent === "discover" && e.primary_alias) {
        primaryAlias = e.primary_alias as string;
      }

      if (e.type === "tool_call" && e.agent === "discover" && e.name === "fetch_dataset") {
        const args = e.args as Record<string, unknown> | undefined;
        if (args?.alias) {
          fetchArgsByAlias[args.alias as string] = {
            datasetId: (args.dataset_id as string) ?? "",
            where: args.where as string | undefined,
          };
        }
      }

      if (e.type === "tool_result" && e.agent === "discover" && e.name === "get_dataset_schema") {
        const r = e.result as Record<string, unknown> | undefined;
        if (r?.id) {
          schemaByDatasetId[r.id as string] = {
            title: (r.name as string) ?? "",
            description: (r.description as string) ?? "",
          };
        }
      }
    }

    const datasets: {
      alias: string;
      rows: number;
      cols: number;
      datasetId: string;
      title: string;
      description: string;
      where?: string;
    }[] = [];

    for (const ev of state.discoverEvents) {
      const e = ev as Record<string, unknown>;
      if (e.type === "tool_result" && e.agent === "discover" && e.name === "fetch_dataset") {
        const r = e.result as Record<string, unknown> | undefined;
        if (r?.ok && r.alias) {
          const alias = r.alias as string;
          const fetchArgs = fetchArgsByAlias[alias];
          const datasetId = fetchArgs?.datasetId ?? "";
          const schema = datasetId ? schemaByDatasetId[datasetId] : undefined;
          datasets.push({
            alias,
            rows: (r.rows as number) ?? 0,
            cols: Array.isArray(r.columns) ? (r.columns as unknown[]).filter(c => c !== "...").length : 0,
            datasetId,
            title: schema?.title ?? "",
            description: schema?.description ?? "",
            where: fetchArgs?.where,
          });
        }
      }
    }

    return { datasets, primaryAlias };
  }, [state.discoverEvents]);
  const [discoverQuestion, setDiscoverQuestion] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);

  const busy =
    state.step === "uploading" ||
    state.step === "profiling" ||
    state.step === "discovering" ||
    discovering;

  const profileAfterUpload = async (result: UploadResponse) => {
    dispatch({ type: "SET_UPLOAD", payload: result });
    dispatch({ type: "SET_STEP", step: "profiling" });
    try {
      const profile = await profileDataset(result.session_id);
      dispatch({ type: "SET_PROFILE", payload: profile });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  };

  const handleUploadComplete = async (result: UploadResponse) => {
    await profileAfterUpload(result);
  };

  const handleDiscover = async () => {
    const q = discoverQuestion.trim();
    if (!q || discovering) return;
    setDiscovering(true);
    setDiscoverError(null);
    dispatch({ type: "DISCOVER_RESET" });
    dispatch({ type: "LITERATURE_RESET" });
    dispatch({ type: "SET_STEP", step: "discovering" });

    // Kick off literature review in parallel — same research question, no session yet.
    // Persistence to the session happens after discover finishes (see below).
    const literaturePromise = (async () => {
      let result: LiteratureResult | null = null;
      try {
        const litRes = await streamLiterature(q, null);
        await consumeAgentStream(litRes, (event: AgentEvent) => {
          dispatch({ type: "LITERATURE_EVENT", event });
          if (event.type === "result") {
            const data = (event as { data: Record<string, unknown> }).data;
            if (data.ok && typeof data.summary === "string") {
              result = {
                question: (data.question as string) ?? q,
                summary: data.summary,
                articles: (data.articles as LiteratureResult["articles"]) ?? [],
              };
              dispatch({ type: "SET_LITERATURE_RESULT", result });
            }
          }
        });
      } catch {
        // non-fatal: discover continues regardless
      }
      return result;
    })();

    try {
      const res = await streamDiscover(q);
      const payloadHolder: { value: DiscoverResultPayload | null; error: string | null } = {
        value: null,
        error: null,
      };
      await consumeAgentStream(res, (event: AgentEvent) => {
        dispatch({ type: "DISCOVER_EVENT", event });
        if (event.type === "result") {
          const data = (event as { data: Record<string, unknown> }).data;
          if (data.ok) {
            payloadHolder.value = data as unknown as DiscoverResultPayload;
          } else if (typeof data.error === "string") {
            payloadHolder.error = data.error;
          }
        }
      });
      const payload = payloadHolder.value;
      if (payload) {
        const upload: UploadResponse = {
          session_id: payload.session_id,
          filename: payload.filename,
          row_count: payload.row_count,
          col_count: payload.col_count,
          columns: payload.columns,
          preview_rows: payload.preview_rows,
          file_size_bytes: payload.file_size_bytes,
          provenance: payload.provenance,
        };
        await profileAfterUpload(upload);
      } else {
        const message = payloadHolder.error ?? "Discovery agent did not produce a primary dataset.";
        setDiscoverError(message);
        dispatch({ type: "SET_STEP", step: "idle" });
      }
    } catch (err) {
      setDiscoverError((err as Error).message);
      dispatch({ type: "SET_STEP", step: "idle" });
    } finally {
      // Let the literature stream finish in the background; don't block the UI on it.
      literaturePromise.catch(() => {});
      setDiscovering(false);
    }
  };

  const handleReset = () => {
    dispatch({ type: "RESET" });
    setDiscoverQuestion("");
    setDiscoverError(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-sky-500 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-800">HealthLab Agent</h1>
            <p className="text-xs text-slate-400">Public Health Analysis</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* CDC Discover */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Discover (CDC)
          </p>
          <textarea
            value={discoverQuestion}
            onChange={(e) => setDiscoverQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleDiscover();
              }
            }}
            placeholder="Research question, e.g. How does flu vaccination relate to hospitalization rates by state? (Enter to submit, Shift+Enter for newline)"
            rows={3}
            disabled={busy}
            className={clsx(
              "w-full resize-none rounded-lg border border-slate-200 px-2.5 py-2 text-xs",
              "placeholder:text-slate-300 focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-400/20",
              busy && "opacity-50 cursor-not-allowed"
            )}
          />
          <button
            onClick={handleDiscover}
            disabled={busy || !discoverQuestion.trim()}
            className={clsx(
              "mt-1.5 w-full px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              !busy && discoverQuestion.trim()
                ? "bg-teal-500 hover:bg-teal-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-300 cursor-not-allowed"
            )}
          >
            {discovering ? "Searching CDC catalog..." : "Discover datasets"}
          </button>
          {discoverError && (
            <p className="mt-1.5 text-xs text-red-500">{discoverError}</p>
          )}
        </div>

        {/* Discovered datasets — informational compact list */}
        {discoveredDatasets.datasets.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Discovered Datasets
            </p>
            <div className="space-y-2">
              {discoveredDatasets.datasets.map((ds) => {
                const isPrimary = ds.alias === discoveredDatasets.primaryAlias;
                return (
                  <div
                    key={ds.alias}
                    className={clsx(
                      "rounded-lg border px-3 py-2.5 space-y-1",
                      isPrimary ? "bg-teal-50 border-teal-200" : "bg-slate-50 border-slate-100"
                    )}
                  >
                    {/* Alias + primary badge */}
                    <div className="flex items-center justify-between gap-1">
                      <span className={clsx(
                        "text-xs font-semibold truncate",
                        isPrimary ? "text-teal-800" : "text-slate-700"
                      )}>
                        {ds.alias}
                      </span>
                      {isPrimary && (
                        <span className="shrink-0 text-[9px] font-bold bg-teal-500 text-white px-1.5 py-0.5 rounded-full leading-none">
                          primary
                        </span>
                      )}
                    </div>

                    {/* CDC dataset title */}
                    {ds.title && (
                      <p className="text-[11px] text-slate-500 leading-snug">{ds.title}</p>
                    )}

                    {/* Rows × cols */}
                    <p className={clsx("text-[11px]", isPrimary ? "text-teal-600" : "text-slate-400")}>
                      {ds.rows.toLocaleString()} rows · {ds.cols} cols
                    </p>

                    {/* SoQL filter */}
                    {ds.where && (
                      <p className="text-[10px] text-slate-400 font-mono truncate" title={ds.where}>
                        WHERE {ds.where}
                      </p>
                    )}

                    {/* Source link */}
                    {ds.datasetId && (
                      <a
                        href={`https://data.cdc.gov/d/${ds.datasetId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 text-[10px] text-sky-500 hover:text-sky-700 hover:underline"
                      >
                        View on CDC ↗
                      </a>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Upload section */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Upload Dataset</p>
          <DropZone
            onUploadComplete={handleUploadComplete}
            isLoading={state.step === "uploading" || state.step === "profiling"}
          />
        </div>

      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-100">
        {state.step !== "idle" && (
          <button
            onClick={handleReset}
            className="w-full text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            ← Start over
          </button>
        )}
        <p className="text-center text-xs text-slate-300 mt-2">HealthLab Agent v1.0</p>
      </div>
    </div>
  );
}
