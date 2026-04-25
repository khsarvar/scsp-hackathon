"use client";

import { useState } from "react";
import clsx from "clsx";
import DropZone from "@/components/upload/DropZone";
import { useSession } from "@/hooks/useSession";
import { profileDataset, streamDiscover } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import type {
  AgentEvent,
  DiscoverResultPayload,
  UploadResponse,
} from "@/types";

export default function LeftSidebar() {
  const { state, dispatch } = useSession();
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
    dispatch({ type: "SET_STEP", step: "discovering" });
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
            placeholder="Research question, e.g. How does flu vaccination relate to hospitalization rates by state?"
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

        {/* Upload section */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Upload Dataset</p>
          <DropZone
            onUploadComplete={handleUploadComplete}
            isLoading={state.step === "uploading" || state.step === "profiling"}
          />
        </div>

        {/* Current session info */}
        {state.uploadResult && (
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Current Session</p>
            <div className="bg-teal-50 border border-teal-100 rounded-lg px-3 py-2.5">
              <p className="text-xs font-medium text-teal-800 truncate">{state.uploadResult.filename}</p>
              <p className="text-xs text-teal-600 mt-0.5">
                {state.uploadResult.row_count.toLocaleString()} rows · {state.uploadResult.col_count} columns
              </p>
            </div>
          </div>
        )}

        {/* Analysis history */}
        {state.history.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Recent Sessions</p>
            <div className="space-y-1">
              {state.history.slice(0, 5).map((h) => (
                <div
                  key={h.session_id}
                  className={clsx(
                    "px-3 py-2 rounded-lg text-xs cursor-default",
                    h.session_id === state.sessionId
                      ? "bg-teal-50 border border-teal-200"
                      : "bg-slate-50 border border-slate-100"
                  )}
                >
                  <p className="font-medium text-slate-700 truncate">{h.filename}</p>
                  <p className="text-slate-400">{h.row_count} rows · {new Date(h.created_at).toLocaleDateString()}</p>
                </div>
              ))}
            </div>
          </div>
        )}
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
