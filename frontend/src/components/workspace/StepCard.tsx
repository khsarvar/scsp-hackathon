"use client";

import { useState, useEffect } from "react";
import clsx from "clsx";

interface StepCardProps {
  title: string;
  stepNumber?: number;
  status: "pending" | "loading" | "done" | "error";
  collapsible?: boolean;
  defaultOpen?: boolean;
  children: React.ReactNode;
  badge?: string;
}

export default function StepCard({
  title,
  stepNumber,
  status,
  collapsible = false,
  defaultOpen = true,
  children,
  badge,
}: StepCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  // Auto-open when a parent signals the card should become visible
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  return (
    <div
      className={clsx(
        "bg-white rounded-xl border shadow-sm animate-fade-in overflow-hidden",
        status === "loading" && "border-teal-200",
        status === "done" && "border-slate-100",
        status === "error" && "border-red-200",
        status === "pending" && "border-slate-100 opacity-50"
      )}
    >
      {/* Header */}
      <div
        className={clsx(
          "flex items-center gap-3 px-5 py-3.5",
          status === "loading" && "border-l-4 border-teal-500 bg-teal-50/30",
          status === "done" && "border-l-4 border-teal-400",
          status === "error" && "border-l-4 border-red-400",
          collapsible && "cursor-pointer hover:bg-slate-50 transition-colors"
        )}
        onClick={() => collapsible && setOpen(!open)}
      >
        {/* Step indicator */}
        <div className={clsx(
          "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
          status === "loading" && "bg-teal-100 text-teal-600",
          status === "done" && "bg-teal-500 text-white",
          status === "error" && "bg-red-100 text-red-600",
          status === "pending" && "bg-slate-100 text-slate-400"
        )}>
          {status === "loading" ? (
            <div className="w-3 h-3 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
          ) : status === "done" ? (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          ) : status === "error" ? (
            "!"
          ) : (
            stepNumber || "·"
          )}
        </div>

        <h3 className="text-sm font-semibold text-slate-700 flex-1">{title}</h3>

        {badge && (
          <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">{badge}</span>
        )}

        {collapsible && (
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#94a3b8"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={clsx("transition-transform", open ? "rotate-180" : "")}
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        )}
      </div>

      {/* Body */}
      {(!collapsible || open) && (
        <div className="px-5 pb-5 pt-1">{children}</div>
      )}
    </div>
  );
}
