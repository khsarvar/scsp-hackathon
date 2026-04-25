"use client";

interface CleaningSummaryProps {
  steps: string[];
}

export default function CleaningSummary({ steps }: CleaningSummaryProps) {
  return (
    <ul className="space-y-2">
      {steps.map((step, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm text-slate-600">
          <span className="mt-0.5 w-4 h-4 flex-shrink-0 rounded-full bg-teal-100 flex items-center justify-center">
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </span>
          {step}
        </li>
      ))}
    </ul>
  );
}
