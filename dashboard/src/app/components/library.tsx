import { useState } from "react";
import { Filter, Download, ArrowUpDown, Sparkles } from "lucide-react";
import { Card, Tag, Pill } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import { applyDashboardCatalog, dashboardSummary, strategies, Strategy } from "./data";
import { getDashboardJson, postDashboardJson } from "./runtime";

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
  const [idea, setIdea] = useState(
    "Create a QQQ 15m breakout strategy with volume expansion and volatility filter.",
  );
  const [useLlm, setUseLlm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftStatus, setDraftStatus] = useState("Local command API is idle.");
  const filters = [
    ["All", dashboardSummary.strategyCount],
    ["Active", dashboardSummary.activeStrategyCount],
    ["Approved", dashboardSummary.approvedStrategyCount],
    ["Draft", dashboardSummary.draftStrategyCount],
    ["Retired", dashboardSummary.retiredStrategyCount],
  ] as const;

  const refreshCatalog = async () => {
    const runtimeCatalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
      "/api/dashboard/catalog",
    );
    applyDashboardCatalog(runtimeCatalog as Parameters<typeof applyDashboardCatalog>[0]);
  };

  const runDraftCommand = async () => {
    const cleanIdea = idea.trim();
    if (!cleanIdea) {
      setDraftStatus("Idea is required.");
      return;
    }
    setBusy(true);
    setDraftStatus("Creating draft command plan...");
    try {
      const plan = await postDashboardJson<{
        command_id: string;
        confirmation_phrase: string;
        plan_path?: string | null;
      }>("/api/dashboard/command-plan", {
        action: "strategy.draft",
        reason: "dashboard draft",
        requested_by: "dashboard",
        idea: cleanIdea,
        use_llm: useLlm,
      });
      if (!plan.plan_path) {
        throw new Error("dashboard command plan missing plan_path");
      }
      const confirmation = window.prompt(
        `Type the exact confirmation phrase to draft this strategy.\n\n${plan.confirmation_phrase}`,
        plan.confirmation_phrase,
      );
      if (confirmation === null) {
        setDraftStatus("Draft command plan created. Execution cancelled before confirmation.");
        return;
      }
      setDraftStatus("Executing draft command...");
      const result = await postDashboardJson<{
        status: string;
        message: string;
        output_paths?: string[];
      }>("/api/dashboard/command-run", {
        plan_path: plan.plan_path,
        confirm: confirmation,
        executed_by: "dashboard",
      });
      await refreshCatalog();
      const output = result.output_paths?.[0] ? ` · ${result.output_paths[0]}` : "";
      setDraftStatus(`${result.message}${output}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown dashboard command error";
      setDraftStatus(message);
    } finally {
      setBusy(false);
    }
  };

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
        <div className="grid grid-cols-12 gap-3 p-4 items-stretch">
          <div className="col-span-8">
            <textarea
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              className="ds-input w-full min-h-[86px] resize-none bg-transparent px-3 py-2 outline-none t-body-md"
              placeholder="Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
            />
          </div>
          <div className="col-span-4 flex flex-col gap-2">
            <label className="ds-input flex items-center gap-2 h-10 px-3">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(event) => setUseLlm(event.target.checked)}
              />
              <span className="t-body-sm ink">Use LLM</span>
            </label>
            <button
              onClick={runDraftCommand}
              disabled={busy}
              className="pill pill-primary justify-center h-10"
              style={{ opacity: busy ? 0.72 : 1 }}
            >
              <Sparkles size={14} />
              Draft strategy
            </button>
            <div className="t-body-sm ink-subtle leading-snug">{draftStatus}</div>
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
