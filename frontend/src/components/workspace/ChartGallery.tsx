"use client";

import type { ChartSpec } from "@/types";
import LineChartCard from "@/components/charts/LineChartCard";
import BarChartCard from "@/components/charts/BarChartCard";
import ScatterChartCard from "@/components/charts/ScatterChartCard";

interface ChartGalleryProps {
  charts: ChartSpec[];
}

export default function ChartGallery({ charts }: ChartGalleryProps) {
  if (charts.length === 0) {
    return <p className="text-sm text-slate-400 italic">No charts could be generated for this dataset.</p>;
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {charts.map((chart, i) => {
        if (chart.chart_type === "line") {
          return (
            <LineChartCard
              key={i}
              title={chart.title}
              data={chart.data as Record<string, unknown>[]}
              xKey={chart.x_key}
              yKeys={chart.y_keys}
            />
          );
        }
        if (chart.chart_type === "bar" && chart.y_key) {
          return (
            <BarChartCard
              key={i}
              title={chart.title}
              data={chart.data as Record<string, unknown>[]}
              xKey={chart.x_key}
              yKey={chart.y_key}
            />
          );
        }
        if (chart.chart_type === "scatter" && chart.y_key) {
          return (
            <ScatterChartCard
              key={i}
              title={chart.title}
              data={chart.data as Record<string, unknown>[]}
              xKey={chart.x_key}
              yKey={chart.y_key}
            />
          );
        }
        return null;
      })}
    </div>
  );
}
