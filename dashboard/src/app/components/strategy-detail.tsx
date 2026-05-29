import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Bot,
  Check,
  CircleStop,
  Pencil,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { applyDashboardCatalog, strategies } from "./data";
import { dashboardApiToken, getDashboardJson, postDashboardJson } from "./runtime";
import { EquityCurve } from "./charts/equity-curve";
import { DrawdownChart } from "./charts/drawdown";
import { SignalLogChart } from "./charts/signal-log";
import { FactorICChart } from "./charts/factor-ic";

type Tab =
  | "overview"
  | "conversation"
  | "spec"
  | "runs"
  | "promotion"
  | "paper"
  | "llm"
  | "trace";

type StrategyDetailPayload = {
  strategy: Record<string, any>;
  project_id: string;
  project: Record<string, any> | null;
  queue: QueueRow[];
  trace: TraceRow[];
  runs: Array<Record<string, any>>;
  signals: SignalRow[];
  paper_readiness: Array<Record<string, any>>;
  research_reports: Array<Record<string, any>>;
  spec: SpecPayload;
  equity: { points: Array<{ ts: string; value: number; benchmark?: number }> };
  drawdown: { points: Array<{ ts: string; value: number }> };
  llm_factors: Array<Record<string, any>>;
  pass_reasons: Record<string, string[]>;
};

type QueueRow = {
  id: string;
  ts: string;
  kind: string;
  body: string;
  consumed_at?: string | null;
  metadata?: Record<string, any>;
};

type TraceRow = {
  ts: string;
  span_id: string;
  agent: string;
  operation: string;
  queue_command_id?: string | null;
  metadata?: Record<string, any>;
};

type SignalRow = {
  id?: string;
  signal_id?: string;
  timestamp: string;
  price: number;
  side: string;
  action?: string;
};

type SpecPayload = {
  strategy_name: string;
  active_path: string;
  active_hash: string;
  active_text: string;
  draft_path: string | null;
  draft_hash: string | null;
  draft_text: string;
  has_pending_draft: boolean;
};

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "conversation", label: "Conversation" },
  { key: "spec", label: "Spec" },
  { key: "runs", label: "Runs" },
  { key: "promotion", label: "Promotion" },
  { key: "paper", label: "Paper" },
  { key: "llm", label: "LLM Factors" },
  { key: "trace", label: "Trace" },
];

export function StrategyDetail({ id }: { id: string }) {
  const fallback = strategies.find((item) => item.id === id) ?? strategies[0];
  const [data, setData] = useState<StrategyDetailPayload | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [status, setStatus] = useState("Loading strategy workspace.");
  const [busy, setBusy] = useState<string | null>(null);

  const strategyId = data?.strategy?.strategy_id ?? fallback?.id ?? id;
  const name = data?.strategy?.strategy_name ?? fallback?.name ?? id;

  const refresh = async () => {
    setStatus("Refreshing strategy workspace.");
    const payload = await getDashboardJson<StrategyDetailPayload>(`/api/strategies/${strategyId}`);
    setData(payload);
    setStatus("Strategy workspace loaded.");
  };

  useEffect(() => {
    void refresh().catch((error) => {
      setStatus(error instanceof Error ? error.message : "Strategy workspace failed to load.");
    });
  }, [id]);

  useEffect(() => {
    if (!data?.project_id) return;
    const token = dashboardApiToken();
    const streamPath = token
      ? `/api/projects/${data.project_id}/trace/stream?token=${encodeURIComponent(token)}`
      : `/api/projects/${data.project_id}/trace/stream`;
    const source = new EventSource(streamPath);
    let polling = false;
    source.onmessage = (event) => {
      try {
        const row = JSON.parse(event.data) as TraceRow;
        setData((current) =>
          current ? { ...current, trace: [...current.trace, row].slice(-200) } : current,
        );
      } catch {
        // Keep polling fallback below.
      }
    };
    source.onerror = () => {
      polling = true;
      source.close();
    };
    const timer = window.setInterval(() => {
      if (!polling) return;
      void getDashboardJson<{ entries: TraceRow[] }>(`/api/projects/${data.project_id}/trace?limit=200`)
        .then((payload) => {
          setData((current) => current ? { ...current, trace: payload.entries } : current);
        })
        .catch(() => {
          // Keep the existing trace; the next catalog refresh can recover.
        });
    }, 3000);
    return () => {
      source.close();
      window.clearInterval(timer);
    };
  }, [data?.project_id]);

  const runAction = async (action: string, payload: Record<string, unknown> = {}) => {
    if (!data) return;
    const phrase = confirmationPhrase(action, payload);
    if (phrase && !confirmTypedPhrase(phrase, `Confirm ${action}`)) return;
    setBusy(action);
    setStatus(`Submitting ${action}.`);
    try {
      const result = await postDashboardJson<Record<string, any>>(
        `/api/strategies/${strategyId}/actions/${action}`,
        payload,
      );
      setStatus(result.status === "queued" ? `${action} queued.` : `${action} executed.`);
      if (result.status === "queued") setTab("trace");
      await refresh();
      const catalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
        "/api/dashboard/catalog",
      );
      applyDashboardCatalog(catalog);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : `${action} failed.`);
    } finally {
      setBusy(null);
    }
  };

  const acceptDraft = async (accept: boolean) => {
    setBusy(accept ? "accept" : "reject");
    try {
      await postDashboardJson(`/api/strategies/${strategyId}/spec/${accept ? "accept" : "reject"}`, {
        reason: accept ? "Dashboard accept draft" : "Dashboard reject draft",
      });
      setStatus(accept ? "Draft accepted." : "Draft rejected.");
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Spec action failed.");
    } finally {
      setBusy(null);
    }
  };

  if (!fallback && !data) {
    return <div className="px-6 pb-8"><Card>No strategy found for {id}.</Card></div>;
  }

  const gate = data?.project?.gate_summary ?? {};
  const paperReport = data?.paper_readiness?.[0];
  const latestRun = data?.runs?.[0];
  const evidence = data?.project?.evidence ?? {};
  const signals = data?.signals ?? [];

  return (
    <div className="px-6 pb-8 space-y-3">
      <div className="dscard p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="t-caption ink-subtle">STRATEGY WORKBENCH</span>
              <Tag color="paper">{data?.strategy?.lifecycle ?? fallback?.status ?? "unknown"}</Tag>
              <Tag color="cyan">{data?.strategy?.timeframe ?? fallback?.timeframe ?? "n/a"}</Tag>
              <Tag color="paper">{data?.strategy?.backend ?? fallback?.backend ?? "python_reference"}</Tag>
            </div>
            <h1 className="t-title-xl mt-2 truncate">{humanize(name)}</h1>
            <div className="t-body-sm ink-subtle mt-1 truncate">
              {data?.spec?.active_path ?? fallback?.sourcePath ?? "No StrategySpec path"}
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button className="pill pill-primary" disabled={!!busy} onClick={() => void runAction("evidence")}>
              <Play size={13} /> Run Evidence
            </button>
            <button className="pill pill-secondary" disabled={!!busy} onClick={() => void runAction("materialize")}>
              <Sparkles size={13} /> Materialize
            </button>
            <button className="pill pill-secondary" disabled={!!busy} onClick={() => void runAction("promote")}>
              <ShieldCheck size={13} /> Promote
            </button>
          </div>
        </div>
      </div>

      <div className="sticky top-0 z-10 dscard p-3 grid grid-cols-4 gap-2">
        <PassBadge label="workflow_pass" value={gate.workflow_pass} reasons={data?.pass_reasons?.workflow_pass ?? []} />
        <PassBadge label="research_pass" value={gate.research_pass} reasons={data?.pass_reasons?.research_pass ?? []} />
        <PassBadge label="llm_contribution_pass" value={gate.llm_contribution_pass} reasons={data?.pass_reasons?.llm_contribution_pass ?? []} />
        <PassBadge label="paper_ready_pass" value={gate.paper_ready_pass ?? paperReport?.ready} reasons={data?.pass_reasons?.paper_ready_pass ?? []} />
      </div>

      <div className="flex flex-wrap gap-1 px-1">
        {TABS.map((item) => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={`pill ${tab === item.key ? "pill-primary" : "pill-secondary"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <OverviewTab
          data={data}
          latestRun={latestRun}
          evidence={evidence}
          status={status}
          busy={busy}
          onAction={runAction}
        />
      )}
      {tab === "conversation" && (
        <ConversationTab projectId={data?.project_id} queue={data?.queue ?? []} trace={data?.trace ?? []} />
      )}
      {tab === "spec" && (
        <SpecTab spec={data?.spec} busy={busy} onAccept={() => void acceptDraft(true)} onReject={() => void acceptDraft(false)} />
      )}
      {tab === "runs" && <RunsTab runs={data?.runs ?? []} signals={signals} />}
      {tab === "promotion" && <PromotionTab reports={data?.research_reports ?? []} paper={paperReport} />}
      {tab === "paper" && (
        <PaperTab
          paper={paperReport}
          onActivate={(mode) => void runAction("activate", { mode })}
          onDisable={() => void runAction("disable")}
          busy={busy}
        />
      )}
      {tab === "llm" && (
        <LLMFactorsTab
          strategyId={strategyId}
          factors={data?.llm_factors ?? []}
          onMaterialize={(factor, windowBars) => void runAction("materialize", { factor, window_bars: windowBars ?? "full" })}
          onPromptSaved={() => void refresh()}
        />
      )}
      {tab === "trace" && <TraceTab trace={data?.trace ?? []} />}
    </div>
  );
}

function confirmationPhrase(action: string, payload: Record<string, unknown>) {
  if (action === "promote" || action === "disable") return "CONFIRM STRATEGY COMMAND";
  if (action === "activate" && payload.mode === "paper_auto") return "CONFIRM PAPER COMMAND";
  return "";
}

function confirmTypedPhrase(phrase: string, title: string) {
  const typed = window.prompt(`${title}\n\nType exactly: ${phrase}`);
  return typed === phrase;
}

function OverviewTab({
  data,
  latestRun,
  evidence,
  status,
  busy,
  onAction,
}: {
  data: StrategyDetailPayload | null;
  latestRun?: Record<string, any>;
  evidence: Record<string, any>;
  status: string;
  busy: string | null;
  onAction: (action: string, payload?: Record<string, unknown>) => Promise<void>;
}) {
  const equity = data?.equity?.points ?? [];
  const drawdown = data?.drawdown?.points ?? [];
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card className="col-span-8" pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="green">Equity Curve</SectionTitle></div>
        <div className="p-4"><EquityCurve data={equity} /></div>
      </Card>
      <Card className="col-span-4">
        <SectionTitle tick="ink" hint={status}>Key Metrics</SectionTitle>
        <div className="grid grid-cols-2 gap-2 mt-4">
          <KPI label="Return" value={formatPct(latestRun?.total_return_pct)} accent="green" />
          <KPI label="Sharpe" value={formatNumber(latestRun?.sharpe_ratio)} accent="cyan" />
          <KPI label="Trades" value={String(latestRun?.trades ?? latestRun?.signals ?? 0)} accent="orange" />
          <KPI label="Fees" value={money(latestRun?.total_fees ?? 0)} accent="black" />
        </div>
      </Card>
      <Card className="col-span-5" pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="pink">Drawdown</SectionTitle></div>
        <div className="p-4"><DrawdownChart data={drawdown} /></div>
      </Card>
      <Card className="col-span-3">
        <SectionTitle tick="cyan">Evidence Tracks</SectionTitle>
        <EvidenceLine label="Factor Quality" item={evidence.factor_quality} />
        <EvidenceLine label="Execution Reality" item={evidence.execution_reality} />
        <EvidenceLine label="Alt/LLM Evidence" item={evidence.alt_llm_evidence} />
      </Card>
      <Card className="col-span-4">
        <SectionTitle tick="orange">Actions</SectionTitle>
        <div className="grid grid-cols-1 gap-2 mt-4">
          {[
            ["evidence", "Run Evidence", Play],
            ["materialize", "Materialize LLM Factors", Sparkles],
            ["promote", "Promote to Approved", ShieldCheck],
            ["disable", "Disable", CircleStop],
          ].map(([action, label, Icon]: any) => (
            <button
              key={action}
              className="pill pill-secondary justify-start"
              disabled={!!busy}
              onClick={() => void onAction(action)}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ConversationTab({
  projectId,
  queue,
  trace,
}: {
  projectId?: string;
  queue: QueueRow[];
  trace: TraceRow[];
}) {
  const [body, setBody] = useState("");
  const [status, setStatus] = useState(projectId ? "Queue is ready." : "No linked project yet.");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!projectId || !body.trim()) return;
    setStatus("Writing queue command.");
    try {
      await postDashboardJson(`/api/projects/${projectId}/queue`, { kind: "advice", body });
      setBody("");
      setStatus("Command queued. Trace will update as the agent works.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Queue write failed.");
    }
  };
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card className="col-span-7" pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="purple">Conversation Trace</SectionTitle></div>
        <TraceList rows={trace.slice(-60)} />
      </Card>
      <Card className="col-span-5">
        <SectionTitle tick="green" hint={status}>Send Advice</SectionTitle>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="ds-input w-full min-h-[140px] px-3 py-2 t-body-sm"
            placeholder="Describe what the agent should try next."
          />
          <button className="pill pill-primary" disabled={!projectId || !body.trim()}>
            <Bot size={13} /> Queue to Agent
          </button>
        </form>
        <div className="mt-5 space-y-2">
          <SectionTitle tick="ink">Queue</SectionTitle>
          {queue.slice(-8).reverse().map((item) => (
            <div key={item.id} className="rounded-md bg-[var(--paper-3)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="t-title-sm">{item.kind}</span>
                <Tag color={item.consumed_at ? "green" : "orange"}>{item.consumed_at ? "consumed" : "pending"}</Tag>
              </div>
              <div className="t-body-sm ink-subtle mt-1 line-clamp-3">{item.body || "(empty)"}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SpecTab({
  spec,
  busy,
  onAccept,
  onReject,
}: {
  spec?: SpecPayload;
  busy: string | null;
  onAccept: () => void;
  onReject: () => void;
}) {
  const diff = useMemo(() => buildDiff(spec?.active_text ?? "", spec?.draft_text ?? ""), [spec]);
  if (!spec) return <Card>Spec is loading.</Card>;
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card className="col-span-6" pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="ink">Active Spec</SectionTitle></div>
        <CodeBlock text={spec.active_text} />
      </Card>
      <Card className="col-span-6" pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick={spec.has_pending_draft ? "orange" : "cyan"} action={
            <div className="flex gap-2">
              <button className="pill pill-primary" disabled={!!busy || !spec.has_pending_draft} onClick={onAccept}>
                <Check size={13} /> Accept
              </button>
              <button className="pill pill-secondary" disabled={!!busy || !spec.has_pending_draft} onClick={onReject}>
                Reject
              </button>
            </div>
          }>
            Draft Diff
          </SectionTitle>
        </div>
        <CodeBlock text={diff.length ? diff.join("\n") : "No pending draft diff."} />
      </Card>
    </div>
  );
}

function RunsTab({ runs, signals }: { runs: Array<Record<string, any>>; signals: SignalRow[] }) {
  return (
    <div className="space-y-3">
      <Card pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="cyan">Runs</SectionTitle></div>
        <div className="overflow-auto">
          <table className="w-full t-body-sm">
            <thead><tr className="hairline-b bg-[var(--paper-4)]">
              <th className="text-left px-5 py-2">Run</th><th className="text-left">Kind</th><th className="text-right">Return</th><th className="text-right">Sharpe</th><th className="text-right pr-5">Signals</th>
            </tr></thead>
            <tbody>
              {runs.length === 0 ? <tr><td colSpan={5} className="px-5 py-8 ink-muted">No runs indexed yet.</td></tr> : runs.map((run) => (
                <tr key={run.run_id} className="hairline-b">
                  <td className="px-5 py-3 t-mono">{run.run_id}</td>
                  <td><Tag color="paper">{run.kind ?? "unknown"}</Tag></td>
                  <td className="text-right t-num">{formatPct(run.total_return_pct)}</td>
                  <td className="text-right t-num">{formatNumber(run.sharpe_ratio)}</td>
                  <td className="text-right pr-5 t-num">{run.signals ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="green">Signal Log</SectionTitle></div>
        <div className="p-4"><SignalLogChart data={signals.map((row) => ({ timestamp: row.timestamp, price: Number(row.price), side: row.side, action: row.action }))} /></div>
      </Card>
    </div>
  );
}

function PromotionTab({ reports, paper }: { reports: Array<Record<string, any>>; paper?: Record<string, any> }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card className="col-span-7" pad={false}>
        <div className="px-5 py-4 hairline-b"><SectionTitle tick="cyan">Research Reports</SectionTitle></div>
        <div className="divide-y divide-[var(--hairline)]">
          {reports.length === 0 ? <div className="px-5 py-8 ink-muted">No promotion or evidence report is indexed yet.</div> : reports.map((report) => (
            <div key={report.report_json_path ?? report.source_path} className="px-5 py-3">
              <div className="flex items-center justify-between gap-2">
                <div className="t-title-sm">{report.kind ?? "research"}</div>
                <Tag color={statusColor(report.status)}>{report.status ?? "warning"}</Tag>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {report.candidate_status ? <Tag color="paper">candidate: {report.candidate_status}</Tag> : null}
                {report.iteration_outcome ? <Tag color="paper">outcome: {report.iteration_outcome}</Tag> : null}
                {report.data_compare_status ? <Tag color={statusColor(report.data_compare_status)}>data: {report.data_compare_status}</Tag> : null}
                {report.route_attribution_status ? <Tag color={statusColor(report.route_attribution_status)}>route: {report.route_attribution_status}</Tag> : null}
              </div>
              <div className="t-body-sm ink-subtle mt-1 truncate">{report.report_json_path ?? report.source_path}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="col-span-5">
        <SectionTitle tick="orange">Paper Readiness</SectionTitle>
        <div className="mt-4 space-y-2">
          <StatusRow label="Status" value={paper?.status ?? "missing"} />
          <StatusRow label="Ready" value={paper?.ready ? "yes" : "no"} />
          <StatusRow label="Report" value={paper?.path ?? "n/a"} />
        </div>
        <div className="mt-4 space-y-2">
          {(paper?.checks ?? []).slice(0, 8).map((check: any) => (
            <div key={check.name} className="rounded-md bg-[var(--paper-3)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="t-title-sm">{check.name}</span>
                <Tag color={statusColor(check.status)}>{check.status}</Tag>
              </div>
              <div className="t-body-sm ink-subtle mt-1">{check.message}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function PaperTab({
  paper,
  busy,
  onActivate,
  onDisable,
}: {
  paper?: Record<string, any>;
  busy: string | null;
  onActivate: (mode: "manual" | "paper_auto") => void;
  onDisable: () => void;
}) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card className="col-span-5">
        <SectionTitle tick="green">Lifecycle</SectionTitle>
        <div className="mt-4 grid grid-cols-1 gap-2">
          <button className="pill pill-primary justify-start" disabled={!!busy} onClick={() => onActivate("manual")}>
            <Play size={13} /> Activate Manual
          </button>
          <button className="pill pill-secondary justify-start" disabled={!!busy} onClick={() => onActivate("paper_auto")}>
            <ShieldCheck size={13} /> Activate Paper
          </button>
          <button className="pill pill-secondary justify-start" disabled={!!busy} onClick={onDisable}>
            <CircleStop size={13} /> Disable
          </button>
        </div>
      </Card>
      <Card className="col-span-7">
        <SectionTitle tick="orange">Readiness Gates</SectionTitle>
        <div className="mt-4 space-y-2">
          {(paper?.checks ?? []).length === 0 ? (
            <div className="t-body-sm ink-muted">No paper readiness report is indexed.</div>
          ) : (
            paper?.checks.map((check: any) => (
              <StatusRow key={check.name} label={check.name} value={`${check.status}: ${check.message}`} />
            ))
          )}
        </div>
      </Card>
    </div>
  );
}

function LLMFactorsTab({
  strategyId,
  factors,
  onMaterialize,
  onPromptSaved,
}: {
  strategyId: string;
  factors: Array<Record<string, any>>;
  onMaterialize: (factor: string, windowBars?: number) => void;
  onPromptSaved: () => void;
}) {
  const [windowByFactor, setWindowByFactor] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [promptText, setPromptText] = useState("");
  const [status, setStatus] = useState("LLM factor prompts are ready.");

  const editPrompt = async (factor: string) => {
    setStatus("Loading prompt.");
    try {
      const payload = await getDashboardJson<Record<string, any>>(
        `/api/strategies/${strategyId}/llm-factors/${factor}/prompt`,
      );
      setEditing(factor);
      setPromptText(String(payload.prompt ?? ""));
      setStatus("Prompt loaded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Prompt load failed.");
    }
  };

  const savePrompt = async (factor: string) => {
    setStatus("Saving prompt.");
    try {
      const payload = await postDashboardJson<Record<string, any>>(
        `/api/strategies/${strategyId}/llm-factors/${factor}/prompt`,
        { prompt: promptText },
      );
      setStatus(payload.needs_rematerialize ? "Prompt saved. Re-materialize this factor before promotion." : "Prompt saved.");
      setEditing(null);
      onPromptSaved();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Prompt save failed.");
    }
  };

  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-12 t-body-sm ink-subtle">{status}</div>
      {factors.length === 0 ? (
        <Card className="col-span-12">This strategy has no source=llm_feature factors.</Card>
      ) : (
        factors.map((factor) => (
          <Card key={factor.name} className="col-span-6">
            <SectionTitle tick="purple" action={
              <div className="flex flex-wrap gap-2">
                <select
                  className="ds-input h-8 px-2 t-body-xs"
                  value={windowByFactor[String(factor.name)] ?? "full"}
                  onChange={(event) => setWindowByFactor((current) => ({ ...current, [String(factor.name)]: event.target.value }))}
                >
                  <option value="16">Last 16</option>
                  <option value="200">Last 200</option>
                  <option value="1000">Last 1000</option>
                  <option value="full">Full history</option>
                </select>
                <button
                  className="pill pill-secondary"
                  onClick={() => {
                    const selected = windowByFactor[String(factor.name)] ?? "full";
                    onMaterialize(String(factor.name), selected === "full" ? undefined : Number(selected));
                  }}
                >
                  <RefreshCw size={13} /> Materialize
                </button>
              </div>
            }>
              {factor.name}
            </SectionTitle>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <KPI label="Packets" value={String(factor.packet_count ?? 0)} accent={factor.point_in_time_ready ? "green" : "orange"} />
              <KPI label="Input view" value={String(factor.input_view_version ?? "n/a")} accent="cyan" />
              <KPI label="Prompt hash" value={shortHash(factor.prompt_hash)} accent="black" />
              <KPI label="PIT" value={factor.point_in_time_ready ? "ready" : "missing"} accent={factor.point_in_time_ready ? "green" : "orange"} />
            </div>
            {editing === factor.name ? (
              <div className="mt-4 space-y-2">
                <textarea
                  value={promptText}
                  onChange={(event) => setPromptText(event.target.value)}
                  className="ds-input w-full min-h-[220px] px-3 py-2 t-body-sm"
                />
                <div className="flex gap-2">
                  <button className="pill pill-primary" onClick={() => void savePrompt(String(factor.name))}>
                    <Save size={13} /> Save
                  </button>
                  <button className="pill pill-secondary" onClick={() => setEditing(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-md bg-[var(--paper-3)] p-3 t-body-sm ink-subtle whitespace-pre-wrap max-h-36 overflow-auto">
                {factor.prompt_preview || "No prompt template preview."}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="pill pill-secondary" onClick={() => void editPrompt(String(factor.name))}>
                <Pencil size={13} /> Edit prompt
              </button>
              {factor.factor_lab?.flags?.slice(0, 3).map((flag: string) => (
                <Tag key={flag} color="orange">{flag}</Tag>
              ))}
            </div>
            <div className="mt-3">
              <FactorICChart data={[
                { name: "RankIC", value: numericOrNull(factor.factor_lab?.rank_ic) },
                { name: "RollMean", value: numericOrNull(factor.factor_lab?.rolling_rank_ic_mean) },
                { name: "RollMin", value: numericOrNull(factor.factor_lab?.rolling_rank_ic_min) },
              ]} />
            </div>
          </Card>
        ))
      )}
    </div>
  );
}

function TraceTab({ trace }: { trace: TraceRow[] }) {
  return <Card pad={false}><TraceList rows={trace} detailed /></Card>;
}

function TraceList({ rows, detailed = false }: { rows: TraceRow[]; detailed?: boolean }) {
  if (rows.length === 0) return <div className="px-5 py-8 t-body-sm ink-muted">No trace rows yet.</div>;
  return (
    <div className="divide-y divide-[var(--hairline)]">
      {rows.slice().reverse().map((row) => (
        <div key={`${row.span_id}-${row.ts}`} className="px-5 py-3 grid grid-cols-[132px_100px_minmax(0,1fr)] gap-3">
          <div className="t-body-xs t-mono ink-subtle">{formatDate(row.ts)}</div>
          <div><Tag color={agentColor(row.agent)}>{row.agent}</Tag></div>
          <div className="min-w-0">
            <div className="t-title-sm truncate">{row.operation}</div>
            <div className="t-body-xs ink-subtle truncate">{row.queue_command_id ?? row.span_id}</div>
            {detailed && <pre className="mt-2 t-body-xs bg-[var(--paper-3)] p-2 overflow-auto">{JSON.stringify(row.metadata ?? {}, null, 2)}</pre>}
          </div>
        </div>
      ))}
    </div>
  );
}

function PassBadge({ label, value, reasons }: { label: string; value: unknown; reasons: string[] }) {
  const color = value === true ? "green" : value === false ? "pink" : "orange";
  const detail = reasons.length ? reasons.slice(0, 6).join("\n") : "No blocker or warning detail indexed.";
  return (
    <div className="rounded-md bg-[var(--paper-3)] px-3 py-2 flex items-center justify-between gap-2 min-w-0" title={detail}>
      <span className="t-caption ink-subtle truncate">{label}</span>
      <Tag color={color}>{value === true ? "pass" : value === false ? "fail" : "unknown"}</Tag>
    </div>
  );
}

function EvidenceLine({ label, item }: { label: string; item?: Record<string, any> }) {
  return (
    <div className="mt-3 rounded-md bg-[var(--paper-3)] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="t-title-sm">{label}</span>
        <Tag color={evidenceColor(item?.status)}>{item?.status ?? "unknown"}</Tag>
      </div>
      <div className="t-body-sm ink-subtle mt-1 line-clamp-2">{item?.summary ?? "No evidence linked."}</div>
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[150px_minmax(0,1fr)] gap-3 py-2 hairline-b t-body-sm">
      <span className="ink-subtle">{label}</span>
      <span className="truncate" title={value}>{value}</span>
    </div>
  );
}

function CodeBlock({ text }: { text: string }) {
  return <pre className="max-h-[620px] overflow-auto p-4 t-body-xs bg-[var(--paper-3)] whitespace-pre-wrap">{text}</pre>;
}

function buildDiff(left: string, right: string) {
  if (!right.trim() || left === right) return [];
  const leftLines = left.split("\n");
  const rightLines = right.split("\n");
  const rows: string[] = [];
  const length = Math.max(leftLines.length, rightLines.length);
  for (let index = 0; index < length; index += 1) {
    if (leftLines[index] === rightLines[index]) {
      rows.push(`  ${leftLines[index] ?? ""}`);
    } else {
      if (leftLines[index] !== undefined) rows.push(`- ${leftLines[index]}`);
      if (rightLines[index] !== undefined) rows.push(`+ ${rightLines[index]}`);
    }
  }
  return rows;
}

function humanize(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPct(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(2)}%` : "n/a";
}

function formatNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "n/a";
}

function numericOrNull(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function shortHash(value: unknown) {
  const text = String(value ?? "");
  if (!text) return "n/a";
  return text.replace("sha256:", "").slice(0, 10);
}

function money(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusColor(status: string): "green" | "orange" | "pink" | "paper" {
  if (status === "ok") return "green";
  if (status === "blocked" || status === "failed") return "pink";
  if (status === "warning") return "orange";
  return "paper";
}

function evidenceColor(status: string): "green" | "orange" | "pink" | "paper" {
  if (status === "ok") return "green";
  if (status === "blocked") return "pink";
  if (status === "warning" || status === "unknown") return "orange";
  return "paper";
}

function agentColor(agent: string): "green" | "cyan" | "purple" | "black" | "paper" {
  if (agent === "dashboard") return "cyan";
  if (agent === "codex") return "green";
  if (agent === "claude_code") return "purple";
  if (agent === "cli") return "black";
  return "paper";
}
