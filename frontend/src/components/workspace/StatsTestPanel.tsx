"use client";

import { useState } from "react";
import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import { useSession } from "@/hooks/useSession";
import { streamAsk } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import ThoughtStream from "./ThoughtStream";
import type { AgentEvent } from "@/types";

export default function StatsTestPanel() {
  const { state, dispatch } = useSession();
  const [question, setQuestion] = useState("");
  const [running, setRunning] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onAsk = async () => {
    const q = question.trim();
    if (!q || !state.sessionId || running) return;
    setRunning(true);
    setError(null);
    setAnswer(null);
    dispatch({ type: "ASK_RESET" });
    try {
      const res = await streamAsk(state.sessionId, q);
      await consumeAgentStream(res, (event: AgentEvent) => {
        dispatch({ type: "ASK_EVENT", event });
        if (event.type === "result") {
          const data = (event as { data: Record<string, unknown> }).data;
          if (typeof data.answer === "string") {
            setAnswer(data.answer);
          }
        }
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Ask a free-form question. The agent will pick the right test, check assumptions,
        and give a plain-English answer.
      </p>

      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && onAsk()}
          placeholder="e.g. Does outcome differ between treatment and control groups?"
          disabled={running}
          className={clsx(
            "flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm",
            "placeholder:text-slate-300 focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-400/20",
            running && "opacity-50 cursor-not-allowed"
          )}
        />
        <button
          onClick={onAsk}
          disabled={running || !question.trim()}
          className={clsx(
            "px-4 py-2 rounded-lg text-sm font-semibold transition-all",
            !running && question.trim()
              ? "bg-teal-500 hover:bg-teal-600 text-white shadow-sm"
              : "bg-slate-100 text-slate-300 cursor-not-allowed"
          )}
        >
          {running ? "Asking..." : "Ask"}
        </button>
      </div>

      <div className="rounded-lg bg-slate-50/60 border border-slate-100 p-3 max-h-64 overflow-y-auto">
        <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">
          Agent reasoning
        </p>
        <ThoughtStream
          events={state.askEvents}
          isStreaming={running}
          emptyHint="Agent reasoning, test choice, and assumption checks will stream here."
        />
      </div>

      {answer && (
        <div className="rounded-lg border border-teal-100 bg-teal-50/30 p-3">
          <p className="text-xs font-semibold text-teal-700 mb-1.5">Answer</p>
          <div className="prose-healthlab text-sm text-slate-700">
            <ReactMarkdown>{answer}</ReactMarkdown>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
