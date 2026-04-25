"use client";

import ReactMarkdown from "react-markdown";

interface FindingsTextProps {
  findings: string;
}

export default function FindingsText({ findings }: FindingsTextProps) {
  return (
    <div className="bg-gradient-to-br from-teal-50 to-sky-50 rounded-xl p-5 border border-teal-100">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-full bg-teal-500 flex items-center justify-center flex-shrink-0">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </div>
        <h4 className="text-sm font-semibold text-teal-800">Key Findings</h4>
      </div>
      <div className="prose-healthlab">
        <ReactMarkdown>{findings}</ReactMarkdown>
      </div>
    </div>
  );
}
