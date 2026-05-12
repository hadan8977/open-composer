import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  GitCommit,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Card, SectionTitle, Tag, KPI, Pill, ColorBlock } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import {
  auditLog,
  applyDashboardCatalog,
  dashboardSummary,
  events,
  llmReviews,
  paperOrders,
  paperPositions,
  paperReadinessReports,
  strategies,
  strategyGroups,
  versions,
} from "./data";
import { getDashboardJson, postDashboardJson } from "./runtime";

/* ---------------- Versions ---------------- */

export function Versions() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="cyan"
        greeting="Version control · immutable"
        headline="Lineage"
        meta="Every visible version is rebuilt from StrategySpec snapshots and registry records."
        stat={{ label: "Versions tracked", value: String(dashboardSummary.versionCount), delta: dashboardSummary.generatedLabel }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Versions tracked" value={String(dashboardSummary.versionCount)} accent="black" /></div>
        <div className="col-span-3"><KPI label="Active pointers" value={String(dashboardSummary.activeStrategyCount)} accent="green" /></div>
        <div className="col-span-3"><KPI label="Draft specs" value={String(dashboardSummary.draftStrategyCount)} accent="pink" /></div>
        <div className="col-span-3"><KPI label="LLM-enabled" value={String(strategies.filter((s) => s.llmReviewEnabled).length)} accent="orange" /></div>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="cyan" action={<Pill variant="ghost">Compare two →</Pill>}>
            Recent versions
          </SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Version</th>
              <th className="text-left t-caption ink-subtle">Strategy</th>
              <th className="text-left t-caption ink-subtle">Parent</th>
              <th className="text-left t-caption ink-subtle">Author</th>
              <th className="text-left t-caption ink-subtle">Created</th>
              <th className="text-left t-caption ink-subtle">Diff</th>
              <th className="text-left t-caption ink-subtle">Hash</th>
              <th className="text-left t-caption ink-subtle">Status</th>
              <th className="px-5"></th>
            </tr>
          </thead>
          <tbody>
            {versions.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-5 py-8 t-body-sm ink-muted">
                  No version records are present in the dashboard catalog.
                </td>
              </tr>
            ) : versions.map((v) => (
              <tr key={v.id + v.strat} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 flex items-center gap-2">
                  <GitCommit size={14} className="ink-subtle" />
                  <span className="t-mono">{v.id}</span>
                </td>
                <td className="t-title-sm">{v.strat}</td>
                <td className="ink-muted t-mono">{v.parent}</td>
                <td><Tag color={v.by === "llm" ? "purple" : v.by === "codex" ? "cyan" : "paper"}>{v.by}</Tag></td>
                <td className="ink-muted t-num">{v.at}</td>
                <td className="t-mono">{v.diff}</td>
                <td className="t-mono ink-subtle">{v.hash}</td>
                <td><Tag color={v.status === "active" ? "green" : v.status === "approved" ? "cyan" : "paper"}>{v.status}</Tag></td>
                <td className="px-5 text-right whitespace-nowrap">
                  <button className="t-body-sm ink-muted hover:ink mr-3">diff</button>
                  <button className="t-body-sm ink-muted hover:ink" disabled title="Rollback is only available through the CLI safety gate.">rollback</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ---------------- Paper monitor ---------------- */

export function Paper() {
  const runningStrategies = strategies.filter(
    (strategy) => strategy.executionMode === "paper_auto" || strategy.status === "active",
  );

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting={`Paper monitor · ${dashboardSummary.paperAutoStrategyCount} configured`}
        headline="Live"
        meta="Read-only paper account, order and reconciliation state from the generated catalog."
        stat={{
          label: "Kill switch",
          value: dashboardSummary.paperKillSwitchEnabled ? "Enabled" : "Clear",
          delta: `${dashboardSummary.paperOpenOrderCount} open orders`,
        }}
      />
      <PaperCommandDock />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Auto strategies" value={String(dashboardSummary.paperAutoStrategyCount)} accent="green" /></div>
        <div className="col-span-3"><KPI label="Open positions" value={String(dashboardSummary.paperPositionCount)} accent="black" /></div>
        <div className="col-span-2"><KPI label="Orders" value={String(paperOrders.length)} accent="cyan" /></div>
        <div className="col-span-2"><KPI label="Unrealized" value={money(dashboardSummary.paperTotalUnrealizedPl)} accent="pink" /></div>
        <div className="col-span-2"><KPI label="Alerts" value={dashboardSummary.paperAlertStatus} accent="orange" /></div>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="orange">Paper readiness</SectionTitle>
        </div>
        <div className="divide-y divide-[var(--hairline)]">
          {paperReadinessReports.length === 0 ? (
            <div className="px-5 py-5 t-body-sm ink-muted">
              No paper readiness reports are present.
            </div>
          ) : paperReadinessReports.map((report) => {
            const firstAction = report.checks.find((check) => check.status !== "ok")?.suggestedActions?.[0];
            return (
            <div key={report.path || report.strategyId} className="px-5 py-3.5 grid grid-cols-12 gap-3 items-start">
              <div className="col-span-3 min-w-0">
                <div className="t-title-sm truncate">{report.strategyName}</div>
                <div className="t-caption ink-subtle t-mono truncate mt-1">{report.path}</div>
              </div>
              <div className="col-span-2">
                <Tag color={report.status === "ok" ? "green" : report.status === "warning" ? "orange" : "pink"}>
                  {report.status}
                </Tag>
              </div>
              <div className="col-span-7 t-body-sm ink-muted">
                {report.blockingChecks.length > 0 ? (
                  <>Blocked: {report.blockingChecks.join(", ")}</>
                ) : report.warningChecks.length > 0 ? (
                  <>Warnings: {report.warningChecks.join(", ")}</>
                ) : (
                  <>Ready for paper automation</>
                )}
                {firstAction && (
                  <div className="t-caption t-mono ink-subtle mt-1 truncate">{firstAction}</div>
                )}
              </div>
            </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-7" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="green">Running strategies</SectionTitle>
          </div>
          <div className="divider-soft">
            {runningStrategies.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">
                No active or paper_auto strategies are checked into the current catalog.
              </div>
            ) : runningStrategies.map((s) => (
              <div key={s.id} className="px-5 py-3.5 flex items-center gap-4">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[#16C268] opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#16C268]" />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="t-title-sm truncate">{s.name}</div>
                  <div className="t-body-sm ink-subtle mt-0.5">{s.symbol} · {s.version} · {s.group}</div>
                  {s.backendPlanPath && (
                    <div className="t-caption ink-subtle mt-1 truncate">
                      Nautilus plan · {s.backendPlanPath}
                    </div>
                  )}
                </div>
                <Sparkline data={s.series} color={s.lastReturn >= 0 ? "#16C268" : "#FF2D7A"} width={140} height={28} />
                <div className="text-right t-num">
                  <div className="t-title-sm" style={{ color: s.lastReturn >= 0 ? "#0A6E3B" : "#C81E5C" }}>
                    {s.lastReturn >= 0 ? "+" : ""}{s.lastReturn}%
                  </div>
                  <div className="t-body-sm ink-subtle">{s.trades} trades</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-5" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="ink">Open positions</SectionTitle>
          </div>
          <table className="w-full t-body-sm">
            <thead>
              <tr className="hairline-b">
                <th className="text-left px-5 py-2.5 t-caption ink-subtle">Sym</th>
                <th className="text-right t-caption ink-subtle">Qty</th>
                <th className="text-right t-caption ink-subtle">Avg</th>
                <th className="text-right t-caption ink-subtle">Mkt</th>
                <th className="text-right pr-5 t-caption ink-subtle">uPnL</th>
              </tr>
            </thead>
            <tbody className="t-num">
              {paperPositions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 t-body-sm ink-muted">
                    No paper position snapshot is present.
                  </td>
                </tr>
              ) : paperPositions.map((p) => (
                <tr key={p.sym} className="hairline-b last:border-b-0">
                  <td className="px-5 py-3 t-title-sm">{p.sym}</td>
                  <td className="text-right">{p.qty}</td>
                  <td className="text-right">{p.avg.toFixed(2)}</td>
                  <td className="text-right">{p.mkt.toFixed(2)}</td>
                  <td className="text-right pr-5" style={{ color: p.upnl >= 0 ? "#0A6E3B" : "#C81E5C" }}>
                    {p.upnl >= 0 ? "+" : ""}{p.upnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

function PaperCommandDock() {
  type DashboardCommandPlan = {
    command_id: string;
    action: string;
    plan_path?: string | null;
    confirmation_phrase: string;
    cli_args: string[];
    warnings: string[];
  };
  type DashboardCommandResult = {
    command_id: string;
    action: string;
    status: string;
    message: string;
    result_path?: string | null;
    output_paths?: string[];
  };
  type RuntimePaperSummary = {
    generated_at?: string | null;
    paper_kill_switch_enabled?: boolean;
    paper_open_order_count?: number;
    paper_position_count?: number;
    paper_alert_status?: string;
    paper_reconciliation_status?: string;
    paper_account_equity?: number | null;
    paper_total_unrealized_pl?: number;
    paper_account_snapshot_at?: string | null;
    paper_positions_snapshot_at?: string | null;
    audit_count?: number;
  };

  const [reason, setReason] = useState("operator check");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Dashboard command API is local-only and confirmed.");
  const [lastPlan, setLastPlan] = useState<DashboardCommandPlan | null>(null);
  const [lastResult, setLastResult] = useState<DashboardCommandResult | null>(null);
  const refreshRuntimeSummary = async () => {
    const runtimeCatalog = await getDashboardJson<{ summary?: RuntimePaperSummary }>(
      "/api/dashboard/catalog",
    );
    applyDashboardCatalog(runtimeCatalog as Parameters<typeof applyDashboardCatalog>[0]);
  };

  useEffect(() => {
    void refreshRuntimeSummary().catch(() => {
      setStatusMessage("Dashboard catalog refresh failed; run make dashboard-serve.");
    });
  }, []);

  const actions = [
    {
      action: "paper.status.refresh",
      label: "Refresh status",
      hint: "Write a current paper snapshot",
      icon: RefreshCw,
      tone: "cyan" as const,
    },
    {
      action: "paper.sync.orders",
      label: "Sync orders",
      hint: "Pull broker order snapshot",
      icon: RefreshCw,
      tone: "cyan" as const,
    },
    {
      action: "paper.sync.account",
      label: "Sync account",
      hint: "Pull account and positions",
      icon: ArrowUpRight,
      tone: "green" as const,
    },
    {
      action: "paper.monitor.refresh",
      label: "Refresh monitor",
      hint: "Update reconciliation and alerts",
      icon: Activity,
      tone: "green" as const,
    },
    {
      action: "paper.kill_switch.enable",
      label: "Enable kill switch",
      hint: "Hold paper execution",
      icon: ShieldAlert,
      tone: "pink" as const,
    },
    {
      action: "paper.kill_switch.clear",
      label: "Clear kill switch",
      hint: "Resume guarded flow",
      icon: ShieldCheck,
      tone: "orange" as const,
    },
    {
      action: "system.prepare_workspace",
      label: "Prepare workspace",
      hint: "Rebuild catalog, reports, and readiness",
      icon: Wrench,
      tone: "green" as const,
    },
    {
      action: "system.readiness.refresh",
      label: "Refresh readiness",
      hint: "Rebuild deployment readiness",
      icon: RefreshCw,
      tone: "cyan" as const,
    },
  ];

  const runCommand = async (action: string) => {
    setBusyAction(action);
    setStatusMessage("Creating command plan…");
    setLastPlan(null);
    setLastResult(null);
    try {
      const plan = await postDashboardJson<DashboardCommandPlan>("/api/dashboard/command-plan", {
        action,
        reason,
        requested_by: "dashboard",
      });
      setLastPlan(plan);
      if (!plan.plan_path) {
        throw new Error("dashboard command plan missing plan_path");
      }
      const confirmation = window.prompt(
        `Type the exact confirmation phrase to execute this local command.\n\n${plan.confirmation_phrase}`,
        plan.confirmation_phrase,
      );
      if (confirmation === null) {
        setStatusMessage("Command plan created. Execution cancelled before confirmation.");
        return;
      }
      setStatusMessage("Executing local command…");
      const result = await postDashboardJson<DashboardCommandResult>("/api/dashboard/command-run", {
        plan_path: plan.plan_path,
        confirm: confirmation,
        executed_by: "dashboard",
      });
      setLastResult(result);
      await refreshRuntimeSummary();
      setStatusMessage(`${result.message}${result.result_path ? ` · ${result.result_path}` : ""}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown dashboard command error";
      setStatusMessage(message);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <Card pad={false}>
      <div className="px-5 py-4 hairline-b">
        <SectionTitle
          tick="green"
          hint="Paper and local maintenance gates exposed through the local dashboard server"
        >
          Command center
        </SectionTitle>
      </div>
      <div className="p-4 space-y-3">
        <label className="ds-input flex items-center gap-2 h-10 px-3">
          <span className="t-caption ink-subtle shrink-0">Reason</span>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="bg-transparent outline-none flex-1 t-body-md placeholder:text-[#9A988F]"
            placeholder="operator check"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          {actions.map(({ action, label, hint, icon: Icon, tone }) => (
            <button
              key={action}
              onClick={() => runCommand(action)}
              disabled={busyAction !== null}
              className={`flex items-center gap-3 px-3.5 py-3 text-left transition-colors ${
                busyAction === action ? "opacity-70" : "hover:bg-[var(--paper-3)]"
              }`}
              style={{
                borderRadius: "var(--r-md)",
                background: busyAction === action ? "var(--paper-3)" : "transparent",
                border: "1px solid rgba(10,10,10,.08)",
              }}
            >
              <span
                className="flex h-8 w-8 items-center justify-center shrink-0"
                style={{
                  borderRadius: 4,
                  background:
                    tone === "pink"
                      ? "rgba(255,45,122,.12)"
                      : tone === "orange"
                        ? "rgba(248,169,59,.16)"
                        : tone === "green"
                          ? "rgba(31,184,90,.12)"
                          : "rgba(26,200,232,.12)",
                  color:
                    tone === "pink"
                      ? "#C81E5C"
                      : tone === "orange"
                        ? "#A45A00"
                        : tone === "green"
                          ? "#0A6E3B"
                          : "#087A96",
                }}
              >
                <Icon size={15} strokeWidth={2.2} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="t-body-md block" style={{ fontWeight: 600 }}>
                  {label}
                </span>
                <span className="t-body-sm ink-subtle block mt-0.5">{hint}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="space-y-2 rounded-lg bg-[var(--paper-3)] p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="t-caption ink-subtle">Status</span>
            <span className="t-caption ink-subtle">
              {busyAction ? `Working on ${busyAction}` : "Idle"}
            </span>
          </div>
          <div className="t-body-sm ink leading-snug">{statusMessage}</div>
          {lastPlan && (
            <div className="space-y-1 pt-1">
              <div className="t-body-sm ink-subtle">
                Plan <span className="t-mono">{lastPlan.command_id}</span>
              </div>
              <div className="t-body-sm ink-subtle">
                Confirmation <span className="t-mono">{lastPlan.confirmation_phrase}</span>
              </div>
              {lastPlan.warnings.length > 0 && (
                <div className="t-body-sm ink-subtle">
                  Warnings: {lastPlan.warnings.join(" · ")}
                </div>
              )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <RuntimeMetric
              label="Kill switch"
              value={dashboardSummary.paperKillSwitchEnabled ? "Enabled" : "Clear"}
            />
            <RuntimeMetric
              label="Open orders"
              value={String(dashboardSummary.paperOpenOrderCount ?? 0)}
            />
            <RuntimeMetric
              label="Positions"
              value={String(dashboardSummary.paperPositionCount ?? 0)}
            />
            <RuntimeMetric
              label="Alerts"
              value={dashboardSummary.paperAlertStatus ?? "unknown"}
            />
            <RuntimeMetric
              label="Account sync"
              value={formatRuntimeTimestamp(dashboardSummary.paperAccountSnapshotAt)}
            />
            <RuntimeMetric
              label="Positions sync"
              value={formatRuntimeTimestamp(dashboardSummary.paperPositionsSnapshotAt)}
            />
          </div>
          {lastResult && (
            <div className="space-y-1 pt-1">
              <div className="t-body-sm ink-subtle">
                Result <span className="t-mono">{lastResult.command_id}</span> · {lastResult.status}
              </div>
              <div className="t-body-sm ink-subtle">{lastResult.message}</div>
              {lastResult.output_paths && lastResult.output_paths.length > 0 && (
                <div className="t-body-sm ink-subtle">
                  Outputs: {lastResult.output_paths.join(" · ")}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function RuntimeMetric({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="px-3 py-2"
      style={{
        background: "rgba(255,255,255,.62)",
        border: "1px solid rgba(10,10,10,.06)",
        borderRadius: "var(--r-sm)",
      }}
    >
      <div className="t-caption ink-subtle">{label}</div>
      <div className="t-body-sm ink mt-0.5" style={{ fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}

function formatRuntimeTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

/* ---------------- Events / News / Macro ---------------- */

export function Events() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="orange"
        greeting="Events · macro · news"
        headline="Signal"
        meta="Catalog-visible data comparisons, context packets and replayable feature files."
        stat={{ label: "Catalog events", value: String(events.length), delta: `${dashboardSummary.featurePacketCount} feature packets` }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-4"><KPI label="Data comparisons" value={String(dashboardSummary.dataComparisonCount)} accent="cyan" /></div>
        <div className="col-span-4"><KPI label="Context packets" value={String(dashboardSummary.contextCount)} accent="green" /></div>
        <div className="col-span-4"><KPI label="Feature packets" value={String(dashboardSummary.featurePacketCount)} accent="pink" /></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-8" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="orange">Event stream</SectionTitle>
          </div>
          <ul className="divider-soft">
            {events.length === 0 ? (
              <li className="px-5 py-8 t-body-sm ink-muted">
                No event, macro, news or replay feature artifacts are present.
              </li>
            ) : events.map((e, i) => (
              <li key={i} className="px-5 py-3 flex items-start gap-3">
                <span className="t-body-sm ink-subtle t-num w-12">{e.t}</span>
                <Tag color={e.kind === "Earnings" ? "pink" : e.kind === "Macro" ? "orange" : e.kind === "News" ? "cyan" : "paper"}>{e.kind}</Tag>
                <span className="t-body-sm flex-1">{e.title}</span>
                <span className="t-caption" style={{
                  color: e.impact === "high" ? "#C81E5C" : e.impact === "med" ? "#B8761B" : "#A09E97",
                }}>{e.impact}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="cyan">Factors derived</SectionTitle>
          </div>
          <div className="p-3 space-y-2">
            {strategies.flatMap((strategy) => strategy.factors).slice(0, 8).length === 0 ? (
              <div className="px-3.5 py-3 t-body-sm ink-muted" style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                No replayable feature factors are declared in the visible specs.
              </div>
            ) : strategies.flatMap((strategy) => strategy.factors).slice(0, 8).map((factor) => (
              <div key={factor} className="flex items-center justify-between px-3.5 py-2.5"
                style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                <span className="t-mono">{factor}</span>
                <Tag pill color="cyan">spec</Tag>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ---------------- LLM center ---------------- */

export function LLM() {
  const cols = [
    { title: "Review", subtitle: "Structured review cards", color: "green" as const, items: llmReviews },
    { title: "Scan", subtitle: "LLM-enabled StrategySpecs", color: "cyan" as const, items: strategies.filter((s) => s.llmReviewEnabled).map((strategy) => ({
      id: strategy.id,
      strat: strategy.name,
      verdict: "enabled",
      summary: strategy.llmReviewModel ?? "model pending",
      color: "cyan" as const,
    })) },
    { title: "Orchestrator", subtitle: "Not enabled in this catalog", color: "purple" as const, items: [] },
  ];
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="purple"
        greeting={`LLM workspace · ${dashboardSummary.reviewCount} cards`}
        headline="Reasoning"
        meta="Review and scan records are shown only when they exist in the dashboard catalog."
        stat={{ label: "LLM-enabled", value: String(strategies.filter((s) => s.llmReviewEnabled).length), delta: `${dashboardSummary.reviewCount} reviews` }}
      />
      <div className="grid grid-cols-3 gap-3">
        {cols.map((c) => (
          <Card key={c.title} pad={false}>
            <ColorBlock color={c.color} rounded="sm" halftone className="m-3 px-5 py-4 relative overflow-hidden">
              <div className="t-display-md" style={{ position: "relative", zIndex: 1 }}>{c.title}</div>
              <div className="t-body-sm mt-0.5" style={{ opacity: 0.85, position: "relative", zIndex: 1 }}>{c.subtitle}</div>
            </ColorBlock>
            <div className="px-3 pb-3 space-y-2">
              {c.items.length === 0 ? (
                <div className="p-3.5 t-body-sm ink-muted" style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                  No catalog records in this lane.
                </div>
              ) : c.items.map((r) => (
                <div key={r.id} className="p-3.5" style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                  <div className="flex items-center justify-between mb-1">
                    <Tag pill color={r.color}>{r.verdict}</Tag>
                    <span className="t-mono ink-subtle">{r.id}</span>
                  </div>
                  <div className="t-title-sm">{r.strat}</div>
                  <div className="t-body-sm ink-muted mt-1 leading-snug">{r.summary}</div>
                  <div className="flex items-center gap-2 mt-3">
                    <Pill variant="primary">Open card</Pill>
                    <Pill variant="secondary">Replay</Pill>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="purple">Prompt / model lineage</SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Session</th>
              <th className="text-left t-caption ink-subtle">Model</th>
              <th className="text-left t-caption ink-subtle">Template</th>
              <th className="text-left t-caption ink-subtle">Strategy version</th>
              <th className="text-left t-caption ink-subtle">Output</th>
              <th className="text-right pr-5 t-caption ink-subtle">Tokens</th>
            </tr>
          </thead>
          <tbody>
            {strategies.filter((strategy) => strategy.llmReviewEnabled).length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 t-body-sm ink-muted">
                  No LLM prompt lineage records are present.
                </td>
              </tr>
            ) : strategies.filter((strategy) => strategy.llmReviewEnabled).map((strategy) => (
              <tr key={strategy.id} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 t-mono">{strategy.id}</td>
                <td className="t-mono">{strategy.llmReviewModel ?? "pending"}</td>
                <td className="t-mono">review</td>
                <td className="t-title-sm">{strategy.name} {strategy.version}</td>
                <td><Tag color="paper">{strategy.llmReviewEnabled ? "enabled" : "disabled"}</Tag></td>
                <td className="text-right t-num pr-5">n/a</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ---------------- Strategy Groups ---------------- */

export function Groups() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="pink"
        greeting={`Strategy groups · ${strategyGroups.length} read-model groups`}
        headline="Compose"
        meta="Groups are generated from current catalog categories until orchestrator objects become write-managed."
        stat={{ label: "Strategies grouped", value: String(dashboardSummary.strategyCount), delta: `${dashboardSummary.activeStrategyCount} active` }}
      />
      <div className="grid grid-cols-3 gap-3">
      {strategyGroups.length === 0 ? (
        <Card>
          <div className="t-body-sm ink-muted">No strategy groups are present in the catalog.</div>
        </Card>
      ) : strategyGroups.map((g) => (
        <Card key={g.name} pad={false}>
          <ColorBlock color={g.color} rounded="sm" halftone className="m-3 px-5 py-5 relative overflow-hidden">
            <div className="t-caption" style={{ opacity: 0.78, position: "relative", zIndex: 1 }}>Strategy group</div>
            <div className="t-display-md mt-1" style={{ position: "relative", zIndex: 1 }}>{g.name}</div>
            <div className="mt-5 flex items-baseline gap-3" style={{ position: "relative", zIndex: 1 }}>
              <div className="t-display-xl t-num">{g.weight}%</div>
              <div className="t-body-sm" style={{ opacity: 0.82 }}>catalog share</div>
            </div>
          </ColorBlock>
          <div className="px-4 pb-4 space-y-2">
            <div className="flex items-center justify-between t-body-sm ink-muted">
              <span>Children · <span className="ink t-num">{g.children.length}</span></span>
              <Tag pill color={g.risk === "stable" ? "green" : g.risk === "moderate" ? "orange" : "pink"}>{g.risk}</Tag>
            </div>
            {g.children.map((c) => (
              <div key={c} className="flex items-center gap-2 px-3.5 py-2.5"
                style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                <Layers size={13} className="ink-subtle" />
                <span className="t-body-md flex-1 truncate">{c}</span>
                <ArrowUpRight size={13} className="ink-subtle" />
              </div>
            ))}
            <button
              className="w-full mt-1 t-body-sm ink-muted py-2.5 opacity-60"
              style={{ borderRadius: "var(--r-md)", border: "1px dashed rgba(10,10,10,.18)" }}
              disabled
              title="Group write controls are intentionally not exposed in the read-only dashboard."
            >
              read-only group
            </button>
          </div>
        </Card>
      ))}
      </div>
    </div>
  );
}

/* ---------------- Audit ---------------- */

export function Audit() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting={`Activity ledger · ${dashboardSummary.auditCount} events`}
        headline="Audit"
        meta="Catalog audit events are rebuilt from journals, paper orders and safety controls."
        stat={{ label: "Events", value: String(dashboardSummary.auditCount), delta: dashboardSummary.paperReconciliationStatus }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Audit events" value={String(dashboardSummary.auditCount)} accent="black" /></div>
        <div className="col-span-3"><KPI label="Journal entries" value={String(dashboardSummary.journalCount)} accent="green" /></div>
        <div className="col-span-3"><KPI label="Paper orders" value={String(paperOrders.length)} accent="pink" /></div>
        <div className="col-span-3"><KPI label="LLM reviews" value={String(dashboardSummary.reviewCount)} accent="cyan" /></div>
      </div>
      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="ink">Activity log</SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Time</th>
              <th className="text-left t-caption ink-subtle">Actor</th>
              <th className="text-left t-caption ink-subtle">Action</th>
              <th className="text-left t-caption ink-subtle">Target</th>
              <th className="text-right pr-5 t-caption ink-subtle">Replay</th>
            </tr>
          </thead>
          <tbody>
            {auditLog.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-8 t-body-sm ink-muted">
                  No audit events are present. Journals and paper orders will appear here after they are written.
                </td>
              </tr>
            ) : auditLog.map((a, i) => (
              <tr key={i} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 t-num ink-muted">{a.t}</td>
                <td><Tag color={a.who === "user" ? "paper" : a.who === "codex" ? "cyan" : a.who === "llm" ? "purple" : "orange"}>{a.who}</Tag></td>
                <td>{a.action}</td>
                <td className="t-title-sm">{a.target}</td>
                <td className="pr-5 text-right">
                  <button className="t-body-sm ink-muted hover:ink">view →</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function money(value: number) {
  return value === 0
    ? "$0.00"
    : value.toLocaleString([], { style: "currency", currency: "USD" });
}
