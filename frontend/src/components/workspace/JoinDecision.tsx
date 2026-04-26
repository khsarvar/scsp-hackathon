"use client";

import { useState } from "react";
import clsx from "clsx";
import { useSession } from "@/hooks/useSession";
import { selectFrame, profileDataset } from "@/lib/api";
import type { DiscoverCandidate, UploadResponse } from "@/types";

function CandidateCard({
  candidate,
  isSuggested,
  onSelect,
  isLoading,
}: {
  candidate: DiscoverCandidate;
  isSuggested: boolean;
  onSelect: () => void;
  isLoading: boolean;
}) {
  return (
    <div
      className={clsx(
        "rounded-xl border p-4 flex flex-col gap-3 transition-colors",
        isSuggested
          ? "border-teal-400 bg-teal-50/40"
          : "border-slate-200 bg-white hover:border-slate-300"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-semibold text-slate-800">
            {candidate.alias}
          </span>
          {isSuggested && (
            <span className="text-xs bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full font-medium">
              agent suggestion
            </span>
          )}
          {candidate.is_derived && (
            <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-medium">
              joined
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500 whitespace-nowrap shrink-0">
          {candidate.rows.toLocaleString()} rows &times; {candidate.cols} cols
        </span>
      </div>

      {candidate.is_derived && candidate.parents.length > 0 && (
        <p className="text-xs text-slate-500">
          Joined from:{" "}
          {candidate.parents.map((p, i) => (
            <span key={p}>
              <span className="font-mono">{p}</span>
              {i < candidate.parents.length - 1 ? " + " : ""}
            </span>
          ))}
        </p>
      )}

      {!candidate.is_derived && candidate.source_title && candidate.source_title !== candidate.alias && (
        <p className="text-xs text-slate-500 truncate" title={candidate.source_title}>
          CDC ID: {candidate.source_title}
        </p>
      )}

      <div className="flex flex-wrap gap-2 text-xs text-slate-400">
        {candidate.columns.slice(0, 5).map((col) => (
          <span key={col} className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">
            {col}
          </span>
        ))}
        {candidate.columns.length > 5 && (
          <span className="text-slate-400">+{candidate.columns.length - 5} more</span>
        )}
      </div>

      <button
        onClick={onSelect}
        disabled={isLoading}
        className={clsx(
          "mt-1 w-full text-sm font-medium py-2 px-4 rounded-lg transition-colors",
          isSuggested
            ? "bg-teal-500 hover:bg-teal-600 text-white disabled:opacity-50"
            : "bg-slate-100 hover:bg-slate-200 text-slate-700 disabled:opacity-50"
        )}
      >
        {isLoading ? "Loading..." : "Use this dataset \u2192"}
      </button>
    </div>
  );
}

export default function JoinDecision() {
  const { state, dispatch } = useSession();
  const { discoverCandidates, discoverSuggestedAlias, sessionId } = state;
  const [loadingAlias, setLoadingAlias] = useState<string | null>(null);

  const profileAfterSelect = async (upload: UploadResponse) => {
    dispatch({ type: "CLEAR_JOIN_CANDIDATES" });
    dispatch({ type: "SET_UPLOAD", payload: upload });
    dispatch({ type: "SET_STEP", step: "profiling" });
    try {
      const profile = await profileDataset(upload.session_id);
      dispatch({ type: "SET_PROFILE", payload: profile });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    }
  };

  const handleSelect = async (alias: string) => {
    if (!sessionId || loadingAlias) return;
    setLoadingAlias(alias);
    try {
      const upload = await selectFrame(sessionId, alias);
      if (!upload.session_id) throw new Error("Invalid response from server");
      await profileAfterSelect(upload);
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: (err as Error).message });
    } finally {
      setLoadingAlias(null);
    }
  };

  if (!discoverCandidates || discoverCandidates.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-5 space-y-4">
      <div>
        <h3 className="font-semibold text-slate-800 text-sm">Choose your dataset</h3>
        <p className="text-xs text-slate-500 mt-1">
          The agent fetched {discoverCandidates.length} datasets. Pick one to profile and analyze.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {discoverCandidates.map((c: DiscoverCandidate) => (
          <CandidateCard
            key={c.alias}
            candidate={c}
            isSuggested={c.alias === discoverSuggestedAlias}
            onSelect={() => handleSelect(c.alias)}
            isLoading={loadingAlias === c.alias}
          />
        ))}
      </div>
    </div>
  );
}
