/**
 * Sparkline — composer-style: polyline + soft area gradient + end-point ring.
 * `area` defaults to true on >= 80px wide so dense table sparklines stay clean.
 */
export function Sparkline({
  data,
  color = "#1FB85A",
  width = 120,
  height = 32,
  area,
  baseline = false,
  strokeWidth = 1.5,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
  area?: boolean;
  baseline?: boolean;
  strokeWidth?: number;
}) {
  if (!data.length) return null;
  const showArea = area ?? width >= 80;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1 || 1);
  const coords = data.map((v, i) => [i * step, height - ((v - min) / range) * (height - 2) - 1] as [number, number]);
  const points = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const areaPath = `0,${height} ${points} ${width},${height}`;
  const [lastX, lastY] = coords[coords.length - 1];

  // unique gradient id per render (color + size)
  const gid = `sl-${color.replace("#", "")}-${width}-${height}`;

  return (
    <svg width={width} height={height} className="block" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {baseline && (
        <line
          x1={0}
          x2={width}
          y1={height - ((data[0] - min) / range) * (height - 2) - 1}
          y2={height - ((data[0] - min) / range) * (height - 2) - 1}
          stroke="rgba(10,10,10,.10)"
          strokeDasharray="2 3"
          strokeWidth="1"
        />
      )}
      {showArea && <polygon points={areaPath} fill={`url(#${gid})`} />}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* end-point: white halo + filled dot */}
      <circle cx={lastX} cy={lastY} r="3.2" fill="#fff" />
      <circle cx={lastX} cy={lastY} r="2" fill={color} />
    </svg>
  );
}
