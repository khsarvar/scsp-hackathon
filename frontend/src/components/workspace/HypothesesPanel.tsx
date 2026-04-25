"use client";

import { useState } from "react";
import clsx from "clsx";
import { useSession } from "@/hooks/useSession";
import { generateHypotheses, runStatsTest } from "@/lib/api";
import type { Hypothesis } from "@/types";

export default function HypothesesPanel() {
  const { state, dispatch } = useSession();
  const [loading, setLoading] = useState(false);
  const [runningIndex, setRunningIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hypotheses = state.hypotheses;

  const onGenerate = async () => {
    if (!state.sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generateHypotheses(state.sessionId, 4);
      dispatch({ type: "SET_HYPOTHESES", hypotheses: res.hypotheses });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const onRun = async (h: Hypothesis, idx: number) => {
    if (!state.sessionId || !h.test_type) return;
    setRunningIndex(idx);
    setError(null);
    try {
      const res = await runStatsTest(state.sessionId, h.test_type, h.args || {});
      dispatch({ type: "SET_TEST_RESULT", result: res });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunningIndex(null);
    }
  };

  return (
    <div className="space-y-3">
      {hypotheses.length === 0 ? (
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Generate testable research questions tailored to your dataset.
          </p>
          <button
            onClick={onGenerate}
            disabled={loading}
            className={clsx(
              "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              loading
                ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                : "bg-teal-500 hover:bg-teal-600 text-white shadow-sm"
            )}
          >
            {loading ? "Generating..." : "Generate hypotheses"}
          </button>
        </div>
      ) : (
        <>
          {hypotheses.map((h, i) => (
            <div
              key={i}
              className="rounded-lg border border-slate-100 bg-slate-50/40 p-3 space-y-1"
            >
              <p className="text-sm font-medium text-slate-800">{h.question}</p>
              <p className="text-xs text-slate-500">
                Test: <code className="text-teal-700">{h.test_type ?? "?"}</code>
                {h.variables && h.variables.length > 0 && (
                  <span className="ml-2">
                    Vars: {h.variables.map((v) => <code key={v} className="text-slate-700 mx-0.5">{v}</code>)}
                  </span>
                )}
              </p>
              {h.rationale && (
                <p className="text-xs text-slate-500 italic">{h.rationale}</p>
              )}
              {h.test_type && (
                <button
                  onClick={() => onRun(h, i)}
                  disabled={runningIndex !== null}
                  className={clsx(
                    "mt-1.5 text-xs px-2.5 py-1 rounded-md border transition-all",
                    runningIndex === i
                      ? "border-teal-300 bg-teal-50 text-teal-700"
                      : "border-slate-200 hover:border-teal-300 hover:bg-teal-50 text-slate-700"
                  )}
                >
                  {runningIndex === i ? "Running..." : "Run this test"}
                </button>
              )}
            </div>
          ))}
          <button
            onClick={onGenerate}
            disabled={loading}
            className="text-xs text-slate-500 hover:text-teal-700"
          >
            {loading ? "Regenerating..." : "↻ Regenerate hypotheses"}
          </button>
        </>
      )}

      {state.lastTestResult && (
        <div className="mt-2 rounded-lg border border-teal-100 bg-teal-50/30 p-3">
          <p className="text-xs font-semibold text-teal-700 mb-1">Latest test result</p>
          <p className="text-xs text-slate-600 mb-1">
            <code>{state.lastTestResult.test}</code>
            {state.lastTestResult.result.test &&
              state.lastTestResult.result.test !== state.lastTestResult.test && (
                <span className="text-slate-400"> → {state.lastTestResult.result.test}</span>
              )}
          </p>
          {state.lastTestResult.result.error ? (
            <p className="text-xs text-red-600">{state.lastTestResult.result.error}</p>
          ) : (
            <>
              {state.lastTestResult.result.interpretation && (
                <p className="text-xs text-slate-700">
                  {state.lastTestResult.result.interpretation}
                </p>
              )}
              {state.lastTestResult.result.assumption_check && (
                <p className="text-xs text-slate-500 mt-1">
                  Normality satisfied:{" "}
                  <span
                    className={
                      state.lastTestResult.result.assumption_check.normality_satisfied
                        ? "text-emerald-600"
                        : "text-amber-600"
                    }
                  >
                    {state.lastTestResult.result.assumption_check.normality_satisfied
                      ? "yes"
                      : "no — non-parametric fallback applied"}
                  </span>
                </p>
              )}
            </>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
