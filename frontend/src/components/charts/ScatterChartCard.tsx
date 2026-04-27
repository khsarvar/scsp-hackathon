"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface ScatterChartCardProps {
  title: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: { value: unknown; name: string }[];
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (active && payload && payload.length >= 2) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm px-3 py-2 text-xs">
        <p className="text-slate-600"><span className="font-medium">x:</span> {String(payload[0].value)}</p>
        <p className="text-slate-600"><span className="font-medium">y:</span> {String(payload[1].value)}</p>
      </div>
    );
  }
  return null;
}

export default function ScatterChartCard({ title, data, xKey, yKey }: ScatterChartCardProps) {
  const scatterData = data.map((d) => ({ x: d[xKey], y: d[yKey] }));

  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-slate-700 mb-4">{title}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="x"
            type="number"
            name={xKey}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
            label={{ value: xKey, position: "insideBottom", offset: -2, fontSize: 10, fill: "#94a3b8" }}
          />
          <YAxis
            dataKey="y"
            type="number"
            name={yKey}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            width={50}
          />
          <Tooltip content={<CustomTooltip />} />
          <Scatter
            data={scatterData}
            fill="#14b8a6"
            fillOpacity={0.6}
            r={4}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
