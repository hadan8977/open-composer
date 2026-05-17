import { Card, SectionTitle, Tag, KPI } from "./blocks";
import { Hero } from "./hero";
import {
  auditLog,
  dashboardSummary,
  events,
  llmReviews,
  paperOrders,
  recentSignals,
  researchRuns,
} from "./data";
import { Notifications } from "./notifications";

export function ActivityView() {
  const timeline = [
    ...recentSignals.map((signal) => ({
      id: `signal-${signal.id}`,
      time: signal.t,
      kind: "Signal",
      title: `${signal.side} ${signal.symbol}`,
      detail: `${signal.strat} · ${signal.tag} · ${signal.px.toFixed(2)}`,
      color: "green" as const,
    })),
    ...paperOrders.map((order) => ({
      id: `order-${order.id}`,
      time: order.submittedAt,
      kind: "Paper order",
      title: `${order.side} ${order.symbol}`,
      detail: `${order.strategy} · ${order.qty} · ${order.status}`,
      color: "pink" as const,
    })),
    ...events.map((event, index) => ({
      id: `event-${index}`,
      time: event.t,
      kind: event.kind,
      title: event.title,
      detail: `Impact ${event.impact}`,
      color: event.impact === "high" ? "orange" as const : "cyan" as const,
    })),
    ...llmReviews.map((review) => ({
      id: `review-${review.id}`,
      time: review.id,
      kind: "LLM review",
      title: `${review.strat} · ${review.verdict}`,
      detail: review.summary,
      color: "purple" as const,
    })),
    ...auditLog.map((entry, index) => ({
      id: `audit-${index}`,
      time: entry.t,
      kind: "Audit",
      title: entry.action,
      detail: `${entry.who} · ${entry.target}`,
      color: "black" as const,
    })),
  ].slice(0, 24);

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="orange"
        greeting={`Activity · ${timeline.length} visible records`}
        headline="Timeline"
        meta="Signals, paper orders, notifications, reviews, replay records and audits from the generated dashboard catalog."
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
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="orange">Unified activity</SectionTitle>
        </div>
        <div className="divide-y divide-[var(--hairline)]">
          {timeline.length === 0 ? (
            <div className="px-5 py-8 t-body-sm ink-muted">
              No activity records are present in the current dashboard catalog.
            </div>
          ) : (
            timeline.map((item) => (
              <div
                key={item.id}
                className="grid grid-cols-[96px_120px_minmax(0,1fr)] gap-3 px-5 py-3 items-start"
              >
                <div className="t-body-sm t-num ink-subtle truncate">{item.time}</div>
                <div>
                  <Tag color={item.color}>{item.kind}</Tag>
                </div>
                <div className="min-w-0">
                  <div className="t-title-sm truncate">{item.title}</div>
                  <div className="t-body-sm ink-subtle mt-0.5 truncate">{item.detail}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      <Notifications />
    </div>
  );
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
        meta="ResearchRunIndex records from the shared kernel, including candidate counts, trial counts, gate status, blockers and source artifacts."
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
                    <td><Tag color="paper">{run.kind}</Tag></td>
                    <td><Tag color={statusColor(run.status)}>{run.status}</Tag></td>
                    <td className="text-right t-num">{run.candidateCount}</td>
                    <td className="text-right t-num">{run.trialCount}</td>
                    <td className="text-right t-num">{formatSeconds(run.runtimeSeconds)}</td>
                    <td className="max-w-[260px]">
                      <div className="truncate" title={blockers.join(", ") || "none"}>
                        {blockers.join(", ") || "none"}
                      </div>
                      <div className="t-body-xs ink-subtle mt-0.5">
                        {run.dataSourceMode}{run.dataAsOf ? ` · ${formatDate(run.dataAsOf)}` : ""}
                      </div>
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
