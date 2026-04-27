"use client";

import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import { useChat } from "@/hooks/useChat";

interface ChatPanelProps {
  sessionId: string | null;
  /** Optional pre-instantiated chat state. If omitted, the panel owns its own. */
  chat?: ReturnType<typeof useChat>;
}

const QUICK_PROMPTS = [
  "What trends do you see?",
  "Show missing data issues",
  "Which groups have highest rates?",
  "Can we make causal claims?",
  "Suggest follow-up experiments",
];

export default function ChatPanel({ sessionId, chat }: ChatPanelProps) {
  const owned = useChat(chat ? null : sessionId);
  const { messages, isStreaming, error, sendMessage } = chat ?? owned;
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const disabled = !sessionId;

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 px-2">
            {disabled ? (
              <div className="text-center">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-2">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                </div>
                <p className="text-xs text-slate-400 text-center">Upload a dataset to start chatting with the AI agent</p>
              </div>
            ) : (
              <div className="w-full space-y-2">
                <p className="text-xs text-slate-400 text-center mb-3">Try asking...</p>
                {QUICK_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => sendMessage(p)}
                    className="w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-100 hover:border-teal-200 hover:bg-teal-50 text-slate-600 transition-all"
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <ChatMessage
                key={i}
                message={msg}
                isStreaming={isStreaming && i === messages.length - 1 && msg.role === "assistant"}
              />
            ))}
            {error && (
              <p className="text-xs text-red-400 text-center px-2">{error}</p>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput
        onSend={sendMessage}
        isStreaming={isStreaming}
        disabled={disabled}
      />
    </div>
  );
}
