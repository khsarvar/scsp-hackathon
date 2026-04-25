"use client";

import clsx from "clsx";
import type { AgentEvent } from "@/types";

interface ThoughtStreamProps {
  events: AgentEvent[];
  isStreaming?: boolean;
  emptyHint?: string;
}

const ICONS: Record<string, string> = {
  thought: "💭",
  tool_call: "🔧",
  tool_result: "✓",
  final: "🏁",
  error: "⚠️",
  result: "📦",
};

function formatArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const entries = Object.entries(args as Record<string, unknown>);
  return entries
    .slice(0, 4)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
}

export default function ThoughtStream({ events, isStreaming, emptyHint }: ThoughtStreamProps) {
  if (events.length === 0) {
    return (
      <div className="text-xs text-slate-400 italic px-1 py-2">
        {emptyHint || "The agent's reasoning will appear here."}
      </div>
    );
  }

  return (
    <div className="space-y-1.5 font-mono text-xs">
      {events.map((e, i) => {
        const t = (e as { type?: string }).type ?? "unknown";
        const icon = ICONS[t] ?? "•";

        if (t === "thought") {
          const ev = e as Extract<AgentEvent, { type: "thought" }>;
          return (
            <div key={i} className="text-slate-500 italic leading-relaxed">
              <span className="mr-2">{icon}</span>
              {ev.text}
            </div>
          );
        }
        if (t === "tool_call") {
          const ev = e as Extract<AgentEvent, { type: "tool_call" }>;
          return (
            <div key={i} className="text-slate-700">
              <span className="mr-2">{icon}</span>
              <span className="font-semibold text-teal-700">{ev.name}</span>
              <span className="text-slate-400">({formatArgs(ev.args)})</span>
              {ev.rationale && <span className="text-slate-400"> — {ev.rationale}</span>}
            </div>
          );
        }
        if (t === "tool_result") {
          const ev = e as Extract<AgentEvent, { type: "tool_result" }>;
          return (
            <div key={i} className="text-slate-500 pl-5">
              <span className="mr-2 text-emerald-500">{icon}</span>
              {ev.summary}
            </div>
          );
        }
        if (t === "final") {
          const ev = e as Extract<AgentEvent, { type: "final" }>;
          const extra = ev.primary_alias ? ` → primary alias \`${ev.primary_alias}\`` : "";
          return (
            <div key={i} className="text-teal-700 font-semibold pt-1">
              <span className="mr-2">{icon}</span>
              done{extra}
              {ev.summary && <span className="font-normal text-slate-600"> — {ev.summary}</span>}
            </div>
          );
        }
        if (t === "error") {
          const ev = e as Extract<AgentEvent, { type: "error" }>;
          return (
            <div key={i} className="text-red-600">
              <span className="mr-2">{icon}</span>
              {ev.message}
            </div>
          );
        }
        if (t === "result") {
          return null; // result events carry payloads, not display
        }
        return (
          <div key={i} className="text-slate-400">
            <span className="mr-2">{icon}</span>
            {JSON.stringify(e).slice(0, 200)}
          </div>
        );
      })}
      {isStreaming && (
        <div className={clsx("flex items-center gap-2 text-slate-400 text-xs pt-1")}>
          <div className="w-3 h-3 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
          thinking...
        </div>
      )}
    </div>
  );
}
