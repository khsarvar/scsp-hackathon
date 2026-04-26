"use client";

import { DataProvenance } from "@/types";

interface DataPreviewProps {
  rows: Record<string, unknown>[];
  columns: string[];
  totalRows: number;
  provenance?: DataProvenance | null;
}

function ProvenanceBanner({ provenance }: { provenance: DataProvenance }) {
  const isUpload = provenance.type === "upload";
  const isCDC = provenance.type === "cdc_discover";

  // Primary sources: Socrata-fetched frames (have cdc_id)
  const fetchedSources = provenance.sources.filter((s) => s.cdc_id);
  // Derived frames: merges, aggregates, etc.
  const derivedSources = provenance.sources.filter(
    (s) => !s.cdc_id && s.alias !== "main"
  );
  const primaryAlias = provenance.primary_alias;

  return (
    <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-600 space-y-1.5">
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            isUpload
              ? "bg-sky-100 text-sky-700"
              : "bg-teal-100 text-teal-700"
          }`}
        >
          {isUpload ? "CSV Upload" : "CDC Discovery"}
        </span>
        {isCDC && provenance.research_question && (
          <span className="text-slate-500 italic truncate max-w-xs">
            &ldquo;{provenance.research_question}&rdquo;
          </span>
        )}
        {isUpload && provenance.filename && (
          <span className="text-slate-500 font-mono">{provenance.filename}</span>
        )}
      </div>

      {/* CDC source list */}
      {isCDC && fetchedSources.length > 0 && (
        <div className="space-y-1">
          <p className="font-medium text-slate-500 uppercase tracking-wide text-[10px]">
            Source datasets
          </p>
          {fetchedSources.map((src) => (
            <div key={src.alias} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 pl-2">
              <span
                className={`font-mono font-semibold ${
                  src.alias === primaryAlias ? "text-teal-700" : "text-slate-600"
                }`}
              >
                {src.alias}
                {src.alias === primaryAlias && (
                  <span className="ml-1 text-[9px] font-normal text-teal-600">(primary)</span>
                )}
              </span>
              {src.cdc_url ? (
                <a
                  href={src.cdc_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sky-600 hover:underline font-mono text-[10px]"
                >
                  data.cdc.gov/{src.cdc_id}
                </a>
              ) : null}
              {src.soql_filter && (
                <span className="text-slate-400">
                  where <code className="text-slate-500 bg-slate-100 rounded px-1">{src.soql_filter}</code>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Derived / joined frames */}
      {isCDC && derivedSources.length > 0 && (
        <div className="space-y-0.5">
          <p className="font-medium text-slate-500 uppercase tracking-wide text-[10px]">
            Transformations
          </p>
          {derivedSources.map((src) => (
            <div key={src.alias} className="pl-2 flex items-baseline gap-2">
              <span
                className={`font-mono font-semibold ${
                  src.alias === primaryAlias ? "text-teal-700" : "text-slate-600"
                }`}
              >
                {src.alias}
                {src.alias === primaryAlias && (
                  <span className="ml-1 text-[9px] font-normal text-teal-600">(primary)</span>
                )}
              </span>
              <span className="text-slate-400 font-mono text-[10px]">{src.source_str}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DataPreview({ rows, columns, totalRows, provenance }: DataPreviewProps) {
  return (
    <div>
      {provenance && <ProvenanceBanner provenance={provenance} />}
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
