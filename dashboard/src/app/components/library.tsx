import { Filter, Download, ArrowUpDown } from "lucide-react";
import { Card, Tag, Pill } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import { strategies, Strategy } from "./data";

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
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting="Strategy library · 24 specs"
        headline="Catalog"
        meta="Every StrategySpec across versions, lifecycles and risk tiers — one source of truth."
        stat={{ label: "Active / total", value: "12 / 24", delta: "5 approved · 6 draft" }}
      />

      <div className="flex items-center gap-2 pt-1">
        {[
          ["All", "24"],
          ["Active", "12"],
          ["Approved", "5"],
          ["Draft", "6"],
          ["Retired", "1"],
        ].map(([l, c], i) => (
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
              {c}
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
              {strategies.map((s) => {
                const m = modelTag[s.modelClass];
                const r = riskTag[s.risk];
                return (
                  <tr
                    key={s.id}
                    onClick={() => onSelect?.(s.id)}
                    className="hairline-b last:border-b-0 hover:bg-[var(--paper-4)] transition-colors cursor-pointer group"
                  >
                    <td className="px-5 py-3">
                      <div className="t-title-sm">{s.name}</div>
                      <div className="t-mono ink-subtle mt-0.5">{s.symbol} · {s.version}</div>
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
