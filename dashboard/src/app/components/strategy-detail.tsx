import { useState } from "react";
import {
  GitBranch, Play, Pause, FlaskConical, Eye, ShieldCheck, Sparkles, RefreshCw,
  TrendingUp, Plus,
} from "lucide-react";
import { Card, Tag, Pill, KPI, SectionTitle } from "./blocks";
import { CommandResultDetails } from "./command-details";
import { Sparkline } from "./sparkline";
import { applyDashboardCatalog, auditLog, llmReviews, recentSignals, strategies, versions } from "./data";
import {
  getDashboardJson,
  postDashboardJson,
  promptDashboardConfirmations,
  resolveDashboardCommandRun,
} from "./runtime";
import type { DashboardCommandPlanResponse, DashboardCommandRunResponse } from "./runtime";

type Tab = "spec" | "backtest" | "signals" | "versions" | "llm" | "audit";
type StrategyDataSource = "keep" | "sample" | "alpaca" | "longbridge";

const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: "spec",     label: "Spec",     icon: FlaskConical },
  { key: "backtest", label: "Backtest", icon: TrendingUp },
  { key: "signals",  label: "Signals",  icon: Eye },
  { key: "versions", label: "Versions", icon: GitBranch },
  { key: "llm",      label: "LLM",      icon: Sparkles },
  { key: "audit",    label: "Audit",    icon: ShieldCheck },
];

export function StrategyDetail({ id }: { id: string }) {
  const s = strategies.find((x) => x.id === id) ?? strategies[0];
  const [tab, setTab] = useState<Tab>("spec");
  const [reason, setReason] = useState("operator check");
  const [dataSource, setDataSource] = useState<StrategyDataSource>(
    s.dataSource === "sample" ? "alpaca" : (s.dataSource as "keep" | "sample" | "alpaca" | "longbridge"),
  );
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Dashboard command API is local-only and confirmed.");
  const [lastPlan, setLastPlan] = useState<DashboardCommandPlanResponse | null>(null);
  const [lastResult, setLastResult] = useState<DashboardCommandRunResponse | null>(null);
  const positive = s.lastReturn >= 0;
  const accent = positive ? "#16C268" : "#FF2D7A";

  const refreshCatalog = async () => {
    const runtimeCatalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
      "/api/dashboard/catalog",
    );
    applyDashboardCatalog(runtimeCatalog as Parameters<typeof applyDashboardCatalog>[0]);
  };

  const lifecycleActions = [
    {
      action: "strategy.approve",
      label: "Approve",
      hint: "Promote draft to approved",
      icon: ShieldCheck,
      tone: "cyan" as const,
    },
    {
      action: "strategy.validate",
      label: "Validate",
      hint: "Write spec validation report",
      icon: FlaskConical,
      tone: "cyan" as const,
    },
    {
      action: "strategy.capabilities.refresh",
      label: "Capabilities",
      hint: "Refresh backend capability report",
      icon: RefreshCw,
      tone: "cyan" as const,
    },
    {
      action: "strategy.workflow.verify",
      label: "Verify workflow",
      hint: "Run validation, reports, backtest, scan",
      icon: Play,
      tone: "green" as const,
    },
    {
      action: "strategy.activate.manual",
      label: "Activate manual",
      hint: "Keep manual signal mode",
      icon: Play,
      tone: "green" as const,
    },
    {
      action: "strategy.activate.paper_auto",
      label: "Activate paper",
      hint: "Switch to Alpaca paper",
      icon: Sparkles,
      tone: "green" as const,
    },
    {
      action: "strategy.disable",
      label: "Disable",
      hint: "Retire the strategy",
      icon: Pause,
      tone: "pink" as const,
    },
  ];

  const parseSuggestedStrategyAction = (suggestion: string): {
    action: string;
    dataSource?: StrategyDataSource;
    label: string;
  } | null => {
    const trimmed = suggestion.trim();
    if (trimmed.includes("uv run oc deploy prepare")) {
      return { action: "system.prepare_workspace", label: "Prepare workspace" };
    }
    if (trimmed.includes("uv run oc readiness") || trimmed.includes("uv run oc doctor")) {
      return { action: "system.readiness.refresh", label: "Refresh readiness" };
    }
    if (trimmed.includes("uv run oc paper sync-account")) {
      return { action: "paper.sync.account", label: "Sync account" };
    }
    if (trimmed.includes("uv run oc paper sync")) {
      return { action: "paper.sync.orders", label: "Sync orders" };
    }
    if (trimmed.includes("uv run oc spec validate")) {
      return { action: "strategy.validate", label: "Validate" };
    }
    if (trimmed.includes("uv run oc spec capabilities")) {
      return { action: "strategy.capabilities.refresh", label: "Capabilities" };
    }
    if (trimmed.startsWith("uv run oc strategy approve ")) {
      return { action: "strategy.approve", label: "Apply" };
    }
    if (trimmed.startsWith("uv run oc strategy activate ")) {
      if (trimmed.includes("--paper-auto")) {
        const dataSourceMatch = trimmed.match(/--data-source\s+([^\s]+)/);
        const parsedDataSource = dataSourceMatch?.[1];
        const resolvedDataSource: StrategyDataSource =
          parsedDataSource === "sample" ||
          parsedDataSource === "alpaca" ||
          parsedDataSource === "longbridge"
            ? parsedDataSource
            : "keep";
        return {
          action: "strategy.activate.paper_auto",
          dataSource: resolvedDataSource,
          label: "Activate paper",
        };
      }
      return { action: "strategy.activate.manual", label: "Activate manual" };
    }
    return null;
  };

  const runLifecycleCommand = async (action: string, overrideDataSource?: StrategyDataSource) => {
    setBusyAction(action);
    setStatusMessage("Creating dashboard command plan…");
    setLastPlan(null);
    setLastResult(null);
    const commandDataSource = overrideDataSource ?? dataSource;
    try {
      const plan = await postDashboardJson<DashboardCommandPlanResponse>("/api/dashboard/command-plan", {
        action,
        reason,
        requested_by: "dashboard",
        strategy_path: s.sourcePath,
        data_source: commandDataSource,
      });
      setLastPlan(plan);
      if (!plan.plan_path) {
        throw new Error("dashboard command plan missing plan_path");
      }
      const confirmations = await promptDashboardConfirmations(
        plan,
        "Type the exact confirmation phrase to execute this dashboard command.",
      );
      if (confirmations === null) {
        setStatusMessage("Command plan created. Execution cancelled before confirmation.");
        return;
      }
      setStatusMessage(plan.remote ? "Queueing remote command job…" : "Executing dashboard command…");
      const queued = await postDashboardJson<DashboardCommandRunResponse>("/api/dashboard/command-run", {
        plan_path: plan.plan_path,
        ...confirmations,
        executed_by: "dashboard",
      });
      const result = await resolveDashboardCommandRun(queued, (job) => {
        setStatusMessage(`${job.status}: ${job.message}`);
      });
      setLastResult(result);
      await refreshCatalog();
      setStatusMessage(
        `${result.message}${result.result_path ? ` · ${result.result_path}` : ""}${
          result.backup_manifest_path ? ` · ${result.backup_manifest_path}` : ""
        }`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown dashboard command error";
      setStatusMessage(message);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="px-6 pb-8 space-y-3">
      {/* Detail header — strategy hero */}
      <div
        className="dscard relative overflow-hidden"
        style={{ borderRadius: "var(--r-2xl)", padding: "22px 26px" }}
      >
        {/* composer-style multi-tile color signature in corner */}
        <div
          aria-hidden
          className="absolute blend-multiply tile-halftone"
          style={{ top: 0, right: 0, width: 240, height: 56, background: accent }}
        />
        <div
          aria-hidden
          className="absolute blend-multiply"
          style={{ top: 56, right: 96, width: 56, height: 32, background: "#0A0A0A" }}
        />
        <div
          aria-hidden
          className="absolute blend-multiply"
          style={{ top: 56, right: 152, width: 32, height: 16, background: accent, opacity: 0.55 }}
        />
        <div className="relative flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2 t-caption ink-subtle">
              <span>STRATEGY</span>
              <span>·</span>
              <span className="t-mono">{s.symbol}</span>
              <span>·</span>
              <span className="t-mono">{s.version}</span>
            </div>
            <h1 className="t-display-lg mt-2 grad-ink-green">{s.name}</h1>
            <div className="flex items-center gap-2 mt-3">
              <Tag color={s.status === "active" ? "green" : "paper"}>{s.status}</Tag>
              <Tag color="cyan">{s.modelClass.replace("-", " ")}</Tag>
              <Tag color={s.risk === "stable" ? "green" : s.risk === "moderate" ? "orange" : "pink"}>{s.risk}</Tag>
              <span className="t-body-sm ink-subtle ml-1">in {s.group}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Pill variant="secondary"><Pause size={12} /> Read-only</Pill>
            <Pill variant="primary"><Play size={12} fill="white" /> CLI gated</Pill>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-1">
        {TABS.map(({ key, label, icon: Icon }) => {
          const isActive = key === tab;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`pill ${isActive ? "pill-primary" : "pill-ghost"}`}
            >
              <Icon size={13} /> {label}
            </button>
          );
        })}
      </div>

      {tab === "spec" && <SpecCanvas s={s} accent={accent} />}
      {tab === "backtest" && (
        <BacktestPanel
          s={s}
          accent={accent}
          onRerun={runLifecycleCommand}
          busyAction={busyAction}
        />
      )}
      {tab === "signals" && (
        <SignalsPanel s={s} onRerun={runLifecycleCommand} busyAction={busyAction} />
      )}
      {tab === "versions" && <VersionsMini s={s} />}
      {tab === "llm" && <LLMPanel s={s} />}
      {tab === "audit" && <AuditMini s={s} />}
    </div>
  );
}

/* ---------------- Spec — halftone workspace canvas ---------------- */

function SpecCanvas({ s, accent }: { s: any; accent: string }) {
  const factorTitle = s.factors.length > 0 ? s.factors.slice(0, 3).join(", ") : "No custom factors";
  const capabilityTitle =
    s.requiredCapabilities.length > 0
      ? s.requiredCapabilities.slice(0, 3).join(", ")
      : "No required capabilities";
  const backendReasons = s.backendReasons ?? [];
  const compatibilityReasonEntries = Object.entries(s.compatibilityReasons ?? {}).filter(
    ([, reasons]) => Array.isArray(reasons) && reasons.length > 0,
  );
  const reasonCount =
    backendReasons.length +
    compatibilityReasonEntries.reduce((count, [, reasons]) => count + reasons.length, 0);

  return (
    <div className="grid grid-cols-12 gap-3">
      {/* The canvas itself — halftone background, the "engineering file" */}
      <div className="col-span-8">
        <Card pad={false}>
          <div className="px-5 py-3 hairline-b flex items-center justify-between">
            <SectionTitle hint="StrategySpec · YAML-backed workspace">Editor canvas</SectionTitle>
            <div className="flex items-center gap-1.5">
              <Pill variant="ghost">YAML</Pill>
              <Pill variant="ghost">Visual</Pill>
            </div>
          </div>
          <div
            className="relative halftone bg-paper-3 overflow-hidden"
            style={{ height: 460 }}
          >
            {/* subtle grid hint */}
            <div
              aria-hidden
              className="absolute inset-0 pointer-events-none"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(0,0,0,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,.04) 1px, transparent 1px)",
                backgroundSize: "48px 48px",
                backgroundPosition: "-1px -1px",
              }}
            />

            {/* Node: Universe */}
            <SpecNode
              x={48} y={48} w={220}
              kind="UNIVERSE" title={s.symbol} subtitle={`${s.timeframe} · ${s.dataSource}`} tone="ink"
            />
            {/* Connector */}
            <Connector x1={158} y1={104} x2={158} y2={150} />

            {/* Node: Filter */}
            <SpecNode
              x={48} y={150} w={220}
              kind="DATA" title={s.dataSource} subtitle={s.sourcePath || "StrategySpec source path"} tone="cyan"
            />
            <Connector x1={158} y1={206} x2={158} y2={252} />

            {/* Node: Entry */}
            <SpecNode
              x={48} y={252} w={220}
              kind="FACTORS" title={factorTitle} subtitle={`${s.factors.length} declared factors`} tone="green"
            />
            <Connector x1={268} y1={290} x2={420} y2={290} />

            {/* Node: Sizing */}
            <SpecNode
              x={420} y={252} w={220}
              kind="CAPABILITIES" title={capabilityTitle} subtitle={`${s.requiredCapabilities.length} required`} tone="orange"
            />
            <Connector x1={530} y1={308} x2={530} y2={360} />

            {/* Node: Exit */}
            <SpecNode
              x={420} y={360} w={220}
              kind="EXECUTION" title={s.executionMode} subtitle={`${s.backend} · ${s.backendStatus}`} tone="pink"
            />

            {/* Drifting "+" placeholder */}
            <button
              className="absolute flex items-center gap-1 px-3 h-8 rounded-full t-body-sm ink-muted bg-white/70 hover:bg-white"
              style={{ left: 700, top: 380, boxShadow: "var(--e1)", border: "1px dashed rgba(10,10,10,.18)" }}
              disabled
              title="Dashboard writes are not exposed in read-only mode."
            >
              <Plus size={12} /> read only
            </button>
          </div>
        </Card>
      </div>

      {/* Side panel — stats + spec metadata */}
      <div className="col-span-4 space-y-3">
        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Live metrics</SectionTitle>
          </div>
          <div className="p-3 grid grid-cols-2 gap-2">
            <KPI label="Sharpe" value={String(s.sharpe)} accent="black" />
            <KPI label="30d return" value={`${s.lastReturn > 0 ? "+" : ""}${s.lastReturn}%`} accent={s.lastReturn >= 0 ? "green" : "pink"} />
          </div>
          <div className="px-5 pb-4 pt-1">
            <Sparkline data={s.series} color={accent} width={340} height={64} />
          </div>
        </Card>

        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Compatibility</SectionTitle>
          </div>
          <div className="p-3 space-y-1.5">
            <CompatRow label="Pine export" ok={s.pine} note="full subset" />
            <CompatRow label="Python engine" ok={s.python} note="primary runtime" />
            <CompatRow label="Alpaca paper" ok={s.alpaca} note="paper_auto eligible" />
            <CompatRow label="Backend plan" ok={s.backendStatus === "supported"} note={s.backendStatus} />
          </div>
          {(backendReasons.length > 0 || compatibilityReasonEntries.length > 0) && (
            <div className="px-3 pb-3 pt-1 space-y-2">
              <div className="flex items-center justify-between gap-2 px-1">
                <span className="t-caption ink-subtle">Reason chain</span>
                <span className="t-caption ink-muted">{reasonCount} notes</span>
              </div>
              <ReasonStack title="Backend plan" status={s.backendStatus} reasons={backendReasons} />
              {compatibilityReasonEntries.map(([capability, reasons]) => (
                <ReasonStack
                  key={capability}
                  title={capability}
                  status={s.compatibility[capability] ?? "partial"}
                  reasons={reasons}
                />
              ))}
            </div>
          )}
        </Card>

        {s.paperReadiness && (
          <Card pad={false}>
            <div className="px-5 py-3 hairline-b flex items-center justify-between">
              <SectionTitle>Paper Readiness</SectionTitle>
              <Tag color={s.paperReadiness.status === "ok" ? "green" : s.paperReadiness.status === "warning" ? "orange" : "pink"}>
                {s.paperReadiness.status}
              </Tag>
            </div>
            <div className="p-4 space-y-2">
              <div className="t-caption ink-subtle t-mono truncate">
                {s.paperReadiness.path}
              </div>
              {s.paperReadiness.checks.slice(0, 5).map((check) => (
                <div key={check.name} className="flex items-start gap-3 t-body-sm">
                  <Tag color={check.status === "ok" ? "green" : check.status === "warning" ? "orange" : "pink"}>
                    {check.status}
                  </Tag>
                  <div className="min-w-0">
                    <div className="t-title-sm">{check.name}</div>
                    <div className="ink-muted leading-snug">{check.message}</div>
                    {check.suggestedActions.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {check.suggestedActions.map((suggestion) => {
                          const mapped = parseSuggestedStrategyAction(suggestion);
                          return (
                            <div key={suggestion} className="flex items-center gap-2">
                              <div className="t-caption t-mono ink-subtle truncate flex-1">
                                {suggestion}
                              </div>
                              {mapped && (
                                <button
                                  type="button"
                                  onClick={() => runLifecycleCommand(mapped.action, mapped.dataSource)}
                                  className="t-caption px-2 py-1 rounded-md border border-[rgba(10,10,10,.12)] bg-white hover:bg-[var(--paper-3)]"
                                >
                                  {mapped.label}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card pad={false}>
          <div className="px-5 py-3 hairline-b flex items-center justify-between">
            <SectionTitle>Lifecycle</SectionTitle>
            <Tag color={s.status === "active" ? "green" : s.status === "approved" ? "cyan" : "paper"}>
              {s.status}
            </Tag>
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
            <label className="ds-input flex items-center gap-2 h-10 px-3">
              <span className="t-caption ink-subtle shrink-0">Data source</span>
              <select
                value={dataSource}
                onChange={(event) =>
                  setDataSource(event.target.value as "keep" | "sample" | "alpaca" | "longbridge")
                }
                className="bg-transparent outline-none flex-1 t-body-md"
              >
                <option value="keep">keep current</option>
                <option value="sample">sample</option>
                <option value="alpaca">alpaca</option>
                <option value="longbridge">longbridge</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {lifecycleActions.map(({ action, label, hint, icon: Icon, tone }) => (
                <button
                  key={action}
                  onClick={() => runLifecycleCommand(action)}
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
                          : tone === "green"
                            ? "rgba(31,184,90,.12)"
                            : "rgba(26,200,232,.12)",
                      color:
                        tone === "pink"
                          ? "#C81E5C"
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
                  {(lastPlan.warnings ?? []).length > 0 && (
                    <div className="t-body-sm ink-subtle">
                      Warnings: {(lastPlan.warnings ?? []).join(" · ")}
                    </div>
                  )}
                  {lastPlan.remote && (
                    <div className="t-body-sm ink-subtle">
                      Remote {lastPlan.remote.risk_level}
                      {lastPlan.remote.backup_required ? " · backup required" : ""}
                    </div>
                  )}
                </div>
              )}
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
                  {lastResult.backup_manifest_path && (
                    <div className="t-body-sm ink-subtle">
                      Backup: {lastResult.backup_manifest_path}
                    </div>
                  )}
                </div>
              )}
              <CommandResultDetails plan={lastPlan} result={lastResult} />
            </div>
          </div>
        </Card>

        {s.customDataBindings.length > 0 && (
          <Card pad={false}>
            <div className="px-5 py-3 hairline-b">
              <SectionTitle>Nautilus replay</SectionTitle>
            </div>
            <div className="p-3 space-y-2">
              {s.customDataBindings.map((binding: any) => (
                <div
                  key={`${binding.factorName}-${binding.path}`}
                  className="p-3"
                  style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="t-title-sm truncate">{binding.factorName}</div>
                      <div className="t-caption ink-subtle truncate">
                        {binding.source} · {binding.field} · {binding.recordCount} rows
                      </div>
                    </div>
                    <Tag color={replayStatusColor(binding.pointInTimeStatus)}>
                      {binding.pointInTimeStatus}
                    </Tag>
                  </div>
                  <div className="t-caption ink-subtle mt-2 truncate">
                    {binding.path}
                  </div>
                  <div className="t-caption ink-subtle mt-1">
                    {binding.firstTimestamp || "n/a"} → {binding.lastTimestamp || "n/a"}
                  </div>
                  {binding.replayWarnings.length > 0 && (
                    <div className="t-body-sm ink-muted mt-2 leading-snug">
                      {binding.replayWarnings.slice(0, 2).join(" · ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Provenance</SectionTitle>
          </div>
          <div className="p-4 t-body-sm space-y-1.5">
            <ProvRow k="Source" v={s.sourcePath || "unknown"} mono />
            <ProvRow k="Version" v={s.version} mono />
            <ProvRow k="Hash" v={s.specHash || "unknown"} mono />
            <ProvRow k="Backend plan" v={s.backendPlanPath || "n/a"} mono />
            <ProvRow k="Paper readiness" v={s.paperReadinessReportPath || "n/a"} mono />
            <ProvRow k="Broker" v={s.broker} />
            <ProvRow k="Data" v={s.dataSource} />
          </div>
        </Card>
      </div>
    </div>
  );
}

function SpecNode({
  x, y, w, kind, title, subtitle, tone,
}: {
  x: number; y: number; w: number; kind: string; title: string; subtitle: string;
  tone: "ink" | "green" | "pink" | "cyan" | "orange";
}) {
  const tones: Record<string, { bg: string; bar: string; ink: string }> = {
    ink:    { bg: "#FFFFFF", bar: "#0A0A0A", ink: "#0A0A0A" },
    green:  { bg: "#FFFFFF", bar: "#16C268", ink: "#0A0A0A" },
    pink:   { bg: "#FFFFFF", bar: "#FF2D7A", ink: "#0A0A0A" },
    cyan:   { bg: "#FFFFFF", bar: "#21CFEF", ink: "#0A0A0A" },
    orange: { bg: "#FFFFFF", bar: "#F8A93B", ink: "#0A0A0A" },
  };
  const t = tones[tone];
  return (
    <div
      className="absolute"
      style={{
        left: x, top: y, width: w,
        background: t.bg,
        borderRadius: "var(--r-md)",
        boxShadow: "var(--e2)",
        border: "1px solid rgba(10,10,10,.06)",
        overflow: "hidden",
      }}
    >
      <div className="flex items-center gap-2 px-3 py-1.5" style={{ borderBottom: "1px solid rgba(10,10,10,.06)" }}>
        <span style={{ width: 6, height: 6, background: t.bar, borderRadius: 2, display: "inline-block" }} />
        <span className="t-caption" style={{ color: "#6B6B68" }}>{kind}</span>
      </div>
      <div className="px-3 py-2.5">
        <div className="t-title-sm" style={{ color: t.ink }}>{title}</div>
        <div className="t-body-sm ink-subtle mt-0.5">{subtitle}</div>
      </div>
    </div>
  );
}

function Connector({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const isHorizontal = y1 === y2;
  const left = Math.min(x1, x2) - 4;
  const top = Math.min(y1, y2) - 4;
  const width = isHorizontal ? Math.abs(x2 - x1) + 8 : 8;
  const height = isHorizontal ? 8 : Math.abs(y2 - y1) + 8;
  return (
    <svg
      className="absolute pointer-events-none"
      style={{ left, top, width, height }}
      viewBox={`0 0 ${width} ${height}`}
    >
      {isHorizontal ? (
        <line x1={4} y1={4} x2={width - 4} y2={4} stroke="#0A0A0A" strokeWidth="1.5" strokeDasharray="3 3" />
      ) : (
        <line x1={4} y1={4} x2={4} y2={height - 4} stroke="#0A0A0A" strokeWidth="1.5" strokeDasharray="3 3" />
      )}
      <circle cx={isHorizontal ? width - 4 : 4} cy={isHorizontal ? 4 : height - 4} r="2" fill="#0A0A0A" />
    </svg>
  );
}

function CompatRow({ label, ok, note }: { label: string; ok: boolean; note: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: ok ? "var(--paper-3)" : "transparent" }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: ok ? "#16C268" : "rgba(10,10,10,.18)" }} />
      <span className="t-body-md flex-1">{label}</span>
      <span className="t-body-sm ink-subtle">{note}</span>
    </div>
  );
}

function replayStatusColor(status: string) {
  if (status === "complete") {
    return "green";
  }
  if (status === "partial") {
    return "orange";
  }
  return "pink";
}

function ReasonStack({
  title,
  status,
  reasons,
}: {
  title: string;
  status: "supported" | "partial" | "blocked" | "unsupported" | string;
  reasons: string[];
}) {
  if (reasons.length === 0) {
    return null;
  }
  const tone: "green" | "orange" | "pink" | "paper" =
    status === "supported" ? "green"
      : status === "partial" ? "orange"
      : status === "blocked" ? "pink"
      : "paper";

  return (
    <div className="rounded-lg border border-[rgba(10,10,10,.08)] bg-white px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="t-title-sm">{title}</span>
        <Tag color={tone}>{status}</Tag>
      </div>
      <ul className="mt-2 space-y-1">
        {reasons.map((reason, index) => (
          <li key={`${title}-${index}`} className="t-body-sm ink-subtle leading-5">
            - {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProvRow({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="ink-subtle">{k}</span>
      <span className={mono ? "t-mono" : "ink"}>{v}</span>
    </div>
  );
}

/* ---------------- Other tabs (light placeholders) ---------------- */

function BacktestPanel({
  s,
  accent,
  onRerun,
  busyAction,
}: {
  s: any;
  accent: string;
  onRerun: (action: string) => void;
  busyAction: string | null;
}) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card variant="dark" pad={false} className="col-span-8">
        <div className="px-5 pt-4 pb-3 flex items-end justify-between gap-4">
          <div>
            <div className="t-caption" style={{ color: "rgba(242,242,240,.55)" }}>Equity curve · latest catalog run</div>
            <div className="t-display-xl mt-1.5 t-num">{s.lastReturn >= 0 ? "+" : ""}{s.lastReturn}%</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onRerun("strategy.backtest.rerun")}
              disabled={busyAction !== null}
              className="flex items-center gap-2 px-3 h-8 rounded-full t-body-sm text-white transition-colors hover:bg-white/10 disabled:opacity-60"
              style={{ border: "1px solid rgba(255,255,255,.15)" }}
            >
              <RefreshCw size={13} />
              Rerun backtest
            </button>
            <div className="flex items-center gap-0.5 p-1 rounded-full bg-white/5">
              {["1M", "3M", "1Y", "3Y", "5Y", "All"].map((p, i) => (
                <button
                  key={p}
                  className={`px-2.5 h-7 inline-flex items-center t-body-sm rounded-full transition-colors ${
                    i === 4 ? "bg-white text-[#0A0A0A]" : "text-white/65 hover:text-white"
                  }`}
                  style={{ fontWeight: 600 }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="px-5 pb-5">
          <Sparkline
            data={s.series}
            color={accent}
            width={760}
            height={240}
            area
            strokeWidth={1.8}
          />
        </div>
        {/* benchmark legend */}
        <div className="px-5 pb-5 flex items-center gap-4 t-body-sm" style={{ color: "rgba(242,242,240,.7)" }}>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: accent, borderRadius: 1 }} /> Strategy
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: "rgba(242,242,240,.45)", borderRadius: 1 }} /> SPY benchmark
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: "#1AC8E8", borderRadius: 1 }} /> Risk-free
          </span>
        </div>
      </Card>
      <Card pad={false} className="col-span-4">
        <div className="px-5 py-3 hairline-b">
          <SectionTitle tick="green">Performance</SectionTitle>
        </div>
        <div className="p-3 grid grid-cols-2 gap-1.5">
          {[
            ["Cumulative", `${s.lastReturn >= 0 ? "+" : ""}${s.lastReturn}%`, "green"],
            ["Annualized", "catalog",  "green"],
            ["Sharpe",     String(s.sharpe), null],
            ["Risk",       s.risk,   "pink"],
            ["Backend",    s.backendStatus,   null],
            ["Trades",     String(s.trades), null],
          ].map(([k, v, accent]) => (
            <div
              key={k as string}
              className="px-3.5 py-2.5"
              style={{ background: "var(--paper-3)", borderRadius: "var(--r-sm)" }}
            >
              <div className="t-caption ink-subtle">{k}</div>
              <div
                className="t-title-md t-num mt-1"
                style={{
                  color: accent === "green" ? "#0A6E3B" : accent === "pink" ? "#C81E5C" : "var(--ink)",
                  fontWeight: 700,
                }}
              >{v}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SignalsPanel({
  s,
  onRerun,
  busyAction,
}: {
  s: any;
  onRerun: (action: string) => void;
  busyAction: string | null;
}) {
  const rows = recentSignals.filter((signal) => signal.symbol === s.symbol || signal.strat === s.name);
  return (
    <Card pad={false}>
      <div className="px-5 py-3 hairline-b flex items-center justify-between gap-3">
        <SectionTitle>Signal log</SectionTitle>
        <button
          type="button"
          onClick={() => onRerun("strategy.scan.rerun")}
          disabled={busyAction !== null}
          className="flex items-center gap-2 px-3 h-8 rounded-full t-body-sm transition-colors hover:bg-[var(--paper-3)] disabled:opacity-60"
          style={{ border: "1px solid rgba(10,10,10,.1)" }}
        >
          <RefreshCw size={13} />
          Rerun scan
        </button>
      </div>
      {rows.length === 0 ? (
        <div className="p-5 t-body-md ink-muted">No signal log entries are linked to this strategy.</div>
      ) : (
        <table className="w-full t-body-sm">
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 t-mono ink-muted">{row.t}</td>
                <td>{row.side}</td>
                <td>{row.symbol}</td>
                <td className="text-right pr-5 t-num">{row.px.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
function VersionsMini({ s }: { s: any }) {
  const rows = versions.filter((version) => version.strat === s.name || s.version === version.id);
  return (
    <Card>
      {rows.length === 0 ? (
        <div className="t-body-md ink-muted">No version rows are linked to this strategy.</div>
      ) : rows.map((version) => (
        <div key={version.id} className="flex items-center gap-3 py-2 hairline-b last:border-b-0">
          <GitBranch size={14} className="ink-subtle" />
          <span className="t-mono">{version.id}</span>
          <span className="t-title-sm">{version.strat}</span>
          <span className="ml-auto t-mono ink-muted">{version.hash}</span>
        </div>
      ))}
    </Card>
  );
}
function LLMPanel({ s }: { s: any }) {
  const rows = llmReviews.filter((review) => review.strat === s.name);
  return (
    <Card>
      {rows.length === 0 ? (
        <div className="t-body-md ink-muted">
          {s.llmReviewEnabled ? "LLM review is enabled, but no review cards are present." : "LLM review is disabled for this strategy."}
        </div>
      ) : rows.map((review) => (
        <div key={review.id} className="py-2 hairline-b last:border-b-0">
          <Tag pill color={review.color}>{review.verdict}</Tag>
          <div className="t-title-sm mt-2">{review.strat}</div>
          <div className="t-body-sm ink-muted mt-1">{review.summary}</div>
        </div>
      ))}
    </Card>
  );
}
function AuditMini({ s }: { s: any }) {
  const rows = auditLog.filter((audit) => audit.target.includes(s.id) || audit.target.includes(s.name));
  return (
    <Card>
      {rows.length === 0 ? (
        <div className="t-body-md ink-muted">No audit events are linked to this strategy.</div>
      ) : rows.map((audit) => (
        <div key={`${audit.t}-${audit.action}`} className="flex items-center gap-3 py-2 hairline-b last:border-b-0">
          <span className="t-mono ink-muted">{audit.t}</span>
          <Tag color={audit.who === "user" ? "paper" : "orange"}>{audit.who}</Tag>
          <span>{audit.action}</span>
        </div>
      ))}
    </Card>
  );
}
