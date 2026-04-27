"use client";

import { useState } from "react";

const EXAMPLES = [
  "Do NYC Uber pickups peak at different hours by borough?",
  "How does flu vaccination relate to hospitalization rates by state?",
  "Has California asthma ER visit rate changed since 2020?",
];

const STEPS = [
  {
    n: 1,
    title: "Ingest",
    body: "Upload a CSV or describe a question — the agent searches open-data catalogs for you.",
  },
  {
    n: 2,
    title: "Profile",
    body: "Auto-detect column types, missing values, and outliers. Build exploratory charts.",
  },
  {
    n: 3,
    title: "Plan",
    body: "Claude proposes a tailored 5–7-step analysis plan you can edit before running.",
  },
  {
    n: 4,
    title: "Analyze",
    body: "Cleaning agent runs, hypotheses are generated, stats tests check assumptions live.",
  },
  {
    n: 5,
    title: "Memo",
    body: "Findings, limitations, and follow-up questions — exportable as Markdown.",
  },
];

const DELIVERABLES = [
  {
    title: "Live agent reasoning",
    body: "Watch each tool call and result stream as the agent works.",
  },
  {
    title: "Auto-generated charts",
    body: "Bar, scatter, histogram, box, and heatmap — picked from the data.",
  },
  {
    title: "Exportable memo",
    body: "Findings, limitations, and follow-up questions in Markdown.",
  },
];

function focusSidebarQuestion(prefill?: string) {
  if (typeof window === "undefined") return;
  const el = document.getElementById(
    "sidebar-discover-question",
  ) as HTMLTextAreaElement | null;
  if (prefill) {
    window.dispatchEvent(
      new CustomEvent("healthlab:set-discover-question", { detail: prefill }),
    );
  }
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.focus();
}

function focusSidebarUpload() {
  if (typeof window === "undefined") return;
  const el = document.getElementById("sidebar-upload");
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ring-2", "ring-teal-300", "rounded-lg");
  window.setTimeout(() => {
    el.classList.remove("ring-2", "ring-teal-300", "rounded-lg");
  }, 1400);
}

export default function WelcomeState() {
  const [howOpen, setHowOpen] = useState(false);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Hero */}
      <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-teal-50 via-white to-sky-50 px-6 py-7">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500 to-sky-500 flex items-center justify-center shadow-sm">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-800">
              Welcome to HealthLab Agent
            </h1>
            <p className="text-xs text-slate-500">
              Public-health research, agent-driven.
            </p>
          </div>
        </div>
        <p className="text-sm text-slate-600 leading-relaxed max-w-2xl">
          Turn a CSV — or just a research question — into a reproducible
          analysis. The agent profiles, cleans, charts, tests, and explains
          your data, with every reasoning step shown live.
        </p>
      </div>

      {/* Two CTA cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <button
          onClick={() => focusSidebarQuestion()}
          className="group text-left rounded-xl border border-slate-200 bg-white px-5 py-4 hover:border-teal-300 hover:shadow-sm transition-all"
        >
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-8 h-8 rounded-lg bg-teal-50 flex items-center justify-center">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#14b8a6"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m21 21-4.3-4.3" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-800">
              Ask a research question
            </p>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            The discovery agent searches federal, state, and city open-data
            catalogs and assembles an analysis-ready dataset.
          </p>
          <p className="text-[11px] text-teal-600 mt-2 group-hover:underline">
            Open the question box →
          </p>
        </button>

        <button
          onClick={focusSidebarUpload}
          className="group text-left rounded-xl border border-slate-200 bg-white px-5 py-4 hover:border-sky-300 hover:shadow-sm transition-all"
        >
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-8 h-8 rounded-lg bg-sky-50 flex items-center justify-center">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#0ea5e9"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-800">
              Upload a CSV
            </p>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Drag-drop any CSV. The agent profiles types, missing values, and
            outliers, then proposes a tailored plan.
          </p>
          <p className="text-[11px] text-sky-600 mt-2 group-hover:underline">
            Jump to the upload zone →
          </p>
        </button>
      </div>

      {/* Example questions */}
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          Try an example
        </p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              onClick={() => focusSidebarQuestion(q)}
              className="text-left text-xs px-3 py-2 rounded-full border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50 text-slate-600 transition-all"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* What happens — 5-step strip */}
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          What happens after you start
        </p>
        <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
          {STEPS.map((s) => (
            <li
              key={s.n}
              className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5"
            >
              <p className="text-[10px] font-mono text-teal-500 mb-0.5">
                step {s.n}
              </p>
              <p className="text-xs font-semibold text-slate-700 mb-1">
                {s.title}
              </p>
              <p className="text-[11px] text-slate-500 leading-snug">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>

      {/* What you'll get */}
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          What you&apos;ll get
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {DELIVERABLES.map((c) => (
            <div
              key={c.title}
              className="rounded-lg border border-slate-100 bg-white px-3 py-2.5"
            >
              <p className="text-xs font-semibold text-slate-700 mb-0.5">
                {c.title}
              </p>
              <p className="text-[11px] text-slate-500 leading-snug">
                {c.body}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div className="rounded-lg border border-slate-100 bg-white">
        <button
          onClick={() => setHowOpen((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <span>How it works under the hood</span>
          <span className="text-slate-400 text-base leading-none">
            {howOpen ? "−" : "+"}
          </span>
        </button>
        {howOpen && (
          <div className="px-4 pb-3 text-[11px] text-slate-500 leading-relaxed space-y-2">
            <p>
              Four agentic loops drive the system:{" "}
              <strong className="text-slate-600">CDC discovery</strong>{" "}
              (Socrata catalog search and join), an{" "}
              <strong className="text-slate-600">auto-cleaning</strong> agent,
              a <strong className="text-slate-600">hypothesis generator</strong>
              , and a free-form{" "}
              <strong className="text-slate-600">statistical test</strong>{" "}
              agent that checks assumptions and falls back to non-parametric
              tests when needed.
            </p>
            <p>
              The LLM never writes pandas or scipy directly — it picks named
              ops from small fixed vocabularies and supplies arguments. Each
              loop observes state after every op and self-corrects when one
              fails.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
