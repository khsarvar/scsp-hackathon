"use client";

import { useEffect, useState } from "react";
import LeftSidebar from "./LeftSidebar";
import AppHeader from "./AppHeader";
import ChatSheet from "./ChatSheet";
import WorkspaceArea from "@/components/workspace/WorkspaceArea";
import { useSession } from "@/hooks/useSession";
import { useChat } from "@/hooks/useChat";

export default function AppShell() {
  const { state } = useSession();
  const [chatOpen, setChatOpen] = useState(false);
  const [seenCount, setSeenCount] = useState(0);
  const chat = useChat(state.sessionId);

  // Track unread assistant replies while sheet is closed
  const messageCount = chat.messages.length;
  useEffect(() => {
    if (chatOpen) setSeenCount(messageCount);
  }, [chatOpen, messageCount]);
  const unreadCount = Math.max(0, messageCount - seenCount);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Left Sidebar */}
      <aside className="w-72 flex-shrink-0 border-r border-slate-200 bg-white flex flex-col overflow-hidden">
        <LeftSidebar />
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <AppHeader
          onChatToggle={() => setChatOpen((o) => !o)}
          chatOpen={chatOpen}
          chatActive={!!state.sessionId}
          chatStreaming={chat.isStreaming}
          unreadCount={unreadCount}
        />
        <main className="flex-1 overflow-hidden flex flex-col">
          <WorkspaceArea />
        </main>
      </div>

      {/* Slide-over chat */}
      <ChatSheet
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        sessionId={state.sessionId}
        chat={chat}
      />
    </div>
  );
}
