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
