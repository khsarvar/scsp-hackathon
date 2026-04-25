"use client";

import ChatPanel from "@/components/chat/ChatPanel";

interface RightPanelProps {
  sessionId: string | null;
}

export default function RightPanel({ sessionId }: RightPanelProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2 flex-shrink-0">
        <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
        <h2 className="text-sm font-semibold text-slate-700">AI Agent</h2>
        {sessionId && (
          <span className="ml-auto text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            Active
          </span>
        )}
      </div>

      <div className="flex-1 overflow-hidden">
        <ChatPanel sessionId={sessionId} />
      </div>
    </div>
  );
}
