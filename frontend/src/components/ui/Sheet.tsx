"use client";

import { useEffect } from "react";
import clsx from "clsx";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  side?: "right" | "left";
  width?: string;
  title?: React.ReactNode;
  children: React.ReactNode;
}

export default function Sheet({
  open,
  onClose,
  side = "right",
  width = "w-[420px]",
  title,
  children,
}: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div
      aria-hidden={!open}
      className={clsx(
        "fixed inset-0 z-40 transition-opacity",
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />

      {/* Panel */}
      <aside
        role="dialog"
        aria-modal="true"
        className={clsx(
          "absolute top-0 h-full bg-white shadow-2xl flex flex-col",
          width,
          side === "right" ? "right-0" : "left-0",
          "transition-transform duration-200 ease-out",
          open
            ? "translate-x-0"
            : side === "right"
              ? "translate-x-full"
              : "-translate-x-full",
        )}
      >
        {(title || true) && (
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2 flex-shrink-0">
            <div className="text-sm font-semibold text-slate-700 flex-1">{title}</div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-slate-400 hover:text-slate-700 rounded p-1 -m-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6L6 18" />
                <path d="M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        <div className="flex-1 overflow-hidden">{children}</div>
      </aside>
    </div>
  );
}
