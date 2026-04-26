"use client";

import StepCard from "../StepCard";
import ThoughtStream from "../ThoughtStream";
import DataPreview from "../DataPreview";
import ProfilingReport from "../ProfilingReport";
import JoinDecision from "../JoinDecision";
import DatasetPicker from "../DatasetPicker";
import ChartGallery from "../ChartGallery";
import { useSession } from "@/hooks/useSession";
import { streamDiscoverWithSelection } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import type { AgentEvent, DiscoverResultPayload, UploadResponse } from "@/types";
import { profileDataset } from "@/lib/api";
import { useState, useEffect, useRef } from "react";

export default function DiscoverTab() {
  const { state, dispatch } = useSession();
  const { step, uploadResult, profileResult, discoverEvents, recommendations, recommendationQuestion } = state;
  const [pickerLoading, setPickerLoading] = useState(false);
  const autoSkippedRef = useRef<string | null>(null);

  // Auto-skip the picker when the catalog returned no results
  useEffect(() => {
    if (
      step === "recommended" &&
      recommendations !== null &&
      recommendations.length === 0 &&
      recommendationQuestion &&
      autoSkippedRef.current !== recommendationQuestion
    ) {
      autoSkippedRef.current = recommendationQuestion;
      runDiscover(recommendationQuestion, []);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, recommendations, recommendationQuestion]);

  const profileAfterUpload = async (upload: UploadResponse) => {
    dispatch({ type: "SET_UPLOAD", payload: upload });
    dispatch({ type: "SET_STEP", step: "profiling" });
    try {
      const profile = await profileDataset(
        upload.session_id,
        state.pipelineConfig.runAnalysis,
      );
      dispatch({ type: "SET_PROFILE", payload: profile });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  };

  const runDiscover = async (question: string, selectedIds: string[]) => {
    setPickerLoading(true);
    dispatch({ type: "CLEAR_RECOMMENDATIONS" });
    dispatch({ type: "DISCOVER_RESET" });
    dispatch({ type: "SET_STEP", step: "discovering" });
    try {
      const res = await streamDiscoverWithSelection(question, selectedIds);
      const payloadHolder: { value: DiscoverResultPayload | null; error: string | null } = {
        value: null,
        error: null,
      };
      await consumeAgentStream(res, (event: AgentEvent) => {
        dispatch({ type: "DISCOVER_EVENT", event });
        if (event.type === "result") {
          const data = (event as { data: Record<string, unknown> }).data;
          if (data.ok) {
            payloadHolder.value = data as unknown as DiscoverResultPayload;
          } else if (typeof data.error === "string") {
            payloadHolder.error = data.error;
          }
        }
      });
      const payload = payloadHolder.value;
      if (payload) {
        if (payload.pending_join && payload.candidates && payload.suggested_alias) {
          dispatch({
            type: "SET_JOIN_CANDIDATES",
            candidates: payload.candidates,
            suggestedAlias: payload.suggested_alias,
            sessionId: payload.session_id,
          });
          dispatch({ type: "SET_STEP", step: "join_decision" });
        } else {
          await profileAfterUpload({
            session_id: payload.session_id,
            filename: payload.filename!,
            row_count: payload.row_count!,
            col_count: payload.col_count!,
            columns: payload.columns!,
            preview_rows: payload.preview_rows!,
            file_size_bytes: payload.file_size_bytes!,
            provenance: payload.provenance,
          });
        }
      } else {
        dispatch({ type: "SET_ERROR", error: payloadHolder.error ?? "Discovery agent did not produce a dataset." });
      }
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    } finally {
      setPickerLoading(false);
    }
  };

  if (step === "recommending") {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5 flex items-center gap-4">
          <div className="w-5 h-5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-slate-700">Searching open-data catalogs...</p>
            <p className="text-xs text-slate-400 mt-0.5">Finding relevant datasets for your question</p>
          </div>
        </div>
      </div>
    );
  }

  if (step === "recommended" && recommendations !== null && recommendationQuestion) {
    if (recommendations.length === 0) {
      return (
        <div className="rounded-xl border border-slate-200 bg-white p-5 flex items-center gap-4">
          <div className="w-5 h-5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <p className="text-sm text-slate-500">No catalog results — starting discovery agent...</p>
        </div>
      );
    }
    return (
      <div className="space-y-4">
        <DatasetPicker
          recommendations={recommendations}
          question={recommendationQuestion}
          isLoading={pickerLoading}
          onConfirm={(selectedIds) => runDiscover(recommendationQuestion, selectedIds)}
          onSkip={() => runDiscover(recommendationQuestion, [])}
        />
      </div>
    );
  }

  if (step === "discovering") {
    return (
      <div className="space-y-4">
        <StepCard title="Discovering datasets" status="loading" collapsible={false}>
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              The agent is searching open-data catalogs (federal, state, and city),
              fetching candidate datasets, and joining them as needed. Live reasoning
              below.
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

  if (step === "join_decision") {
    return (
      <div className="space-y-4">
        {discoverEvents.length > 0 && (
          <StepCard
            title="Discovery Trace"
            status="done"
            collapsible
            defaultOpen={false}
            badge={`${discoverEvents.length} events`}
          >
            <ThoughtStream events={discoverEvents} />
          </StepCard>
        )}
        <JoinDecision />
      </div>
    );
  }

  if (!uploadResult && !profileResult && discoverEvents.length === 0) {
    return (
      <div className="text-sm text-slate-400 px-2 py-8">
        No dataset loaded yet. Use the left sidebar to upload a CSV or run a
        discovery search across the open-data catalogs — its activity will appear
        here.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {discoverEvents.length > 0 && (
        <StepCard
          title="Discovery Trace"
          status="done"
          collapsible
          defaultOpen={!uploadResult}
          badge={`${discoverEvents.length} events`}
        >
          <ThoughtStream events={discoverEvents} />
        </StepCard>
      )}

      {uploadResult && (
        <StepCard
          title="Dataset Preview"
          stepNumber={1}
          status={step === "uploading" ? "loading" : "done"}
          collapsible
          defaultOpen={true}
          badge={`${uploadResult.row_count.toLocaleString()} rows`}
        >
          <DataPreview
            rows={uploadResult.preview_rows}
            columns={uploadResult.columns}
            totalRows={uploadResult.row_count}
            provenance={uploadResult.provenance}
          />
        </StepCard>
      )}

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
              <p className="text-sm text-slate-500">
                {state.pipelineConfig.runAnalysis
                  ? "Profiling dataset and generating analysis plan..."
                  : "Profiling dataset and building exploratory charts..."}
              </p>
            </div>
          )}
        </StepCard>
      )}

      {profileResult && profileResult.charts && profileResult.charts.length > 0 && (
        <StepCard
          title="Exploratory Charts"
          stepNumber={3}
          status="done"
          collapsible
          defaultOpen
          badge={`${profileResult.charts.length} charts`}
        >
          <ChartGallery charts={profileResult.charts} />
        </StepCard>
      )}
    </div>
  );
}
