import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function FactorICChart({
  data,
}: {
  data: Array<{ name: string; value: number | null }>;
}) {
  const rows = data.length > 0 ? data : [{ name: "n/a", value: null }];
  return (
    <div className="h-[128px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={36} />
          <Tooltip formatter={(value) => Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "n/a"} />
          <Bar dataKey="value" fill="#1AC8E8" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
