"use client";

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
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
          <ChartGrid charts={step.charts} sessionId={sessionId} />
        )}
      </div>
    </div>
  );
}

function ChartGrid({ charts, sessionId }: { charts: string[]; sessionId: string }) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const close = useCallback(() => setLightboxIndex(null), []);
  const prev = useCallback(() => setLightboxIndex((i) => (i !== null ? (i - 1 + charts.length) % charts.length : null)), [charts.length]);
  const next = useCallback(() => setLightboxIndex((i) => (i !== null ? (i + 1) % charts.length : null)), [charts.length]);

  useEffect(() => {
    if (lightboxIndex === null) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightboxIndex, close, prev, next]);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {charts.map((c, i) => (
          <button
            key={c}
            type="button"
            onClick={() => setLightboxIndex(i)}
            className="group block rounded-lg border border-slate-100 overflow-hidden bg-white hover:border-teal-300 transition-colors text-left w-full cursor-zoom-in"
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
          </button>
        ))}
      </div>

      {lightboxIndex !== null && createPortal(
        <div className="fixed inset-0 z-50 flex flex-col bg-slate-100">
          {/* Top bar */}
          <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200 shadow-sm">
            <p className="text-sm font-mono text-slate-500 truncate max-w-lg">
              {charts[lightboxIndex]}
            </p>
            <div className="flex items-center gap-3">
              {charts.length > 1 && (
                <span className="text-xs text-slate-400">
                  {lightboxIndex + 1} / {charts.length}
                </span>
              )}
              <button
                type="button"
                onClick={close}
                className="w-8 h-8 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600 flex items-center justify-center text-lg leading-none transition-colors"
                aria-label="Close"
              >
                ×
              </button>
            </div>
          </div>

          {/* Chart area — clicking the background closes */}
          <div className="flex-1 flex items-center justify-center p-8 relative cursor-pointer" onClick={close}>
            {charts.length > 1 && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); prev(); }}
                className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white border border-slate-200 hover:border-teal-400 shadow text-slate-600 hover:text-teal-600 flex items-center justify-center text-xl transition-colors"
                aria-label="Previous"
              >
                ‹
              </button>
            )}

            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={chartUrl(sessionId, charts[lightboxIndex])}
              alt={charts[lightboxIndex]}
              className="rounded-xl shadow-lg max-h-full max-w-full object-contain bg-white cursor-default"
              onClick={(e) => e.stopPropagation()}
            />

            {charts.length > 1 && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); next(); }}
                className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white border border-slate-200 hover:border-teal-400 shadow text-slate-600 hover:text-teal-600 flex items-center justify-center text-xl transition-colors"
                aria-label="Next"
              >
                ›
              </button>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
