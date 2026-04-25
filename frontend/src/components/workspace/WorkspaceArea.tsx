"use client";

import { useCallback } from "react";
import StepCard from "./StepCard";
import DataPreview from "./DataPreview";
import ProfilingReport from "./ProfilingReport";
import AnalysisPlan from "./AnalysisPlan";
import CleaningSummary from "./CleaningSummary";
import StatsPanel from "./StatsPanel";
import ChartGallery from "./ChartGallery";
import FindingsText from "./FindingsText";
import LimitationsBox from "./LimitationsBox";
import FollowUpList from "./FollowUpList";
import ExportButton from "./ExportButton";
import ThoughtStream from "./ThoughtStream";
import HypothesesPanel from "./HypothesesPanel";
import StatsTestPanel from "./StatsTestPanel";
import { useSession } from "@/hooks/useSession";
import { runAnalysis } from "@/lib/api";

export default function WorkspaceArea() {
  const { state, dispatch } = useSession();
  const {
    step,
    uploadResult,
    profileResult,
    analysisResult,
    sessionId,
    error,
    discoverEvents,
  } = state;

  const handleApproveAndAnalyze = useCallback(async () => {
    if (!sessionId) return;
    dispatch({ type: "SET_STEP", step: "analyzing" });
    try {
      const result = await runAnalysis(sessionId);
      dispatch({ type: "SET_ANALYSIS", payload: result });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  }, [sessionId, dispatch]);

  // Discovery loading state
  if (step === "discovering") {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <StepCard
          title="Discovering CDC datasets"
          status="loading"
          collapsible={false}
        >
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              The agent is searching the CDC Socrata catalog, fetching candidate
              datasets, and joining them as needed. Live reasoning below.
            </p>
            <ThoughtStream
              events={discoverEvents}
              isStreaming
              emptyHint="Catalog search starting..."
            />
          </div>
        </StepCard>
      </div>
    );
  }

  // Empty state
  if (step === "idle") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 px-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-500 to-sky-500 flex items-center justify-center shadow-lg">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
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
            { icon: "🤖", title: "Agentic Cleaning", desc: "Live tool-use stream as the agent cleans" },
            { icon: "📈", title: "Real Stats Tests", desc: "Assumption-aware tests with fallbacks" },
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

  // Error state
  if (step === "error") {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 max-w-md text-center">
          <p className="text-red-600 font-semibold mb-1">Something went wrong</p>
          <p className="text-sm text-red-500">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      {/* Step 0: Discovery trace (if this session came from CDC discover) */}
      {discoverEvents.length > 0 && (
        <StepCard
          title="CDC Discovery Trace"
          status="done"
          collapsible
          defaultOpen={false}
          badge={`${discoverEvents.length} events`}
        >
          <ThoughtStream events={discoverEvents} />
        </StepCard>
      )}

      {/* Step 1: Dataset Preview */}
      {uploadResult && (
        <StepCard
          title="Dataset Preview"
          stepNumber={1}
          status={step === "uploading" ? "loading" : "done"}
          collapsible
          defaultOpen={step === "uploading"}
          badge={`${uploadResult.row_count.toLocaleString()} rows`}
        >
          <DataPreview
            rows={uploadResult.preview_rows}
            columns={uploadResult.columns}
            totalRows={uploadResult.row_count}
          />
        </StepCard>
      )}

      {/* Step 2: Profiling */}
      {(step === "profiling" || profileResult) && (
        <StepCard
          title="Data Quality Report"
          stepNumber={2}
          status={step === "profiling" ? "loading" : "done"}
          collapsible
          defaultOpen={step === "profiling"}
          badge={profileResult ? `${profileResult.col_count} columns` : undefined}
        >
          {profileResult && <ProfilingReport profile={profileResult} />}
          {step === "profiling" && (
            <div className="flex items-center gap-3 py-4">
              <div className="w-5 h-5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Profiling dataset and generating analysis plan...</p>
            </div>
          )}
        </StepCard>
      )}

      {/* Step 3: Analysis Plan */}
      {profileResult && (
        <StepCard
          title="Proposed Analysis Plan"
          stepNumber={3}
          status="done"
          defaultOpen={step === "planned"}
          collapsible
        >
          <AnalysisPlan
            plan={profileResult.analysis_plan}
            onApprove={handleApproveAndAnalyze}
            isAnalyzing={step === "analyzing"}
          />
        </StepCard>
      )}

      {/* Optional research tools — collapsed by default, shown as one card */}
      {profileResult && (
        <StepCard
          title="Research Tools"
          status="done"
          collapsible
          defaultOpen={state.hypotheses.length > 0}
        >
          <div className="divide-y divide-slate-100">
            {/* Testable Hypotheses */}
            <div className="pb-4 space-y-2">
              <p className="text-xs font-semibold text-slate-600">Testable Hypotheses</p>
              <HypothesesPanel />
            </div>

            {/* Free-form statistical question */}
            <div className="pt-4 space-y-2">
              <p className="text-xs font-semibold text-slate-600">Statistical Test</p>
              <StatsTestPanel />
            </div>
          </div>
        </StepCard>
      )}

      {/* Results: Steps 4-10 */}
      {analysisResult && (
        <>
          <StepCard
            title="Data Cleaning Applied"
            stepNumber={4}
            status="done"
            collapsible
            defaultOpen={false}
            badge={`${analysisResult.cleaning_steps.length} steps`}
          >
            <CleaningSummary steps={analysisResult.cleaning_steps} />
          </StepCard>

          <StepCard
            title="Summary Statistics"
            stepNumber={5}
            status="done"
            collapsible
            defaultOpen={false}
          >
            <StatsPanel stats={analysisResult.stats} />
          </StepCard>

          <StepCard
            title="Visualizations"
            stepNumber={6}
            status="done"
            badge={`${analysisResult.charts.length} charts`}
          >
            <ChartGallery charts={analysisResult.charts} />
          </StepCard>

          <StepCard
            title="Key Findings"
            stepNumber={7}
            status="done"
          >
            <FindingsText findings={analysisResult.findings} />
          </StepCard>

          <StepCard
            title="Limitations"
            stepNumber={8}
            status="done"
          >
            <LimitationsBox limitations={analysisResult.limitations} />
          </StepCard>

          <StepCard
            title="Suggested Follow-Up Research"
            stepNumber={9}
            status="done"
          >
            <FollowUpList followUp={analysisResult.follow_up} />
          </StepCard>

          {sessionId && uploadResult && (
            <StepCard
              title="Export Research Memo"
              stepNumber={10}
              status="done"
            >
              <ExportButton sessionId={sessionId} filename={uploadResult.filename} />
            </StepCard>
          )}
        </>
      )}
    </div>
  );
}
