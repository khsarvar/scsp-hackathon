"use client";

import type { StatRow } from "@/types";

interface StatsPanelProps {
  stats: StatRow[];
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export default function StatsPanel({ stats }: StatsPanelProps) {
  if (stats.length === 0) {
    return <p className="text-sm text-slate-400 italic">No numeric columns found.</p>;
  }

  return (
    <div className="overflow-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="px-3 py-2 text-left font-semibold text-slate-600">Column</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Count</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Mean</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Median</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Std</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Min</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">Max</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">P25</th>
            <th className="px-3 py-2 text-right font-semibold text-slate-600">P75</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {stats.map((row) => (
            <tr key={row.column} className="hover:bg-slate-50 transition-colors">
              <td className="px-3 py-2 font-medium text-slate-700">{row.column}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{row.count}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{fmt(row.mean)}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{fmt(row.median)}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{fmt(row.std)}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{fmt(row.min)}</td>
              <td className="px-3 py-2 text-right text-slate-600 font-mono">{fmt(row.max)}</td>
              <td className="px-3 py-2 text-right text-slate-500 font-mono">{fmt(row.p25)}</td>
              <td className="px-3 py-2 text-right text-slate-500 font-mono">{fmt(row.p75)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
