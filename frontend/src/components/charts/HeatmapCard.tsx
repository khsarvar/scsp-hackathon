"use client";

interface HeatmapRow {
  row: string;
  col: string;
  value: number;
}

interface HeatmapCardProps {
  title: string;
  data: Record<string, unknown>[];
}

function cellColor(value: number): string {
  const hue = value > 0 ? 174 : 0;
  const saturation = Math.abs(value) * 70;
  const lightness = 90 - Math.abs(value) * 40;
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}

export default function HeatmapCard({ title, data }: HeatmapCardProps) {
  const rows = data as unknown as HeatmapRow[];
  if (rows.length === 0) return null;

  const rowLabels = Array.from(new Set(rows.map((r) => r.row)));
  const colLabels = Array.from(new Set(rows.map((r) => r.col)));

  const lookup = new Map<string, number>();
  rows.forEach((r) => lookup.set(`${r.row}||${r.col}`, r.value ?? 0));

  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-slate-700 mb-3">{title}</h4>
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="w-24" />
              {colLabels.map((col) => (
                <th
                  key={col}
                  className="px-1 py-1 text-slate-500 font-normal text-center"
                  style={{ maxWidth: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={col}
                >
                  {col.length > 8 ? col.slice(0, 8) + "…" : col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowLabels.map((rowLabel) => (
              <tr key={rowLabel}>
                <td
                  className="pr-2 text-slate-500 text-right"
                  style={{ maxWidth: 80, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={rowLabel}
                >
                  {rowLabel.length > 10 ? rowLabel.slice(0, 10) + "…" : rowLabel}
                </td>
                {colLabels.map((colLabel) => {
                  const val = lookup.get(`${rowLabel}||${colLabel}`) ?? 0;
                  const isBold = Math.abs(val) > 0.7;
                  return (
                    <td
                      key={colLabel}
                      className="w-12 h-10 text-center"
                      style={{ backgroundColor: cellColor(val) }}
                    >
                      <span
                        className="text-slate-800"
                        style={{ fontWeight: isBold ? 700 : 400 }}
                      >
                        {val.toFixed(2)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
