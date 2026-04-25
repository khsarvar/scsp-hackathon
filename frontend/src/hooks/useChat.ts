"use client";

import { useState, useCallback } from "react";
import type { ChatMessage } from "@/types";
import { sendChatMessage } from "@/lib/api";

export function useChat(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId || isStreaming) return;
      setError(null);

      const userMessage: ChatMessage = { role: "user", content: text };
      const updatedMessages = [...messages, userMessage];
      setMessages(updatedMessages);

      const assistantMessage: ChatMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMessage]);
      setIsStreaming(true);

      try {
        const res = await sendChatMessage(sessionId, text, messages);
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let done = false;
        let buffer = "";

        while (!done) {
          const { value, done: streamDone } = await reader.read();
          done = streamDone;
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6).trim();
                if (data === "[DONE]") {
                  done = true;
                  break;
                }
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.delta) {
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last?.role === "assistant") {
                        updated[updated.length - 1] = {
                          ...last,
                          content: last.content + parsed.delta,
                        };
                      }
                      return updated;
                    });
                  }
                } catch {}
              }
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Chat error");
        // Remove the empty assistant message
        setMessages((prev) => prev.filter((_, i) => !(i === prev.length - 1 && prev[prev.length - 1].content === "")));
      } finally {
        setIsStreaming(false);
      }
    },
    [sessionId, messages, isStreaming]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isStreaming, error, sendMessage, clearMessages };
}
