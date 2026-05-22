import { ArrowUpRight, Play, AlertTriangle } from "lucide-react";
import { Card, KPI, SectionTitle, Tag, Pill, ColorBlock } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import {
  dashboardSummary,
  events,
  llmReviews,
  recentSignals,
  strategies,
  strategyGroups,
} from "./data";

export function Overview() {
  const activeStrategies = strategies.filter((s) => s.status === "active");
  const highlightedStrategies = (activeStrategies.length > 0 ? activeStrategies : strategies).slice(0, 4);
  const latestRun = strategies.find((s) => s.lastReturn !== 0);
  const equityLabel = dashboardSummary.paperAccountEquity
    ? money(dashboardSummary.paperAccountEquity)
    : "No paper equity";
  const deployLabel = `${dashboardSummary.deploymentStatus} deploy`;
  const returnLabel = latestRun ? `${signed(latestRun.lastReturn)} last run` : deployLabel;
  const sharpeLabel = latestRun ? `Sharpe ${latestRun.sharpe}` : "Awaiting backtest";
  const groupHint = `${strategyGroups.length} read-model groups`;
  const equitySeries = latestRun?.series ?? [100, 100];

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting={`Catalog · ${dashboardSummary.generatedLabel}`}
        headline="Workbench"
        meta={`${dashboardSummary.projectCount || dashboardSummary.strategyCount} projects · ${dashboardSummary.strategyCount} specs · ${dashboardSummary.runCount} runs · ${dashboardSummary.signalCount} logged signals.`}
        stat={{
          label: "Paper state",
          value: dashboardSummary.deploymentReady ? "Ready" : "Check",
          delta: `${dashboardSummary.deploymentStatus} deploy`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-4">
          <PrimaryKPI
            label="Paper account equity"
            value={equityLabel}
            sub={`${returnLabel} · ${sharpeLabel}`}
          />
        </div>
        <div className="col-span-2"><KPI label="Active" value={String(dashboardSummary.activeStrategyCount)} delta={`${dashboardSummary.approvedStrategyCount} approved`} accent="black" /></div>
        <div className="col-span-2"><KPI label="Paper auto" value={String(dashboardSummary.paperAutoStrategyCount)} delta={`${dashboardSummary.paperOpenOrderCount} open orders`} accent="green" /></div>
        <div className="col-span-2"><KPI label="Open pos." value={String(dashboardSummary.paperPositionCount)} delta={money(dashboardSummary.paperTotalUnrealizedPl)} accent="pink" /></div>
        <div className="col-span-2"><KPI label="Deploy" value={dashboardSummary.deploymentStatus} delta={dashboardSummary.deploymentNextAction ?? "ready"} accent="orange" /></div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card variant="dark" pad={false} className="col-span-8">
          <div className="px-5 pt-4 pb-2 flex items-end justify-between gap-4">
            <div className="min-w-0">
              <div className="t-caption" style={{ color: "rgba(242,242,240,.55)" }}>
                Paper equity · read model
              </div>
              <div className="t-display-lg t-num mt-2">{equityLabel}</div>
              <div className="t-body-sm mt-1.5 flex items-center gap-1.5" style={{ color: "#3DD68C" }}>
                <ArrowUpRight size={13} strokeWidth={2.4} />
                {returnLabel}
                <span style={{ color: "rgba(242,242,240,.4)" }}>·</span>
                <span>{sharpeLabel}</span>
              </div>
            </div>
            <div className="flex items-center gap-0.5 p-1 rounded-full bg-white/5">
              {["1D", "1W", "1M", "YTD", "1Y", "All"].map((p, i) => (
                <button
                  key={p}
                  className={`px-2.5 h-7 inline-flex items-center t-body-sm rounded-full transition-colors ${
                    i === 3 ? "bg-white text-[#0A0A0A]" : "text-white/65 hover:text-white"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <EquityChart data={equitySeries} />
          <div
            className="grid grid-cols-4 mx-3 mb-3 gap-px overflow-hidden"
            style={{ background: "rgba(255,255,255,.06)", borderRadius: "var(--r-md)" }}
          >
            {[
              ["Projects", String(dashboardSummary.projectCount || dashboardSummary.strategyCount)],
              ["Runs", String(dashboardSummary.runCount)],
              ["Signals", String(dashboardSummary.signalCount)],
              ["Ready", dashboardSummary.readinessReady ? "yes" : "no"],
            ].map(([k, v]) => (
              <div key={k} className="px-4 py-3" style={{ background: "#0B0B0C" }}>
                <div className="t-caption" style={{ color: "rgba(242,242,240,.5)" }}>{k}</div>
                <div className="t-display-md mt-1.5 t-num">{v}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card pad={false} className="col-span-4">
          <div className="px-5 pt-4 pb-3">
            <SectionTitle tick="cyan" hint={groupHint}>Read-model groups</SectionTitle>
          </div>
          <div className="grid grid-cols-6 grid-rows-4 gap-1 px-4 pb-4 h-[260px]">
            {strategyGroups.length === 0 ? (
              <div className="col-span-6 row-span-4 p-4 bg-paper-3 flex items-end" style={{ borderRadius: "var(--r-md)" }}>
                <span className="t-body-sm ink-muted">Run the dashboard catalog command to populate groups.</span>
              </div>
            ) : (
              strategyGroups.slice(0, 6).map((group, index) => (
                <ColorBlock
                  key={group.id}
                  color={group.color}
                  rounded="sm"
                  halftone={index % 2 === 0}
                  className={`${index === 0 ? "col-span-3 row-span-2" : index === 1 ? "col-span-3" : "col-span-2"} p-3 flex flex-col justify-between`}
                >
                  <span className="t-caption" style={{ position: "relative", zIndex: 1 }}>{group.name}</span>
                  <span className="t-display-md t-num" style={{ position: "relative", zIndex: 1 }}>{group.weight}%</span>
                </ColorBlock>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="px-5 pt-4 pb-3 hairline-b">
          <SectionTitle tick="green" action={<Pill variant="ghost">View all →</Pill>}>
            {activeStrategies.length > 0 ? "Active strategies" : "Catalog strategies"}
          </SectionTitle>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4">
          {highlightedStrategies.map((s, i) => {
            const stripe = s.lastReturn >= 0 ? "#1FB85A" : "#FF2D7A";
            const reasonCount =
              s.backendReasons.length +
              Object.values(s.compatibilityReasons).reduce((count, reasons) => count + reasons.length, 0);
            return (
              <div
                key={s.id}
                className={`relative p-4 pt-5 transition-colors hover:bg-[var(--paper-4)] cursor-pointer ${i < 3 ? "hairline-r" : ""}`}
              >
                {/* composer-signature top stripe */}
                <span
                  aria-hidden
                  className="absolute"
                  style={{ left: 16, right: 16, top: 0, height: 3, background: stripe }}
                />
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                  <div className="t-mono ink-subtle">{s.symbol} · {s.version}</div>
                  <div className="t-title-sm mt-1 truncate">{s.name}</div>
                  <div className="t-body-xs mt-1" style={{ color: s.backendStatus === "supported" ? "#0F9A52" : s.backendStatus === "partial" ? "#C57A00" : "#C81E5C" }}>
                    Backend {s.backendStatus}{reasonCount > 0 ? ` · ${reasonCount} reasons` : ""}
                  </div>
                </div>
                  <Tag color={s.lastReturn >= 0 ? "green" : "pink"}>
                    {s.lastReturn >= 0 ? "+" : ""}{s.lastReturn}%
                  </Tag>
                </div>
                <div className="my-3">
                  <Sparkline
                    data={s.series}
                    color={stripe}
                    width={220}
                    height={42}
                  />
                </div>
                <div className="flex items-center gap-2 t-body-sm ink-subtle">
                  <span>Sharpe <span className="ink t-num" style={{ fontWeight: 600 }}>{s.sharpe}</span></span>
                  <span>·</span>
                  <span><span className="ink t-num" style={{ fontWeight: 600 }}>{s.trades}</span> trades</span>
                  <span className="ml-auto inline-flex items-center gap-1" style={{ color: "#0F9A52", fontWeight: 600 }}>
                    <Play size={9} fill="#1FB85A" /> {s.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-3">
        <Card pad={false} className="col-span-5">
          <div className="px-5 py-3 hairline-b">
            <SectionTitle tick="green">Recent signals</SectionTitle>
          </div>
          <table className="w-full t-body-sm">
            <thead>
              <tr className="hairline-b">
                <th className="text-left px-5 py-2 t-caption ink-subtle">Time</th>
                <th className="text-left t-caption ink-subtle">Strategy</th>
                <th className="text-right t-caption ink-subtle">Side</th>
                <th className="text-right t-caption ink-subtle">Px</th>
                <th className="text-right px-5 t-caption ink-subtle">Sz</th>
              </tr>
            </thead>
            <tbody className="t-num">
              {recentSignals.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-6 ink-muted t-body-sm">
                    No signal log entries are present in the catalog.
                  </td>
                </tr>
              ) : recentSignals.map((r, i) => (
                <tr key={i} className="hairline-b last:border-b-0">
                  <td className="px-5 py-2.5 ink-muted">{r.t}</td>
                  <td className="truncate ink">{r.strat}</td>
                  <td className="text-right py-2.5">
                    <Tag color={r.side === "BUY" ? "green" : "black"}>{r.side}</Tag>
                  </td>
                  <td className="text-right">{r.px.toFixed(2)}</td>
                  <td className="text-right px-5">{r.sz}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card pad={false} className="col-span-4">
          <div className="px-5 py-3 hairline-b">
            <SectionTitle tick="orange">Event & macro feed</SectionTitle>
          </div>
          <ul className="divider-soft">
            {events.length === 0 ? (
              <li className="px-5 py-6 t-body-sm ink-muted">No data, context or feature records are present.</li>
            ) : events.map((e, i) => (
              <li key={i} className="px-5 py-2.5 flex items-center gap-3">
                <span className="t-body-sm ink-subtle t-num w-10 shrink-0">{e.t}</span>
                <Tag color={e.kind === "Earnings" ? "pink" : e.kind === "Macro" ? "orange" : e.kind === "News" ? "cyan" : "paper"}>
                  {e.kind}
                </Tag>
                <span className="t-body-sm flex-1 ink leading-snug">{e.title}</span>
                {e.impact === "high" && <AlertTriangle size={13} style={{ color: "#FF2D7A" }} />}
              </li>
            ))}
          </ul>
        </Card>

        <Card pad={false} className="col-span-3">
          <div className="px-5 py-3 hairline-b">
            <SectionTitle tick="purple">LLM review queue</SectionTitle>
          </div>
          <div className="p-2.5 space-y-2">
            {llmReviews.length === 0 ? (
              <div className="bg-paper-3 p-3 t-body-sm ink-muted" style={{ borderRadius: "var(--r-md)" }}>
                No LLM review cards have been generated yet.
              </div>
            ) : llmReviews.map((r) => (
              <div key={r.id} className="bg-paper-3 p-3" style={{ borderRadius: "var(--r-md)" }}>
                <div className="flex items-center justify-between mb-1.5">
                  <Tag pill color={r.color}>{r.verdict}</Tag>
                  <span className="t-mono ink-subtle">{r.id}</span>
                </div>
                <div className="t-title-sm">{r.strat}</div>
                <div className="t-body-sm ink-muted mt-1 leading-snug">{r.summary}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function money(value: number) {
  return value === 0
    ? "$0.00"
    : value.toLocaleString([], { style: "currency", currency: "USD" });
}

/* Primary KPI — composer-style ink panel, animated gradient value,
   embedded micro-sparkline. */
function PrimaryKPI({ label, value, sub }: { label: string; value: string; sub: string }) {
  // micro sparkline (deterministic so it doesn't reflow on rerender)
  const pts = [12, 18, 14, 22, 19, 27, 24, 31, 28, 36, 33, 39, 35, 44, 42, 48];
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const w = 220;
  const h = 28;
  const path = pts
    .map((p, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - ((p - min) / (max - min)) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div
      className="relative overflow-hidden h-full"
      style={{
        background: "linear-gradient(180deg, #FFFFFF 0%, #FAFCFF 100%)",
        borderRadius: "var(--r-md)",
        padding: "16px 18px 16px",
        boxShadow: "0 0 0 1px rgba(18,24,38,.08), 0 1px 0 rgba(18,24,38,.03)",
        minHeight: 116,
      }}
    >
      {/* corner accent stamps — green + cyan, composer's "lead" mark */}
      <span aria-hidden className="absolute" style={{ right: 12, top: 12, width: 14, height: 14, background: "#1FB85A", borderRadius: 2 }} />
      <span aria-hidden className="absolute" style={{ right: 30, top: 12, width: 8, height: 14, background: "#1AC8E8", borderRadius: 2 }} />

      <div className="t-caption" style={{ color: "rgba(42,51,66,.58)", letterSpacing: 0 }}>
        {label}
      </div>
      <div
        className="t-num mt-2.5 grad-green-cyan"
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 800,
          fontSize: "clamp(28px, 3vw, 42px)",
          lineHeight: 1.02,
          letterSpacing: 0,
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </div>
      <div
        className="t-body-sm mt-2"
        style={{ color: "rgba(42,51,66,.62)", fontWeight: 500 }}
      >
        {sub}
      </div>

      {/* embedded micro-sparkline */}
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        aria-hidden
        className="absolute"
        style={{ right: 14, bottom: 14, width: 120, height: 18, opacity: 0.85 }}
      >
        <defs>
          <linearGradient id="pkpi-line" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#1FB85A" />
            <stop offset="100%" stopColor="#1AC8E8" />
          </linearGradient>
        </defs>
        <path d={path} fill="none" stroke="url(#pkpi-line)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>

      {/* tonal underline */}
      <span
        aria-hidden
        className="absolute"
        style={{
          left: 0, right: 0, bottom: 0,
          height: 3,
          background: "linear-gradient(90deg, #1FB85A 0%, #1AC8E833 70%, transparent 100%)",
        }}
      />
    </div>
  );
}

function EquityChart({ data: inputData }: { data: number[] }) {
  const w = 760;
  const h = 220;
  const padL = 0;
  const padR = 0;
  const padT = 12;
  const padB = 28;
  const data = inputData.length >= 2 ? inputData : [100, 100];
  const N = data.length;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const step = innerW / (N - 1);
  const ptsArr = data.map((d, i) => [padL + i * step, padT + innerH - ((d - min) / range) * innerH] as [number, number]);
  const pts = ptsArr.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `${padL},${padT + innerH} ${pts} ${padL + innerW},${padT + innerH}`;
  const [lastX, lastY] = ptsArr[ptsArr.length - 1];

  // Y-axis ticks (4 levels)
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((p) => ({
    y: padT + p * innerH,
    label: (max - p * range).toFixed(1),
  }));
  const xLabels = ["Start", "Mid", "Last"];

  return (
    <div className="relative px-3 pb-2">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 220 }} preserveAspectRatio="none">
        <defs>
          <linearGradient id="eq-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#1FB85A" stopOpacity="0.34" />
            <stop offset="100%" stopColor="#1FB85A" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="eq-line" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#1FB85A" />
            <stop offset="100%" stopColor="#1AC8E8" />
          </linearGradient>
        </defs>

        {/* Horizontal grid + y-labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={padL}
              x2={padL + innerW}
              y1={t.y}
              y2={t.y}
              stroke="rgba(255,255,255,.05)"
              strokeDasharray="2 4"
            />
            <text
              x={padL + innerW - 4}
              y={t.y - 4}
              fontFamily="JetBrains Mono, ui-monospace, monospace"
              fontSize="9.5"
              fill="rgba(242,242,240,.35)"
              textAnchor="end"
            >
              {t.label}
            </text>
          </g>
        ))}

        {/* X-axis labels */}
        {xLabels.map((label, i) => {
          const x = padL + (innerW / (xLabels.length - 1)) * i;
          return (
            <text
              key={label}
              x={x}
              y={h - 8}
              fontFamily="Inter, sans-serif"
              fontSize="9.5"
              fill="rgba(242,242,240,.4)"
              textAnchor={i === 0 ? "start" : i === xLabels.length - 1 ? "end" : "middle"}
              letterSpacing="0"
            >
              {label.toUpperCase()}
            </text>
          );
        })}

        <polygon points={area} fill="url(#eq-area)" />
        <polyline points={pts} fill="none" stroke="url(#eq-line)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />

        {/* Vertical guideline + end-point marker */}
        <line x1={lastX} x2={lastX} y1={padT} y2={padT + innerH} stroke="rgba(255,255,255,.12)" strokeDasharray="2 3" />
        <circle cx={lastX} cy={lastY} r="5" fill="#1FB85A" opacity="0.25" />
        <circle cx={lastX} cy={lastY} r="3" fill="#1FB85A" />
        <circle cx={lastX} cy={lastY} r="1.4" fill="#fff" />
      </svg>
    </div>
  );
}
