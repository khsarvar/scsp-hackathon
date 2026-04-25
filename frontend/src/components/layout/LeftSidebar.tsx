"use client";

import { useState } from "react";
import clsx from "clsx";
import DropZone from "@/components/upload/DropZone";
import { useSession } from "@/hooks/useSession";
import { profileDataset, uploadFromUrl } from "@/lib/api";
import type { UploadResponse } from "@/types";

export default function LeftSidebar() {
  const { state, dispatch } = useSession();
  const [loadingDemo, setLoadingDemo] = useState(false);

  const handleUploadComplete = async (result: UploadResponse) => {
    dispatch({ type: "SET_UPLOAD", payload: result });
    dispatch({ type: "SET_STEP", step: "profiling" });
    try {
      const profile = await profileDataset(result.session_id);
      dispatch({ type: "SET_PROFILE", payload: profile });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  };

  const handleLoadDemo = async () => {
    setLoadingDemo(true);
    try {
      dispatch({ type: "SET_STEP", step: "uploading" });
      const result = await uploadFromUrl("/demo_asthma.csv", "demo_asthma.csv");
      await handleUploadComplete(result);
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    } finally {
      setLoadingDemo(false);
    }
  };

  const handleReset = () => {
    dispatch({ type: "RESET" });
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
        {/* Upload section */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Upload Dataset</p>
          <DropZone
            onUploadComplete={handleUploadComplete}
            isLoading={state.step === "uploading" || state.step === "profiling"}
          />
        </div>

        {/* Demo dataset */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Example Datasets</p>
          <button
            onClick={handleLoadDemo}
            disabled={loadingDemo || state.step === "uploading" || state.step === "profiling"}
            className={clsx(
              "w-full text-left px-3 py-2.5 rounded-lg border text-sm transition-all",
              "hover:border-teal-300 hover:bg-teal-50",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "border-slate-200 bg-white"
            )}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">🫁</span>
              <div>
                <p className="font-medium text-slate-700">Asthma ER Visits</p>
                <p className="text-xs text-slate-400">CA Counties 2020–2023 · 322 rows</p>
              </div>
            </div>
          </button>
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
