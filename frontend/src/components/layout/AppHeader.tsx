"use client";

import clsx from "clsx";

interface AppHeaderProps {
  onChatToggle: () => void;
  chatOpen: boolean;
  chatActive: boolean;
  chatStreaming: boolean;
  unreadCount?: number;
}

export default function AppHeader({
  onChatToggle,
  chatOpen,
  chatActive,
  chatStreaming,
  unreadCount = 0,
}: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-2.5 bg-white border-b border-slate-200 flex-shrink-0">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span className="font-mono">workspace</span>
      </div>

      <button
        type="button"
        onClick={onChatToggle}
        disabled={!chatActive}
        className={clsx(
          "relative inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
          chatActive
            ? chatOpen
              ? "bg-teal-50 border-teal-200 text-teal-700"
              : "bg-white border-slate-200 text-slate-600 hover:border-teal-300 hover:text-teal-700"
            : "bg-slate-50 border-slate-100 text-slate-300 cursor-not-allowed",
        )}
        title={chatActive ? "Toggle AI agent chat" : "Load a dataset to enable chat"}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        Chat
        {chatStreaming && (
          <span className="inline-flex w-2 h-2 rounded-full bg-emerald-400 animate-pulse" aria-label="agent streaming" />
        )}
        {!chatOpen && unreadCount > 0 && (
          <span className="ml-0.5 inline-flex items-center justify-center text-[10px] font-bold bg-teal-500 text-white rounded-full min-w-[16px] h-4 px-1">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
    </header>
  );
}
