"use client";

import { useState } from "react";
import clsx from "clsx";
import type { DatasetRecommendation } from "@/types";

interface Props {
  recommendations: DatasetRecommendation[];
  question: string;
  onConfirm: (selectedIds: string[]) => void;
  onSkip: () => void;
  isLoading: boolean;
}

function RecommendationCard({
  rec,
  selected,
  onToggle,
}: {
  rec: DatasetRecommendation;
  selected: boolean;
  onToggle: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visibleCols = expanded ? rec.columns : rec.columns.slice(0, 6);

  return (
    <button
      type="button"
      onClick={onToggle}
      className={clsx(
        "w-full text-left rounded-xl border p-4 transition-all duration-150 space-y-3",
        selected
          ? "border-teal-400 bg-teal-50/50 ring-1 ring-teal-300"
          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
      )}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        {/* Checkbox */}
        <div
          className={clsx(
            "mt-0.5 flex-shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center",
            selected ? "border-teal-500 bg-teal-500" : "border-slate-300"
          )}
        >
          {selected && (
            <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 12 12">
              <path d="M10 3L5 8.5 2 5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
            </svg>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <span className="font-semibold text-sm text-slate-800 leading-tight">{rec.name}</span>
            {rec.row_count != null && (
              <span className="text-xs text-slate-400 whitespace-nowrap shrink-0">
                ~{rec.row_count.toLocaleString()} rows
              </span>
            )}
          </div>

          {/* Categories */}
          {rec.categories.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {rec.categories.slice(0, 3).map((cat) => (
                <span
                  key={cat}
                  className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full"
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Description */}
      {rec.description && (
        <p className="text-xs text-slate-600 leading-relaxed line-clamp-3 pl-7">
          {rec.description}
        </p>
      )}

      {/* Columns */}
      {rec.columns.length > 0 && (
        <div className="pl-7 space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">
            {rec.columns.length} columns
          </p>
          <div className="flex flex-wrap gap-1">
            {visibleCols.map((col) => (
              <span
                key={col.field}
                title={`${col.name} (${col.type})`}
                className={clsx(
                  "text-[10px] font-mono px-1.5 py-0.5 rounded",
                  col.type === "number" || col.type === "double"
                    ? "bg-amber-50 text-amber-700"
                    : col.type === "calendar_date" || col.type === "date"
                    ? "bg-purple-50 text-purple-700"
                    : "bg-slate-100 text-slate-600"
                )}
              >
                {col.name || col.field}
              </span>
            ))}
            {rec.columns.length > 6 && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded((v) => !v);
                }}
                className="text-[10px] text-teal-600 hover:text-teal-700 px-1"
              >
                {expanded ? "show less" : `+${rec.columns.length - 6} more`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* CDC link */}
      <div className="pl-7">
        <a
          href={`https://data.cdc.gov/d/${rec.id}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-[10px] text-slate-400 hover:text-teal-600 font-mono"
        >
          data.cdc.gov/d/{rec.id}
        </a>
      </div>
    </button>
  );
}

export default function DatasetPicker({ recommendations, question, onConfirm, onSkip, isLoading }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirm = () => {
    onConfirm(Array.from(selected));
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-xl border border-blue-200 bg-blue-50/40 px-4 py-3">
        <p className="text-xs font-semibold text-blue-700 mb-0.5">CDC Catalog Results</p>
        <p className="text-xs text-slate-600">
          Found {recommendations.length} datasets for: <span className="italic">{question}</span>
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Select one or more to fetch, or let the agent choose automatically.
        </p>
      </div>

      {/* Dataset cards */}
      <div className="space-y-2">
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.id}
            rec={rec}
            selected={selected.has(rec.id)}
            onToggle={() => toggle(rec.id)}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={handleConfirm}
          disabled={selected.size === 0 || isLoading}
          className={clsx(
            "flex-1 text-sm font-medium py-2.5 px-4 rounded-lg transition-colors",
            selected.size > 0 && !isLoading
              ? "bg-teal-500 hover:bg-teal-600 text-white"
              : "bg-slate-100 text-slate-400 cursor-not-allowed"
          )}
        >
          {isLoading
            ? "Starting discovery..."
            : selected.size > 0
            ? `Fetch ${selected.size} dataset${selected.size > 1 ? "s" : ""} \u2192`
            : "Select a dataset"}
        </button>
        <button
          onClick={onSkip}
          disabled={isLoading}
          className="text-xs text-slate-500 hover:text-slate-700 transition-colors whitespace-nowrap"
        >
          Let agent decide
        </button>
      </div>
    </div>
  );
}
