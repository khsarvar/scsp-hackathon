"use client";

interface DataPreviewProps {
  rows: Record<string, unknown>[];
  columns: string[];
  totalRows: number;
}

export default function DataPreview({ rows, columns, totalRows }: DataPreviewProps) {
  return (
    <div>
      <div className="overflow-auto max-h-72 rounded-lg border border-slate-200">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left font-semibold text-slate-600 whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50 transition-colors">
                {columns.map((col) => {
                  const val = row[col];
                  const isNull = val === null || val === undefined || val === "";
                  return (
                    <td
                      key={col}
                      className={`px-3 py-1.5 whitespace-nowrap ${
                        isNull ? "text-slate-300 italic" : "text-slate-700"
                      }`}
                    >
                      {isNull ? "null" : String(val)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Showing {rows.length} of {totalRows.toLocaleString()} rows
      </p>
    </div>
  );
}
