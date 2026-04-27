"use client";

import { useState, useRef, useCallback } from "react";
import clsx from "clsx";
import { uploadCSV } from "@/lib/api";
import type { UploadResponse } from "@/types";

interface DropZoneProps {
  onUploadComplete: (result: UploadResponse) => void;
  isLoading: boolean;
}

export default function DropZone({ onUploadComplete, isLoading }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".csv")) {
        setError("Only CSV files are supported.");
        return;
      }
      setError(null);
      try {
        const result = await uploadCSV(file);
        onUploadComplete(result);
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [onUploadComplete]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => !isLoading && inputRef.current?.click()}
        className={clsx(
          "relative border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all",
          isDragging
            ? "border-teal-400 bg-teal-50"
            : "border-slate-200 hover:border-teal-300 hover:bg-slate-50",
          isLoading && "pointer-events-none opacity-60"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={onInputChange}
        />
        {isLoading ? (
          <div className="flex flex-col items-center gap-2 py-2">
            <div className="w-6 h-6 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-slate-500">Processing...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1.5 py-1">
            <div className="w-8 h-8 rounded-lg bg-teal-100 flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <p className="text-xs font-medium text-slate-600">Drop CSV here</p>
            <p className="text-xs text-slate-400">or click to browse</p>
          </div>
        )}
      </div>
      {error && (
        <p className="mt-1.5 text-xs text-red-500 px-1">{error}</p>
      )}
    </div>
  );
}
