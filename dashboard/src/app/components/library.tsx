import { ArrowUpDown, Download, Filter, Terminal } from "lucide-react";
import { Card, Tag, Pill } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import { dashboardSummary, strategies, Strategy } from "./data";

const riskTag: Record<Strategy["risk"], { color: any; label: string }> = {
  stable:   { color: "green",  label: "stable" },
  moderate: { color: "orange", label: "moderate" },
  high:     { color: "pink",   label: "high-risk" },
};

const modelTag: Record<Strategy["modelClass"], { color: any; label: string }> = {
  "pure-quant":         { color: "paper",  label: "pure quant" },
  "quant-review":       { color: "cyan",   label: "+ review" },
  "quant-scan":         { color: "purple", label: "+ scan" },
  "quant-orchestrator": { color: "black",  label: "+ orchestrator" },
};

const statusTag: Record<Strategy["status"], any> = {
  active: "green",
  approved: "cyan",
  draft: "paper",
  retired: "paper",
};

export function Library({ onSelect }: { onSelect?: (id: string) => void }) {
  const filters = [
    ["All", dashboardSummary.strategyCount],
    ["Active", dashboardSummary.activeStrategyCount],
    ["Approved", dashboardSummary.approvedStrategyCount],
    ["Draft", dashboardSummary.draftStrategyCount],
    ["Retired", dashboardSummary.retiredStrategyCount],
  ] as const;

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting={`Strategy library · ${dashboardSummary.strategyCount} specs`}
        headline="Catalog"
        meta="Every StrategySpec in the generated dashboard read model, grouped by lifecycle, capability and risk."
        stat={{
          label: "Active / total",
          value: `${dashboardSummary.activeStrategyCount} / ${dashboardSummary.strategyCount}`,
          delta: `${dashboardSummary.approvedStrategyCount} approved · ${dashboardSummary.draftStrategyCount} draft`,
        }}
      />

      <div className="flex items-center gap-2 pt-1">
        {filters.map(([l, c], i) => (
          <button
            key={l}
            className={`pill ${i === 0 ? "pill-primary" : "pill-secondary"}`}
          >
            {l}
            <span
              className={`t-num inline-flex items-center justify-center ${
                i === 0 ? "bg-white/15 text-white" : "bg-[rgba(10,10,10,.06)] ink-muted"
              }`}
              style={{ minWidth: 18, height: 16, padding: "0 5px", borderRadius: 2, fontSize: 10, fontWeight: 600 }}
            >
              {String(c)}
            </span>
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <Pill><Filter size={12} /> Filter</Pill>
          <Pill><ArrowUpDown size={12} /> Sort: Sharpe</Pill>
          <Pill><Download size={12} /> Export</Pill>
        </div>
      </div>

      <Card pad={false}>
        <div className="grid grid-cols-[44px_minmax(0,1fr)] gap-3 p-4 items-start">
          <span
            className="flex h-11 w-11 items-center justify-center bg-[rgba(10,10,10,.06)]"
            style={{ borderRadius: "var(--r-md)" }}
          >
            <Terminal size={17} strokeWidth={2.2} />
          </span>
          <div className="min-w-0">
            <div className="t-title-sm">Strategy creation stays in CLI files.</div>
            <div className="t-body-sm ink-subtle mt-1 leading-snug">
              Draft and verify StrategySpecs from the terminal, then rebuild the dashboard catalog.
            </div>
            <div className="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-2">
              {[
                'uv run oc strategy draft --idea "QQQ 15m breakout with volume filter"',
                "uv run oc spec validate strategy_specs/drafts/<name>.yaml",
                "uv run oc spec capabilities strategy_specs/drafts/<name>.yaml",
              ].map((command) => (
                <div
                  key={command}
                  className="t-mono ink bg-[var(--paper-3)] px-3 py-2 truncate"
                  style={{ borderRadius: "var(--r-sm)" }}
                  title={command}
                >
                  {command}
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Card pad={false}>
        <div className="overflow-hidden" style={{ borderRadius: "var(--r-xl)" }}>
          <table className="w-full t-body-sm" style={{ borderCollapse: "separate", borderSpacing: 0 }}>
            <thead>
              <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
                <th className="text-left px-5 py-2.5 t-caption ink-muted">Name</th>
                <th className="text-left t-caption ink-muted">Status</th>
                <th className="text-left t-caption ink-muted">Model class</th>
                <th className="text-left t-caption ink-muted">Risk</th>
                <th className="text-left t-caption ink-muted">Group</th>
                <th className="text-center t-caption ink-muted">Pine</th>
                <th className="text-center t-caption ink-muted">Py</th>
                <th className="text-center t-caption ink-muted">Alpaca</th>
                <th className="text-right t-caption ink-muted">Sharpe</th>
                <th className="text-right t-caption ink-muted">Last 30d</th>
                <th className="text-right pr-5 t-caption ink-muted">Trend</th>
              </tr>
            </thead>
            <tbody>
              {strategies.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-5 py-8 t-body-sm ink-muted">
                    Run `uv run oc dashboard catalog` to populate the read model.
                  </td>
                </tr>
              ) : strategies.map((s) => {
                const m = modelTag[s.modelClass];
                const r = riskTag[s.risk];
                const reasonCount =
                  s.backendReasons.length +
                  Object.values(s.compatibilityReasons).reduce((count, reasons) => count + reasons.length, 0);
                return (
                  <tr
                    key={s.id}
                    onClick={() => onSelect?.(s.id)}
                    className="hairline-b last:border-b-0 hover:bg-[var(--paper-4)] transition-colors cursor-pointer group"
                  >
                    <td className="px-5 py-3">
                      <div className="t-title-sm">{s.name}</div>
                      <div className="t-mono ink-subtle mt-0.5">{s.symbol} · {s.version}</div>
                      <div className="t-body-xs mt-1" style={{ color: s.backendStatus === "supported" ? "#0F9A52" : s.backendStatus === "partial" ? "#C57A00" : "#C81E5C" }}>
                        Backend {s.backendStatus}{reasonCount > 0 ? ` · ${reasonCount} reasons` : ""}
                      </div>
                    </td>
                    <td><Tag color={statusTag[s.status]}>{s.status}</Tag></td>
                    <td><Tag color={m.color}>{m.label}</Tag></td>
                    <td><Tag color={r.color}>{r.label}</Tag></td>
                    <td className="ink-muted">{s.group}</td>
                    <td className="text-center">{s.pine ? <span style={{ color: "#1FB85A", fontSize: 11 }}>●</span> : <span className="ink-subtle opacity-30">—</span>}</td>
                    <td className="text-center">{s.python ? <span style={{ color: "#1FB85A", fontSize: 11 }}>●</span> : <span className="ink-subtle opacity-30">—</span>}</td>
                    <td className="text-center">{s.alpaca ? <span style={{ color: "#1FB85A", fontSize: 11 }}>●</span> : <span className="ink-subtle opacity-30">—</span>}</td>
                    <td className="text-right t-num" style={{ fontWeight: 600 }}>{s.sharpe}</td>
                    <td className="text-right t-num" style={{ color: s.lastReturn >= 0 ? "#0A6E3B" : "#C81E5C", fontWeight: 600 }}>
                      {s.lastReturn >= 0 ? "+" : ""}{s.lastReturn}%
                    </td>
                    <td className="pr-5 py-2 text-right">
                      <div className="inline-block">
                        <Sparkline
                          data={s.series}
                          color={s.lastReturn >= 0 ? "#16C268" : "#FF2D7A"}
                          width={120}
                          height={28}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
