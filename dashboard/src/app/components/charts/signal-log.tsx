import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type SignalPoint = {
  timestamp: string;
  price: number;
  side: string;
  action?: string;
};

export function SignalLogChart({ data }: { data: SignalPoint[] }) {
  const rows = data.length > 0 ? data : [{ timestamp: "n/a", price: 0, side: "none" }];
  return (
    <div className="h-[220px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart data={rows} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(18,24,38,.08)" vertical={false} />
          <XAxis dataKey="timestamp" tick={{ fontSize: 11 }} minTickGap={20} />
          <YAxis dataKey="price" tick={{ fontSize: 11 }} width={58} domain={["dataMin", "dataMax"]} />
          <Tooltip
            formatter={(value, name) => (name === "price" ? Number(value).toFixed(2) : String(value))}
            labelFormatter={(label) => String(label)}
          />
          <Scatter dataKey="price" fill="#0A0A0A" isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
