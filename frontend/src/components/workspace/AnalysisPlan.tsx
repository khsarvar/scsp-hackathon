"use client";

import { useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { exportScriptUrl } from "@/lib/api";

interface AnalysisPlanProps {
  plan: string;
  onApprove: () => void;
  isAnalyzing: boolean;
  scriptSessionId?: string | null;
  scriptEnabled?: boolean;
  sessionId?: string | null;
  onPlanChange?: (newPlan: string) => void;
}

type Mode = "view" | "edit" | "refine";

export default function AnalysisPlan({
  plan,
  onApprove,
  isAnalyzing,
  scriptSessionId,
  scriptEnabled,
  sessionId,
  onPlanChange,
}: AnalysisPlanProps) {
  const [mode, setMode] = useState<Mode>("view");
  const [editText, setEditText] = useState(plan);
  const [isSaving, setIsSaving] = useState(false);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [isRefining, setIsRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const refineInputRef = useRef<HTMLInputElement>(null);

  // Keep editText in sync when the plan prop changes externally (e.g. after AI refine)
  // but only when not currently editing.
  const prevPlanRef = useRef(plan);
  if (plan !== prevPlanRef.current && mode !== "edit") {
    prevPlanRef.current = plan;
    setEditText(plan);
  }

  function enterEdit() {
    setEditText(plan);
    setMode("edit");
  }

  async function saveEdit() {
    if (!sessionId || !onPlanChange) return;
    setIsSaving(true);
    try {
      const { updatePlan } = await import("@/lib/api");
      const res = await updatePlan(sessionId, editText);
      onPlanChange(res.analysis_plan);
      setMode("view");
    } catch (e) {
      // Stay in edit mode; surface to user via browser alert for simplicity
      alert(`Save failed: ${(e as Error).message}`);
    } finally {
      setIsSaving(false);
    }
  }

  function cancelEdit() {
    setEditText(plan);
    setMode("view");
  }

  function enterRefine() {
    setRefineInstruction("");
    setRefineError(null);
    setMode("refine");
    // Focus the input after React renders
    setTimeout(() => refineInputRef.current?.focus(), 50);
  }

  async function submitRefine() {
    if (!sessionId || !onPlanChange || !refineInstruction.trim()) return;
    setIsRefining(true);
    setRefineError(null);
    try {
      const { refinePlan } = await import("@/lib/api");
      const res = await refinePlan(sessionId, refineInstruction.trim());
      onPlanChange(res.analysis_plan);
      setMode("view");
      setRefineInstruction("");
    } catch (e) {
      setRefineError((e as Error).message);
    } finally {
      setIsRefining(false);
    }
  }

  function cancelRefine() {
    setMode("view");
    setRefineInstruction("");
    setRefineError(null);
  }

  const canModify = !!sessionId && !!onPlanChange && !isAnalyzing;

  return (
    <div className="space-y-4">
      {/* Plan display / edit area */}
      {mode === "edit" ? (
        <div className="space-y-2">
          <textarea
            className="w-full h-72 text-sm font-mono bg-white border border-teal-300 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-teal-400 resize-y"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            spellCheck={false}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={saveEdit}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-4 py-2 bg-teal-500 hover:bg-teal-600 disabled:bg-teal-300 text-white text-sm font-semibold rounded-lg transition-colors"
            >
              {isSaving ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Saving…
                </>
              ) : (
                "Save"
              )}
            </button>
            <button
              onClick={cancelEdit}
              disabled={isSaving}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 border border-slate-200 hover:border-slate-300 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
          <div className="prose-healthlab">
            <ReactMarkdown>{plan}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* AI Refine input (shown beneath the plan when active) */}
      {mode === "refine" && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 space-y-2">
          <p className="text-xs font-medium text-violet-700">
            Describe what you want changed — the AI will rewrite the full plan.
          </p>
          <input
            ref={refineInputRef}
            type="text"
            value={refineInstruction}
            onChange={(e) => setRefineInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitRefine();
              }
              if (e.key === "Escape") cancelRefine();
            }}
            placeholder="e.g. Add a step for time-series trend analysis"
            className="w-full text-sm bg-white border border-violet-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-400 placeholder-slate-400"
            disabled={isRefining}
          />
          {refineError && (
            <p className="text-xs text-red-500">{refineError}</p>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={submitRefine}
              disabled={isRefining || !refineInstruction.trim()}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-500 hover:bg-violet-600 disabled:bg-violet-300 text-white text-sm font-semibold rounded-lg transition-colors"
            >
              {isRefining ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Refining…
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                  </svg>
                  Revise with AI
                </>
              )}
            </button>
            <button
              onClick={cancelRefine}
              disabled={isRefining}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 border border-slate-200 hover:border-slate-300 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onApprove}
          disabled={isAnalyzing || mode === "edit"}
          className="flex items-center gap-2 px-5 py-2.5 bg-teal-500 hover:bg-teal-600 disabled:bg-teal-300 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          {isAnalyzing ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Running Analysis...
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Approve &amp; Run Analysis
            </>
          )}
        </button>

        {canModify && mode === "view" && (
          <>
            <button
              onClick={enterEdit}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold rounded-lg border border-slate-200 text-slate-700 hover:border-teal-300 hover:text-teal-700 hover:bg-teal-50 transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
              Edit
            </button>

            <button
              onClick={enterRefine}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold rounded-lg border border-slate-200 text-slate-700 hover:border-violet-300 hover:text-violet-700 hover:bg-violet-50 transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              Refine with AI
            </button>
          </>
        )}

        {scriptSessionId && (
          <a
            href={exportScriptUrl(scriptSessionId)}
            download
            aria-disabled={!scriptEnabled}
            onClick={(e) => {
              if (!scriptEnabled) e.preventDefault();
            }}
            className={
              "flex items-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-lg border transition-colors " +
              (scriptEnabled
                ? "border-slate-200 text-slate-700 hover:border-teal-300 hover:text-teal-700 hover:bg-teal-50"
                : "border-slate-100 text-slate-300 cursor-not-allowed")
            }
            title={
              scriptEnabled
                ? "Download a runnable Python script that reproduces this plan"
                : "Run the analysis first to enable script export"
            }
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export Python Script
          </a>
        )}

        <p className="text-xs text-slate-400">
          The agent will clean the data, compute statistics, generate charts, and write a research memo.
        </p>
      </div>
    </div>
  );
}
