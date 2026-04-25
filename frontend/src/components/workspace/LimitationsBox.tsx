"use client";

import ReactMarkdown from "react-markdown";

interface LimitationsBoxProps {
  limitations: string;
}

export default function LimitationsBox({ limitations }: LimitationsBoxProps) {
  return (
    <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-full bg-amber-400 flex items-center justify-center flex-shrink-0">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <h4 className="text-sm font-semibold text-amber-800">Limitations</h4>
      </div>
      <div className="prose-healthlab">
        <ReactMarkdown>{limitations}</ReactMarkdown>
      </div>
    </div>
  );
}
