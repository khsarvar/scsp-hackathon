"use client";

interface BoxRow {
  group: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
}

interface BoxPlotCardProps {
  title: string;
  data: Record<string, unknown>[];
}

const CHART_HEIGHT = 280;
const PADDING_TOP = 16;
const PADDING_BOTTOM = 24;
const PLOT_HEIGHT = CHART_HEIGHT - PADDING_TOP - PADDING_BOTTOM;

export default function BoxPlotCard({ title, data }: BoxPlotCardProps) {
  const rows = data as unknown as BoxRow[];
  if (rows.length === 0) return null;

  const allValues = rows.flatMap((r) => [r.min, r.max]).filter((v) => v != null);
  const globalMin = Math.min(...allValues);
  const globalMax = Math.max(...allValues);
  const range = globalMax - globalMin || 1;

  const toY = (val: number) =>
    PADDING_TOP + PLOT_HEIGHT - ((val - globalMin) / range) * PLOT_HEIGHT;

  const boxWidth = 24;
  const groupWidth = Math.max(60, 600 / rows.length);
  const totalWidth = groupWidth * rows.length;

  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-slate-700 mb-2">{title}</h4>
      <div className="overflow-x-auto">
        <svg width={totalWidth} height={CHART_HEIGHT} className="min-w-full">
          {rows.map((row, i) => {
            const cx = groupWidth * i + groupWidth / 2;
            const yMin = toY(row.min);
            const yQ1 = toY(row.q1);
            const yMedian = toY(row.median);
            const yQ3 = toY(row.q3);
            const yMax = toY(row.max);

            return (
              <g key={i}>
                {/* whisker: min → q1 */}
                <line x1={cx} y1={yMin} x2={cx} y2={yQ1} stroke="#94a3b8" strokeWidth={1.5} />
                {/* whisker cap at min */}
                <line x1={cx - 6} y1={yMin} x2={cx + 6} y2={yMin} stroke="#94a3b8" strokeWidth={1.5} />
                {/* IQR box */}
                <rect
                  x={cx - boxWidth / 2}
                  y={yQ3}
                  width={boxWidth}
                  height={yQ1 - yQ3}
                  fill="#ccfbf1"
                  stroke="#14b8a6"
                  strokeWidth={1.5}
                  rx={2}
                />
                {/* median line */}
                <line
                  x1={cx - boxWidth / 2}
                  y1={yMedian}
                  x2={cx + boxWidth / 2}
                  y2={yMedian}
                  stroke="#0f766e"
                  strokeWidth={2}
                />
                {/* whisker: q3 → max */}
                <line x1={cx} y1={yQ3} x2={cx} y2={yMax} stroke="#94a3b8" strokeWidth={1.5} />
                {/* whisker cap at max */}
                <line x1={cx - 6} y1={yMax} x2={cx + 6} y2={yMax} stroke="#94a3b8" strokeWidth={1.5} />
                {/* group label */}
                <text
                  x={cx}
                  y={CHART_HEIGHT - 4}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#94a3b8"
                >
                  {String(row.group).length > 10
                    ? String(row.group).slice(0, 10) + "…"
                    : row.group}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
