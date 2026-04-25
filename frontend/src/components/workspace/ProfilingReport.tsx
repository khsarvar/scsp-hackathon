"use client";

import { Fragment, useState } from "react";
import clsx from "clsx";
import type { ProfileResponse, ColumnProfile } from "@/types";

interface ProfilingReportProps {
  profile: ProfileResponse;
}

function Badge({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className={`px-3 py-2 rounded-lg ${color}`}>
      <p className="text-lg font-bold">{value}</p>
      <p className="text-xs mt-0.5 opacity-70">{label}</p>
    </div>
  );
}

function RoleChip({ role }: { role: ColumnProfile["dtype_inferred"] }) {
  const styles = {
    datetime: "bg-sky-100 text-sky-700",
    numeric: "bg-teal-100 text-teal-700",
    categorical: "bg-violet-100 text-violet-700",
    id: "bg-slate-100 text-slate-500",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[role]}`}>
      {role}
    </span>
  );
}

export default function ProfilingReport({ profile }: ProfilingReportProps) {
  const [expandedCol, setExpandedCol] = useState<string | null>(null);
  const totalMissing = profile.columns.reduce((s, c) => s + c.missing_count, 0);
  const outlierCols = profile.columns.filter((c) => c.outliers.length > 0);

  return (
    <div className="space-y-4">
      {/* Summary badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Badge label="Rows" value={profile.row_count.toLocaleString()} color="bg-teal-50 text-teal-800" />
        <Badge label="Columns" value={profile.col_count} color="bg-sky-50 text-sky-800" />
        <Badge label="Missing cells" value={totalMissing} color={totalMissing > 0 ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-slate-700"} />
        <Badge label="Duplicate rows" value={profile.duplicate_rows} color={profile.duplicate_rows > 0 ? "bg-rose-50 text-rose-800" : "bg-slate-50 text-slate-700"} />
      </div>

      {/* Column table */}
      <div className="overflow-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-3 py-2 text-left font-semibold text-slate-600">Column</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-600">Type</th>
              <th className="px-3 py-2 text-right font-semibold text-slate-600">Missing</th>
              <th className="px-3 py-2 text-right font-semibold text-slate-600">Unique</th>
              <th className="px-3 py-2 text-right font-semibold text-slate-600">Min / Max</th>
              <th className="px-3 py-2 text-center font-semibold text-slate-600">Outliers</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {profile.columns.map((col) => (
              <Fragment key={col.name}>
                <tr
                  className={clsx(
                    "hover:bg-slate-50 cursor-pointer transition-colors",
                    expandedCol === col.name && "bg-slate-50"
                  )}
                  onClick={() => setExpandedCol(expandedCol === col.name ? null : col.name)}
                >
                  <td className="px-3 py-2 font-medium text-slate-700">{col.name}</td>
                  <td className="px-3 py-2"><RoleChip role={col.dtype_inferred} /></td>
                  <td className="px-3 py-2 text-right">
                    <span className={col.missing_pct > 0 ? "text-amber-600 font-medium" : "text-slate-400"}>
                      {col.missing_pct > 0 ? `${col.missing_pct}%` : "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-slate-500">{col.unique_count}</td>
                  <td className="px-3 py-2 text-right text-slate-500 font-mono">
                    {col.min != null ? `${col.min} / ${col.max}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {col.outliers.length > 0 ? (
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-rose-100 text-rose-600 text-xs font-bold">
                        {col.outliers.length}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
                {expandedCol === col.name && col.outliers.length > 0 && (
                  <tr className="bg-rose-50">
                    <td colSpan={6} className="px-4 py-2">
                      <p className="text-xs font-medium text-rose-700 mb-1">Outliers detected (IQR ×3):</p>
                      <div className="flex flex-wrap gap-2">
                        {col.outliers.map((o) => (
                          <span key={o.row_index} className="text-xs bg-white border border-rose-200 text-rose-600 px-2 py-0.5 rounded">
                            row {o.row_index}: {o.value}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {outlierCols.length > 0 && (
        <p className="text-xs text-slate-400 italic">
          Click on a row to expand outlier details.
        </p>
      )}
    </div>
  );
}
