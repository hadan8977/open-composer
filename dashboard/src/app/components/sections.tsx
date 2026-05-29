import { useEffect, useMemo, useState } from "react";
import { Card, SectionTitle, Tag, KPI } from "./blocks";
import { Hero } from "./hero";
import {
  auditLog,
  dashboardSummary,
  events,
  llmReviews,
  paperOrders,
  projects,
  recentSignals,
  researchRuns,
} from "./data";
import { Notifications } from "./notifications";
import { getDashboardJson } from "./runtime";

type ActivityItem = {
  id: string;
  time: string;
  kind: string;
  project: string;
  title: string;
  detail: string;
  color: "green" | "orange" | "pink" | "cyan" | "purple" | "black" | "paper";
};

export function ActivityView() {
  const [kindFilter, setKindFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [traceItems, setTraceItems] = useState<ActivityItem[]>([]);
  useEffect(() => {
    void getDashboardJson<{ entries: Array<Record<string, any>> }>("/api/activity/trace?limit=200")
      .then((payload) => {
        setTraceItems(payload.entries.map((row) => ({
          id: `trace-${row.project_id}-${row.span_id ?? row.ts}`,
          time: String(row.ts ?? ""),
          kind: String(row.agent ?? "Trace"),
          project: String(row.project_name ?? row.project_id ?? ""),
          title: String(row.operation ?? "trace event"),
          detail: JSON.stringify(row.metadata ?? {}),
          color: agentColor(String(row.agent ?? "")),
        })));
      })
      .catch(() => {
        setTraceItems([]);
      });
  }, []);
  const timeline = useMemo<ActivityItem[]>(() => [
    ...traceItems,
    ...projects.flatMap((project) => {
      const steps = project.latestRunSummary?.stepEvents ?? [];
      const stepItems = steps.map((step, index) => ({
        id: `project-${project.projectId}-step-${index}`,
        time: project.updatedAt ?? project.createdAt ?? "",
        kind: "Project trace",
        project: project.name,
        title: `${step.stepName} · ${step.status}`,
        detail: [
          ...step.blockedItems,
          ...step.warningItems,
          ...step.outputArtifacts,
        ].join(" · ") || project.nextAction || "Project step recorded.",
        color: traceColor(step.status),
      }));
      const blocker = project.blockerSummary
        ? [{
            id: `project-${project.projectId}-blocker`,
            time: project.updatedAt ?? project.createdAt ?? "",
            kind: "Blocker",
            project: project.name,
            title: `${project.blockerSummary.failedStep || "blocked"} · ${project.blockerSummary.trigger || "failure"}`,
            detail: project.blockerSummary.rootBlockers.join(" · ") || project.nextAction,
            color: "pink" as const,
          }]
        : [];
      return [...stepItems, ...blocker];
    }),
    ...recentSignals.map((signal) => ({
      id: `signal-${signal.id}`,
      time: signal.t,
      kind: "Signal",
      project: signal.strat,
      title: `${signal.side} ${signal.symbol}`,
      detail: `${signal.strat} · ${signal.tag} · ${signal.px.toFixed(2)}`,
      color: "green" as const,
    })),
    ...paperOrders.map((order) => ({
      id: `order-${order.id}`,
      time: order.submittedAt,
      kind: "Paper order",
      project: order.strategy,
      title: `${order.side} ${order.symbol}`,
      detail: `${order.strategy} · ${order.qty} · ${order.status}`,
      color: "pink" as const,
    })),
    ...events.map((event, index) => ({
      id: `event-${index}`,
      time: event.t,
      kind: event.kind,
      project: "Market context",
      title: event.title,
      detail: `Impact ${event.impact}`,
      color: event.impact === "high" ? "orange" as const : "cyan" as const,
    })),
    ...llmReviews.map((review) => ({
      id: `review-${review.id}`,
      time: review.id,
      kind: "LLM review",
      project: review.strat,
      title: `${review.strat} · ${review.verdict}`,
      detail: review.summary,
      color: "purple" as const,
    })),
    ...auditLog.map((entry, index) => ({
      id: `audit-${index}`,
      time: entry.t,
      kind: "Audit",
      project: entry.target,
      title: entry.action,
      detail: `${entry.who} · ${entry.target}`,
      color: "black" as const,
    })),
  ], [
    traceItems,
    dashboardSummary.auditCount,
    dashboardSummary.generatedAt,
    dashboardSummary.orderCount,
    dashboardSummary.projectCount,
    dashboardSummary.reviewCount,
    dashboardSummary.signalCount,
  ]);

  const projectOptions = useMemo(
    () => ["all", ...Array.from(new Set(timeline.map((item) => item.project).filter(Boolean)))],
    [timeline],
  );
  const kindOptions = useMemo(
    () => ["all", ...Array.from(new Set(timeline.map((item) => item.kind)))],
    [timeline],
  );
  const filteredTimeline = timeline
    .filter((item) => kindFilter === "all" || item.kind === kindFilter)
    .filter((item) => projectFilter === "all" || item.project === projectFilter)
    .filter((item) => matchesDateFilter(item.time, dateFilter))
    .slice(0, 80);

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="orange"
        greeting={`Activity · ${filteredTimeline.length} visible records`}
        headline="Timeline"
        meta="Signals, paper orders, project trace summaries, notifications, reviews, replay records and audits from the generated dashboard catalog."
        stat={{
          label: "Signals / orders",
          value: `${dashboardSummary.signalCount} / ${dashboardSummary.orderCount}`,
          delta: `${dashboardSummary.auditCount} audits · ${dashboardSummary.reviewCount} reviews`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3">
          <KPI label="Signals" value={String(dashboardSummary.signalCount)} accent="green" />
        </div>
        <div className="col-span-3">
          <KPI label="Paper orders" value={String(paperOrders.length)} accent="pink" />
        </div>
        <div className="col-span-3">
          <KPI label="Reviews" value={String(dashboardSummary.reviewCount)} accent="purple" />
        </div>
        <div className="col-span-3">
          <KPI label="Audit" value={String(dashboardSummary.auditCount)} accent="black" />
        </div>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b space-y-3">
          <SectionTitle tick="orange">Unified activity</SectionTitle>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <FilterSelect label="Kind" value={kindFilter} options={kindOptions} onChange={setKindFilter} />
            <FilterSelect label="Project" value={projectFilter} options={projectOptions} onChange={setProjectFilter} />
            <FilterSelect
              label="Date"
              value={dateFilter}
              options={["all", "today", "7d"]}
              onChange={setDateFilter}
            />
          </div>
        </div>
        <div className="divide-y divide-[var(--hairline)]">
          {filteredTimeline.length === 0 ? (
            <div className="px-5 py-8 t-body-sm ink-muted">
              No activity records match the selected filters.
            </div>
          ) : (
            filteredTimeline.map((item) => (
              <button
                key={item.id}
                onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                className="w-full text-left grid grid-cols-[96px_120px_minmax(0,1fr)] gap-3 px-5 py-3 items-start hover:bg-[var(--paper-4)]"
              >
                <div className="t-body-sm t-num ink-subtle truncate">{item.time}</div>
                <div>
                  <Tag color={item.color}>{item.kind}</Tag>
                </div>
                <div className="min-w-0">
                  <div className="t-title-sm truncate">{item.title}</div>
                  <div className="t-body-sm ink-subtle mt-0.5 truncate">{item.project} · {item.detail}</div>
                  {expandedId === item.id && (
                    <div className="mt-2 t-body-sm ink bg-[var(--paper-3)] p-3" style={{ borderRadius: "var(--r-sm)" }}>
                      {item.detail || "No additional detail."}
                    </div>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </Card>

      <Notifications />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="ds-input flex items-center gap-2 px-3 h-10">
      <span className="t-caption ink-muted w-14">{label}</span>
      <select
        className="bg-transparent outline-none flex-1 t-body-sm ink min-w-0"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>{option === "all" ? "All" : option}</option>
        ))}
      </select>
    </label>
  );
}

function matchesDateFilter(value: string, filter: string) {
  if (filter === "all") return true;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return true;
  const now = new Date();
  if (filter === "today") return date.toDateString() === now.toDateString();
  if (filter === "7d") return now.getTime() - date.getTime() <= 7 * 24 * 60 * 60 * 1000;
  return true;
}

function traceColor(status: string): "green" | "orange" | "pink" | "cyan" {
  if (status === "ok" || status === "pass" || status === "completed") return "green";
  if (status === "blocked" || status === "failed") return "pink";
  if (status === "warning") return "orange";
  return "cyan";
}

function agentColor(agent: string): "green" | "orange" | "pink" | "cyan" | "purple" | "black" | "paper" {
  if (agent === "codex") return "green";
  if (agent === "claude_code") return "purple";
  if (agent === "dashboard") return "cyan";
  if (agent === "cli") return "black";
  if (agent === "system") return "orange";
  return "paper";
}

export function ResearchView() {
  const latest = researchRuns.slice(0, 24);
  const decisionCards = buildDecisionCards(researchRuns).slice(0, 6);
  const candidateLedger = researchRuns
    .filter((run) => run.candidateCount > 1 || run.trialCount > 1)
    .sort((left, right) => {
      const leftScore = left.candidateCount + left.trialCount;
      const rightScore = right.candidateCount + right.trialCount;
      return rightScore - leftScore || compareDateDesc(left.generatedAt, right.generatedAt);
    })
    .slice(0, 8);
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="cyan"
        greeting={`Research · ${dashboardSummary.researchRunCount} indexed runs`}
        headline="Evidence"
        meta="ResearchRunIndex and ExperimentRun records from the shared kernel, including candidate counts, trial counts, gate status, blockers and source artifacts."
        stat={{
          label: "Blocked / warning",
          value: `${dashboardSummary.researchBlockedCount} / ${dashboardSummary.researchWarningCount}`,
          delta: `${dashboardSummary.researchReportCount} reports · ${dashboardSummary.workflowReportCount} workflows`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3">
          <KPI label="Research runs" value={String(dashboardSummary.researchRunCount)} accent="cyan" />
        </div>
        <div className="col-span-3">
          <KPI label="Reports" value={String(dashboardSummary.researchReportCount)} accent="green" />
        </div>
        <div className="col-span-3">
          <KPI label="Blocked" value={String(dashboardSummary.researchBlockedCount)} accent="pink" />
        </div>
        <div className="col-span-3">
          <KPI label="Warnings" value={String(dashboardSummary.researchWarningCount)} accent="orange" />
        </div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-7" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="cyan">Decision cards</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {decisionCards.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">
                No strategy decision cards are available until research runs are indexed.
              </div>
            ) : (
              decisionCards.map((card) => (
                <div key={card.strategyName} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="t-title-sm truncate">{card.strategyName}</div>
                      <div className="t-body-xs ink-subtle mt-0.5 truncate">
                        {card.latestKind} · {formatDate(card.generatedAt)}
                      </div>
                    </div>
                    <Tag color={statusColor(card.status)}>{card.status}</Tag>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <MiniMetric label="Runs" value={String(card.runCount)} />
                    <MiniMetric label="Candidates" value={String(card.candidateCount)} />
                    <MiniMetric label="Trials" value={String(card.trialCount)} />
                  </div>
                  <div className="t-body-sm ink mt-3 truncate" title={card.primaryIssue}>
                    {card.primaryIssue}
                  </div>
                  <div className="t-body-xs ink-subtle mt-1 truncate" title={card.nextAction}>
                    {card.nextAction}
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card className="col-span-5" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="orange">Candidate ledger</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {candidateLedger.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">
                Parameter sweeps and research modules with TrialLedger output will appear here.
              </div>
            ) : (
              candidateLedger.map((run) => (
                <div key={run.id} className="grid grid-cols-[minmax(0,1fr)_80px_80px] gap-3 px-5 py-3 items-center">
                  <div className="min-w-0">
                    <div className="t-title-sm truncate">{run.strategyName}</div>
                    <div className="t-body-xs ink-subtle truncate">
                      {run.kind} · {run.jsonPath ?? run.reportPath ?? run.sourceSpecPath}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="t-num">{run.candidateCount}</div>
                    <div className="t-caption ink-muted">candidates</div>
                  </div>
                  <div className="text-right">
                    <div className="t-num">{run.trialCount}</div>
                    <div className="t-caption ink-muted">trials</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="cyan">Research runs</SectionTitle>
        </div>
        <div className="overflow-hidden" style={{ borderRadius: "var(--r-xl)" }}>
          <table className="w-full t-body-sm" style={{ borderCollapse: "separate", borderSpacing: 0 }}>
            <thead>
              <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
                <th className="text-left px-5 py-2.5 t-caption ink-muted">Run</th>
                <th className="text-left t-caption ink-muted">Strategy</th>
                <th className="text-left t-caption ink-muted">Kind</th>
                <th className="text-left t-caption ink-muted">Status</th>
                <th className="text-right t-caption ink-muted">Candidates</th>
                <th className="text-right t-caption ink-muted">Trials</th>
                <th className="text-right t-caption ink-muted">Runtime</th>
                <th className="text-left t-caption ink-muted">Blockers</th>
                <th className="text-left pr-5 t-caption ink-muted">Source</th>
              </tr>
            </thead>
            <tbody>
              {latest.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-5 py-8 t-body-sm ink-muted">
                    Run `uv run oc strategy research-report strategy_specs/drafts/&lt;name&gt;.yaml` to populate ResearchRunIndex.
                  </td>
                </tr>
              ) : latest.map((run) => {
                const blockers = run.blockedItems.length > 0 ? run.blockedItems : run.warningItems;
                return (
                  <tr key={run.id} className="hairline-b last:border-b-0 hover:bg-[var(--paper-4)] transition-colors">
                    <td className="px-5 py-3">
                      <div className="t-mono ink">{run.id}</div>
                      <div className="t-body-xs ink-subtle mt-0.5">{formatDate(run.generatedAt)}</div>
                    </td>
                    <td className="py-3">{run.strategyName}</td>
                    <td>
                      <Tag color="paper">{run.kind}</Tag>
                      <div className="t-body-xs ink-subtle mt-1">
                        {run.researchMode ?? "legacy"} · {run.artifactCount} artifacts
                      </div>
                    </td>
                    <td><Tag color={statusColor(run.status)}>{run.status}</Tag></td>
                    <td className="text-right t-num">{run.candidateCount}</td>
                    <td className="text-right t-num">{run.trialCount}</td>
                    <td className="text-right t-num">{formatSeconds(run.runtimeSeconds)}</td>
                    <td className="max-w-[260px]">
                      <div className="truncate" title={blockers.join(", ") || "none"}>
                        {blockers.join(", ") || "none"}
                      </div>
                      <div className="t-body-xs ink-subtle mt-0.5">
                        {run.nextAction || run.dataSourceMode}{run.dataAsOf ? ` · ${formatDate(run.dataAsOf)}` : ""}
                      </div>
                      {run.progressStage ? (
                        <div className="t-body-xs ink-subtle mt-0.5 truncate" title={run.progressEventPath ?? ""}>
                          {run.progressPartial ? "partial" : run.progressStatus ?? "progress"} · {run.progressStage}
                          {run.progressCandidateCount
                            ? ` · ${run.progressCandidateIndex ?? 0}/${run.progressCandidateCount}`
                            : ""}
                        </div>
                      ) : null}
                    </td>
                    <td className="pr-5 max-w-[240px]">
                      <div className="t-mono truncate" title={run.jsonPath ?? run.reportPath ?? run.sourceSpecPath}>
                        {run.jsonPath ?? run.reportPath ?? run.sourceSpecPath}
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

interface DecisionCard {
  strategyName: string;
  status: "ok" | "warning" | "blocked";
  latestKind: string;
  generatedAt: string | null;
  runCount: number;
  candidateCount: number;
  trialCount: number;
  primaryIssue: string;
  nextAction: string;
}

function buildDecisionCards(runs: typeof researchRuns): DecisionCard[] {
  const byStrategy = new Map<string, typeof researchRuns>();
  for (const run of runs) {
    byStrategy.set(run.strategyName, [...(byStrategy.get(run.strategyName) ?? []), run]);
  }
  return Array.from(byStrategy.entries())
    .map(([strategyName, strategyRuns]) => {
      const sorted = strategyRuns
        .slice()
        .sort((left, right) => compareDateDesc(left.generatedAt, right.generatedAt));
      const latest = sorted[0];
      const status = worstStatus(sorted.map((run) => run.status));
      const issueItems = sorted.flatMap((run) =>
        run.blockedItems.length > 0 ? run.blockedItems : run.warningItems,
      );
      const primaryIssue = issueItems[0] ?? "No blockers recorded.";
      return {
        strategyName,
        status,
        latestKind: latest?.kind ?? "research_report",
        generatedAt: latest?.generatedAt ?? null,
        runCount: sorted.length,
        candidateCount: sorted.reduce((total, run) => total + run.candidateCount, 0),
        trialCount: sorted.reduce((total, run) => total + run.trialCount, 0),
        primaryIssue,
        nextAction: nextActionForIssue(primaryIssue, status),
      };
    })
    .sort((left, right) => {
      const statusRank = statusWeight(right.status) - statusWeight(left.status);
      return statusRank || compareDateDesc(left.generatedAt, right.generatedAt);
    });
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--r-sm)] bg-[var(--paper-3)] px-3 py-2 min-w-0">
      <div className="t-num truncate">{value}</div>
      <div className="t-caption ink-muted truncate">{label}</div>
    </div>
  );
}

function statusColor(status: "ok" | "warning" | "blocked") {
  if (status === "ok") return "green" as const;
  if (status === "blocked") return "pink" as const;
  return "orange" as const;
}

function worstStatus(statuses: Array<"ok" | "warning" | "blocked">) {
  if (statuses.includes("blocked")) return "blocked";
  if (statuses.includes("warning")) return "warning";
  return "ok";
}

function statusWeight(status: "ok" | "warning" | "blocked") {
  if (status === "blocked") return 2;
  if (status === "warning") return 1;
  return 0;
}

function nextActionForIssue(issue: string, status: "ok" | "warning" | "blocked") {
  if (status === "ok") return "Review paper readiness before any paper automation.";
  if (issue.includes("baseline")) return "Run baseline comparison and marginal-lift review.";
  if (issue.includes("out_of_sample") || issue.includes("walk_forward")) {
    return "Run OOS and walk-forward validation before promotion.";
  }
  if (issue.includes("cost") || issue.includes("capacity") || issue.includes("execution")) {
    return "Run execution reality and capacity review.";
  }
  if (issue.includes("research_only")) return "Keep this result in research-only mode.";
  return "Resolve the listed blockers before promotion.";
}

function compareDateDesc(left: string | null, right: string | null) {
  const leftValue = left ? Date.parse(left) : 0;
  const rightValue = right ? Date.parse(right) : 0;
  return rightValue - leftValue;
}

function formatSeconds(value: number | null) {
  return value == null ? "n/a" : `${value.toFixed(2)}s`;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "n/a";
}
