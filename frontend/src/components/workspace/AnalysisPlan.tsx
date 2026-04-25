"use client";

import ReactMarkdown from "react-markdown";

interface AnalysisPlanProps {
  plan: string;
  onApprove: () => void;
  isAnalyzing: boolean;
}

export default function AnalysisPlan({ plan, onApprove, isAnalyzing }: AnalysisPlanProps) {
  return (
    <div className="space-y-4">
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <div className="prose-healthlab">
          <ReactMarkdown>{plan}</ReactMarkdown>
        </div>
      </div>

      <div className="flex items-center gap-3">
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
        <p className="text-xs text-slate-400">
          The agent will clean the data, compute statistics, generate charts, and write a research memo.
        </p>
      </div>
    </div>
  );
}
