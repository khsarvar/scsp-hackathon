"use client";

import ReactMarkdown from "react-markdown";

interface FollowUpListProps {
  followUp: string;
}

export default function FollowUpList({ followUp }: FollowUpListProps) {
  return (
    <div className="bg-violet-50 rounded-xl p-4 border border-violet-100">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-full bg-violet-500 flex items-center justify-center flex-shrink-0">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
          </svg>
        </div>
        <h4 className="text-sm font-semibold text-violet-800">Suggested Follow-Up Research</h4>
      </div>
      <div className="prose-healthlab">
        <ReactMarkdown>{followUp}</ReactMarkdown>
      </div>
    </div>
  );
}
