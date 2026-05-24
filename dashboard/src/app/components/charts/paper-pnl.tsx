import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function PaperPnlChart({ value }: { value: number }) {
  const rows = [
    { ts: "previous", value: 0 },
    { ts: "current", value },
  ];
  const color = value >= 0 ? "#1FB85A" : "#FF2D7A";
  return (
    <div className="h-[180px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(18,24,38,.08)" vertical={false} />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={64} />
          <Tooltip formatter={(item) => `$${Number(item).toFixed(2)}`} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            fill={value >= 0 ? "rgba(31,184,90,.12)" : "rgba(255,45,122,.12)"}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
