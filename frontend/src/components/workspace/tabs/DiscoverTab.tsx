"use client";

import StepCard from "../StepCard";
import ThoughtStream from "../ThoughtStream";
import DataPreview from "../DataPreview";
import ProfilingReport from "../ProfilingReport";
import { useSession } from "@/hooks/useSession";

export default function DiscoverTab() {
  const { state } = useSession();
  const { step, uploadResult, profileResult, discoverEvents } = state;

  if (step === "discovering") {
    return (
      <div className="space-y-4">
        <StepCard title="Discovering CDC datasets" status="loading" collapsible={false}>
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

  if (!uploadResult && !profileResult && discoverEvents.length === 0) {
    return (
      <div className="text-sm text-slate-400 px-2 py-8">
        No dataset loaded yet. Use the left sidebar to upload a CSV or run a CDC
        discovery search — its activity will appear here.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {discoverEvents.length > 0 && (
        <StepCard
          title="CDC Discovery Trace"
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
              <p className="text-sm text-slate-500">Profiling dataset and generating analysis plan...</p>
            </div>
          )}
        </StepCard>
      )}
    </div>
  );
}
