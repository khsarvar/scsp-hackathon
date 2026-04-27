"use client";

import Sheet from "@/components/ui/Sheet";
import ChatPanel from "@/components/chat/ChatPanel";
import type { useChat } from "@/hooks/useChat";

interface ChatSheetProps {
  open: boolean;
  onClose: () => void;
  sessionId: string | null;
  chat: ReturnType<typeof useChat>;
}

export default function ChatSheet({ open, onClose, sessionId, chat }: ChatSheetProps) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
          <span>AI Agent</span>
          {sessionId && (
            <span className="ml-1 text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
              Active
            </span>
          )}
        </div>
      }
    >
      <ChatPanel sessionId={sessionId} chat={chat} />
    </Sheet>
  );
}
