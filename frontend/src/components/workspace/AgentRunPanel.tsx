"use client";

import { useState } from "react";
import clsx from "clsx";
import type { CodeStep } from "@/types";
import { chartUrl } from "@/lib/api";

interface AgentRunPanelProps {
  steps: CodeStep[];
  sessionId: string;
}

export default function AgentRunPanel({ steps, sessionId }: AgentRunPanelProps) {
  if (!steps.length) {
    return (
      <p className="text-xs text-slate-400 italic">
        No agent code-execution steps were recorded for this analysis.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {steps.map((s, i) => (
        <StepCard key={i} step={s} index={i + 1} sessionId={sessionId} />
      ))}
    </div>
  );
}

function StepCard({
  step,
  index,
  sessionId,
}: {
  step: CodeStep;
  index: number;
  sessionId: string;
}) {
  const [showCode, setShowCode] = useState(false);
  const [showStdout, setShowStdout] = useState(true);

  return (
    <div
      className={clsx(
        "rounded-lg border bg-white",
        step.ok ? "border-slate-200" : "border-red-200",
      )}
    >
      <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 text-xs">
        <span
          className={clsx(
            "inline-flex items-center justify-center w-5 h-5 rounded-full font-bold text-[10px]",
            step.ok ? "bg-teal-500 text-white" : "bg-red-100 text-red-700",
          )}
        >
          {index}
        </span>
        <p className="text-slate-700 flex-1 font-medium">
          {step.rationale || (step.ok ? "Run code" : "Failed step")}
        </p>
        {step.charts.length > 0 && (
          <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-full">
            {step.charts.length} chart{step.charts.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <div className="px-3 py-2.5 space-y-2.5">
        <button
          type="button"
          onClick={() => setShowCode((s) => !s)}
          className="text-[11px] text-slate-400 hover:text-slate-700"
        >
          {showCode ? "▼ Hide" : "▶ Show"} code ({step.code.split("\n").length} lines)
        </button>
        {showCode && (
          <pre className="text-[11px] leading-relaxed bg-slate-900 text-slate-100 rounded-md p-3 overflow-x-auto">
            <code>{step.code}</code>
          </pre>
        )}

        {step.stdout && (
          <div>
            <button
              type="button"
              onClick={() => setShowStdout((s) => !s)}
              className="text-[11px] text-slate-400 hover:text-slate-700"
            >
              {showStdout ? "▼ Hide" : "▶ Show"} stdout
            </button>
            {showStdout && (
              <pre className="mt-1 text-[11px] leading-relaxed bg-slate-50 border border-slate-100 text-slate-700 rounded-md p-3 overflow-x-auto whitespace-pre-wrap">
                {step.stdout}
              </pre>
            )}
          </div>
        )}

        {step.stderr && (
          <pre className="text-[11px] leading-relaxed bg-red-50 border border-red-100 text-red-700 rounded-md p-3 overflow-x-auto whitespace-pre-wrap">
            {step.stderr}
          </pre>
        )}

        {step.charts.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {step.charts.map((c) => (
              <a
                key={c}
                href={chartUrl(sessionId, c)}
                target="_blank"
                rel="noopener noreferrer"
                className="group block rounded-lg border border-slate-100 overflow-hidden bg-white hover:border-teal-300 transition-colors"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={chartUrl(sessionId, c)}
                  alt={c}
                  className="w-full h-auto"
                />
                <p className="text-[10px] text-slate-500 px-2 py-1 truncate font-mono group-hover:text-teal-700">
                  {c}
                </p>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
