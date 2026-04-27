"use client";

import { useCallback } from "react";
import StepCard from "../StepCard";
import AnalysisPlan from "../AnalysisPlan";
import AgentRunPanel from "../AgentRunPanel";
import CleaningSummary from "../CleaningSummary";
import FindingsText from "../FindingsText";
import LimitationsBox from "../LimitationsBox";
import FollowUpList from "../FollowUpList";
import ExportButton from "../ExportButton";
import ChartGallery from "../ChartGallery";
import StatsPanel from "../StatsPanel";
import { useSession } from "@/hooks/useSession";
import { streamAnalysis } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import type { AnalyzeResponse, CodeStep } from "@/types";

export default function PlanTab() {
  const { state, dispatch } = useSession();
  const { step, profileResult, analysisResult, sessionId, uploadResult, codeStepEvents } = state;

  const handleApproveAndAnalyze = useCallback(async () => {
    if (!sessionId) return;
    dispatch({ type: "CODE_STEPS_RESET" });
    dispatch({ type: "SET_STEP", step: "analyzing" });
    try {
      const question = state.literatureResult?.question || null;
      const res = await streamAnalysis(sessionId, question);
      await consumeAgentStream(res, (event) => {
        if (event.type === "code_step") {
          const e = event as unknown as { type: "code_step"; step: CodeStep };
          dispatch({ type: "CODE_STEP_EVENT", step: e.step });
        } else if (event.type === "result") {
          const data = (event as { type: "result"; data: Record<string, unknown> }).data;
          if (data.ok === false) {
            dispatch({ type: "SET_ERROR", error: String(data.error ?? "Analysis failed.") });
          } else {
            dispatch({ type: "SET_ANALYSIS", payload: data as unknown as AnalyzeResponse });
          }
        } else if (event.type === "error") {
          dispatch({ type: "SET_ERROR", error: String((event as { message?: string }).message ?? "Analysis error.") });
        }
      });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  }, [sessionId, dispatch, state.literatureResult?.question]);

  if (!profileResult) {
    return (
      <div className="text-sm text-slate-400 px-2 py-8">
        The analysis plan appears here once the dataset has been profiled.
      </div>
    );
  }

  if (!profileResult.analysis_plan) {
    return (
      <div className="text-sm text-slate-400 px-2 py-8 space-y-2">
        <p>No LLM analysis was requested for this run.</p>
        <p className="text-xs text-slate-400">
          Check &quot;LLM analysis&quot; in the sidebar before running the pipeline to
          generate an analysis plan and findings.
        </p>
      </div>
    );
  }

  const totalCharts = (analysisResult?.steps || []).reduce(
    (n, s) => n + s.charts.length,
    0,
  );

  return (
    <div className="space-y-4">
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
          scriptSessionId={sessionId}
          scriptEnabled={!!analysisResult}
          sessionId={sessionId}
          onPlanChange={(newPlan) => dispatch({ type: "SET_PLAN", plan: newPlan })}
        />
      </StepCard>

      {step === "analyzing" && (
        <StepCard title="Agent Working" status="loading" collapsible={false}>
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <div className="w-3 h-3 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
              {codeStepEvents.length === 0
                ? <span>Writing and executing Python to investigate your question…</span>
                : <span>{codeStepEvents.length} step{codeStepEvents.length !== 1 ? "s" : ""} completed — working on next…</span>
              }
            </div>
            {codeStepEvents.length > 0 && sessionId && (
              <AgentRunPanel steps={codeStepEvents} sessionId={sessionId} />
            )}
          </div>
        </StepCard>
      )}

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
            title="Agent Analysis Run"
            stepNumber={5}
            status="done"
            badge={`${analysisResult.steps.length} steps · ${totalCharts} charts`}
          >
            {sessionId && (
              <AgentRunPanel
                steps={analysisResult.steps}
                sessionId={sessionId}
              />
            )}
          </StepCard>

          {analysisResult.charts?.length > 0 && (
            <StepCard
              title="Exploratory Charts"
              stepNumber={6}
              status="done"
              collapsible
              defaultOpen
              badge={`${analysisResult.charts.length} charts`}
            >
              <ChartGallery charts={analysisResult.charts} />
            </StepCard>
          )}

          {analysisResult.stats?.length > 0 && (
            <StepCard
              title="Summary Statistics"
              stepNumber={7}
              status="done"
              collapsible
              defaultOpen={false}
              badge={`${analysisResult.stats.length} columns`}
            >
              <StatsPanel stats={analysisResult.stats} />
            </StepCard>
          )}

          {analysisResult.summary && (
            <StepCard title="Summary" stepNumber={8} status="done">
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                {analysisResult.summary}
              </p>
            </StepCard>
          )}

          <StepCard title="Key Findings" stepNumber={9} status="done">
            <FindingsText findings={analysisResult.findings} />
          </StepCard>

          {analysisResult.limitations && (
            <StepCard title="Limitations" stepNumber={10} status="done">
              <LimitationsBox limitations={analysisResult.limitations} />
            </StepCard>
          )}

          {analysisResult.follow_up && (
            <StepCard
              title="Suggested Follow-Up Research"
              stepNumber={11}
              status="done"
            >
              <FollowUpList followUp={analysisResult.follow_up} />
            </StepCard>
          )}

          {sessionId && uploadResult && (
            <StepCard title="Export Research Memo" stepNumber={12} status="done">
              <ExportButton
                sessionId={sessionId}
                filename={uploadResult.filename}
              />
            </StepCard>
          )}
        </>
      )}
    </div>
  );
}
