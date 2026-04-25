"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { TEAL_PALETTE } from "@/lib/constants";

interface BarChartCardProps {
  title: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
}

export default function BarChartCard({ title, data, xKey, yKey }: BarChartCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-slate-700 mb-4">{title}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            width={50}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid #e2e8f0",
              boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.05)",
            }}
          />
          <Bar dataKey={yKey} radius={[4, 4, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={TEAL_PALETTE[i % TEAL_PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
