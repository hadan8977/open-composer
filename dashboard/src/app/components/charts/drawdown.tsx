import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function DrawdownChart({ data }: { data: Array<{ ts: string; value: number }> }) {
  const rows = data.length > 0 ? data : [{ ts: "n/a", value: 0 }];
  return (
    <div className="h-[180px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(18,24,38,.08)" vertical={false} />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} width={56} domain={["dataMin", 0]} />
          <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#FF2D7A"
            fill="rgba(255,45,122,.12)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
