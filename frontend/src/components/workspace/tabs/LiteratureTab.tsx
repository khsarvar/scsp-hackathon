"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import StepCard from "../StepCard";
import ThoughtStream from "../ThoughtStream";
import { useSession } from "@/hooks/useSession";
import { streamLiterature } from "@/lib/api";
import { consumeAgentStream } from "@/hooks/useAgentStream";
import type { AgentEvent, LiteratureResult } from "@/types";

function defaultQuestion(state: ReturnType<typeof useSession>["state"]): string {
  if (state.literatureResult?.question) return state.literatureResult.question;
  if (state.hypotheses[0]?.question) return state.hypotheses[0].question;
  if (state.uploadResult?.filename) {
    const base = state.uploadResult.filename.replace(/^cdc_/, "").replace(/\.csv$/i, "");
    return `Recent research on ${base.replace(/[_-]+/g, " ")}`;
  }
  return "";
}

export default function LiteratureTab() {
  const { state, dispatch } = useSession();
  const [question, setQuestion] = useState<string>(() => defaultQuestion(state));
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-suggest a question when a new dataset arrives and the field is still empty
  useEffect(() => {
    if (!question) setQuestion(defaultQuestion(state));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.uploadResult?.filename, state.hypotheses.length]);

  const onRun = async () => {
    const q = question.trim();
    if (!q || running) return;
    setRunning(true);
    setError(null);
    dispatch({ type: "LITERATURE_RESET" });
    try {
      const res = await streamLiterature(q, state.sessionId);
      await consumeAgentStream(res, (event: AgentEvent) => {
        dispatch({ type: "LITERATURE_EVENT", event });
        if (event.type === "result") {
          const data = (event as { data: Record<string, unknown> }).data;
          if (data.ok && typeof data.summary === "string") {
            const result: LiteratureResult = {
              question: (data.question as string) ?? q,
              summary: data.summary,
              articles: (data.articles as LiteratureResult["articles"]) ?? [],
            };
            dispatch({ type: "SET_LITERATURE_RESULT", result });
          } else if (typeof data.error === "string") {
            setError(data.error);
          }
        }
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const result = state.literatureResult;

  return (
    <div className="space-y-4">
      <StepCard
        title="Research Literature Review"
        status={running ? "loading" : result ? "done" : "pending"}
        collapsible={false}
      >
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            Search PubMed for prior peer-reviewed work on a research question. The agent
            picks the best query, fetches abstracts, and summarizes how each paper
            relates to your question.
          </p>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onRun();
              }
            }}
            placeholder="e.g. COVID-19 vaccine effectiveness in adults over 65 (Enter to submit, Shift+Enter for newline)"
            rows={2}
            disabled={running}
            className={clsx(
              "w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm",
              "placeholder:text-slate-300 focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-400/20",
              running && "opacity-50 cursor-not-allowed",
            )}
          />
          <div className="flex items-center gap-3">
            <button
              onClick={onRun}
              disabled={running || !question.trim()}
              className={clsx(
                "px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm",
                running || !question.trim()
                  ? "bg-slate-100 text-slate-300 cursor-not-allowed"
                  : "bg-teal-500 hover:bg-teal-600 text-white",
              )}
            >
              {running ? "Searching PubMed..." : result ? "Re-run search" : "Run literature review"}
            </button>
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>
        </div>
      </StepCard>

      {(state.literatureEvents.length > 0 || running) && (
        <StepCard
          title="Agent Reasoning"
          status={running ? "loading" : "done"}
          collapsible
          defaultOpen={running}
        >
          <ThoughtStream
            events={state.literatureEvents}
            isStreaming={running}
            emptyHint="PubMed search and fetch will stream here."
          />
        </StepCard>
      )}

      {result && (
        <StepCard
          title="Literature Summary"
          status="done"
          badge={`${result.articles.length} papers`}
        >
          <div className="space-y-4">
            <div className="rounded-lg bg-teal-50/50 border border-teal-100 p-3">
              <p className="text-xs font-semibold text-teal-700 mb-1.5 uppercase tracking-wide">
                Synthesis
              </p>
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                {result.summary}
              </p>
            </div>

            <div className="space-y-2.5">
              {result.articles.map((a) => (
                <div
                  key={a.pmid}
                  className="rounded-lg border border-slate-100 bg-white p-3 space-y-1.5"
                >
                  <div className="flex items-baseline gap-2">
                    <a
                      href={a.url || `https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-semibold text-slate-800 hover:text-teal-700 hover:underline"
                    >
                      {a.title}
                    </a>
                  </div>
                  <p className="text-xs text-slate-500">
                    {(a.authors || []).slice(0, 4).join(", ")}
                    {a.authors && a.authors.length > 4 ? ", et al." : ""}
                    {a.journal ? ` · ${a.journal}` : ""}
                    {a.year ? ` · ${a.year}` : ""}
                  </p>
                  {a.relevance && (
                    <p className="text-xs text-teal-700 italic">{a.relevance}</p>
                  )}
                  {a.abstract && (
                    <details className="text-xs text-slate-500">
                      <summary className="cursor-pointer text-slate-400 hover:text-slate-600">
                        Abstract
                      </summary>
                      <p className="mt-1.5 leading-relaxed whitespace-pre-line">
                        {a.abstract}
                      </p>
                    </details>
                  )}
                  <div className="text-[11px] text-slate-400">
                    PMID {a.pmid}
                    {a.doi ? (
                      <>
                        {" "}·{" "}
                        <a
                          className="hover:text-sky-600 hover:underline"
                          href={`https://doi.org/${a.doi}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          DOI {a.doi}
                        </a>
                      </>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </StepCard>
      )}
    </div>
  );
}
