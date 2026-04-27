"use client";

import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import type { ChatMessage as ChatMessageType } from "@/types";

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

export default function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={clsx("flex gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div
        className={clsx(
          "w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5",
          isUser
            ? "bg-sky-100 text-sky-600"
            : "bg-teal-500 text-white"
        )}
      >
        {isUser ? "U" : "AI"}
      </div>

      {/* Bubble */}
      <div
        className={clsx(
          "max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed",
          isUser
            ? "bg-sky-50 border border-sky-100 text-slate-700"
            : "bg-white border border-slate-100 text-slate-700 shadow-sm"
        )}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="prose-healthlab">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {isStreaming && <span className="cursor-blink" />}
          </div>
        )}
      </div>
    </div>
  );
}
