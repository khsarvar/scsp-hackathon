"use client";

import { useState, useRef, useCallback } from "react";
import clsx from "clsx";

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  disabled: boolean;
}

export default function ChatInput({ onSend, isStreaming, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, isStreaming, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
    }
  };

  return (
    <div className="flex items-end gap-2 p-3 border-t border-slate-100">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "Upload a dataset to chat..." : "Ask the AI agent..."}
        disabled={disabled || isStreaming}
        rows={1}
        className={clsx(
          "flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-xs",
          "placeholder:text-slate-300 focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-400/20",
          "transition-all max-h-24",
          (disabled || isStreaming) && "opacity-50 cursor-not-allowed"
        )}
      />
      <button
        onClick={handleSend}
        disabled={disabled || isStreaming || !value.trim()}
        className={clsx(
          "flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all",
          !disabled && !isStreaming && value.trim()
            ? "bg-teal-500 hover:bg-teal-600 text-white shadow-sm"
            : "bg-slate-100 text-slate-300 cursor-not-allowed"
        )}
      >
        {isStreaming ? (
          <div className="w-3 h-3 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        )}
      </button>
    </div>
  );
}
