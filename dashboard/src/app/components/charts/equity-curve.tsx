import {
  Area,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from "recharts";

export type ChartPoint = {
  ts: string;
  value: number;
  benchmark?: number;
};

export function EquityCurve({ data }: { data: ChartPoint[] }) {
  const rows = data.length > 0 ? data : [{ ts: "n/a", value: 100000 }];
  return (
    <div className="h-[260px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 12, right: 18, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(18,24,38,.08)" vertical={false} />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} width={68} domain={["dataMin", "dataMax"]} />
          <Tooltip formatter={(value) => money(Number(value))} />
          <Area
            type="monotone"
            dataKey="value"
            fill="rgba(31,184,90,.10)"
            stroke="none"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#1FB85A"
            strokeWidth={2.2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#8A93A0"
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function money(value: number) {
  if (!Number.isFinite(value)) return "n/a";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}
