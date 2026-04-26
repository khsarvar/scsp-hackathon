"use client";

import { useEffect, useRef } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import DiscoverTab from "./tabs/DiscoverTab";
import LiteratureTab from "./tabs/LiteratureTab";
import PlanTab from "./tabs/PlanTab";
import { useSession } from "@/hooks/useSession";
import type { WorkspaceTab } from "@/types";

const STEP_TO_TAB: Record<string, WorkspaceTab> = {
  discovering: "discover",
  uploading: "discover",
  preview: "discover",
  profiling: "discover",
  planned: "plan",
  analyzing: "plan",
  results: "plan",
};

export default function WorkspaceArea() {
  const { state, dispatch } = useSession();
  const lastStep = useRef<string | null>(null);

  // Auto-switch tab as the workflow progresses, but don't override an explicit user pick
  // for the same step.
  useEffect(() => {
    if (lastStep.current === state.step) return;
    lastStep.current = state.step;
    const target = STEP_TO_TAB[state.step];
    if (target && target !== state.activeTab) {
      dispatch({ type: "SET_ACTIVE_TAB", tab: target });
    }
  }, [state.step, state.activeTab, dispatch]);

  // Idle empty state: no dataset yet, full-screen welcome
  if (state.step === "idle") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 px-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-500 to-sky-500 flex items-center justify-center shadow-lg">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-slate-800 mb-2">HealthLab Agent</h2>
          <p className="text-slate-500 max-w-sm text-sm leading-relaxed">
            Turn public health data into reproducible insights. Upload a CSV, load a
            demo, or ask the agent to discover a CDC dataset for you.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-4 max-w-lg w-full">
          {[
            { icon: "🛰️", title: "CDC Discover", desc: "Agent searches and fetches public datasets" },
            { icon: "📚", title: "Literature Review", desc: "PubMed-backed prior-research summaries" },
            { icon: "📈", title: "Plan & Analyze", desc: "Assumption-aware tests, charts, exports" },
          ].map((f) => (
            <div key={f.title} className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm text-left">
              <div className="text-2xl mb-2">{f.icon}</div>
              <p className="text-xs font-semibold text-slate-700">{f.title}</p>
              <p className="text-xs text-slate-400 mt-0.5">{f.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400">
          Pick a data source in the left sidebar to begin.
        </p>
      </div>
    );
  }

  if (state.step === "error") {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 max-w-md text-center">
          <p className="text-red-600 font-semibold mb-1">Something went wrong</p>
          <p className="text-sm text-red-500">{state.error}</p>
        </div>
      </div>
    );
  }

  const onTabChange = (tab: string) =>
    dispatch({ type: "SET_ACTIVE_TAB", tab: tab as WorkspaceTab });

  return (
    <Tabs
      value={state.activeTab}
      onChange={onTabChange}
      className="h-full"
    >
      <TabsList>
        <TabsTrigger
          value="discover"
          badge={state.discoverEvents.length > 0 ? state.discoverEvents.length : undefined}
        >
          Discover
        </TabsTrigger>
        <TabsTrigger
          value="literature"
          badge={state.literatureResult ? state.literatureResult.articles.length : undefined}
        >
          Literature
        </TabsTrigger>
        <TabsTrigger
          value="plan"
          badge={state.analysisResult ? "✓" : undefined}
        >
          Plan &amp; Analysis
        </TabsTrigger>
      </TabsList>

      <TabsContent value="discover" className="px-6 py-5">
        <div className="max-w-4xl mx-auto">
          <DiscoverTab />
        </div>
      </TabsContent>
      <TabsContent value="literature" className="px-6 py-5">
        <div className="max-w-4xl mx-auto">
          <LiteratureTab />
        </div>
      </TabsContent>
      <TabsContent value="plan" className="px-6 py-5">
        <div className="max-w-4xl mx-auto">
          <PlanTab />
        </div>
      </TabsContent>
    </Tabs>
  );
}
