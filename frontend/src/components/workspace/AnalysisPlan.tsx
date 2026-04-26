"use client";

import ReactMarkdown from "react-markdown";
import { exportScriptUrl } from "@/lib/api";

interface AnalysisPlanProps {
  plan: string;
  onApprove: () => void;
  isAnalyzing: boolean;
  scriptSessionId?: string | null;
  scriptEnabled?: boolean;
}

export default function AnalysisPlan({
  plan,
  onApprove,
  isAnalyzing,
  scriptSessionId,
  scriptEnabled,
}: AnalysisPlanProps) {
  return (
    <div className="space-y-4">
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <div className="prose-healthlab">
          <ReactMarkdown>{plan}</ReactMarkdown>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onApprove}
          disabled={isAnalyzing}
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
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Approve &amp; Run Analysis
            </>
          )}
        </button>

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
