import { Card, SectionTitle, Tag, KPI } from "./blocks";
import { Hero } from "./hero";
import {
  auditLog,
  dashboardSummary,
  events,
  llmReviews,
  paperOrders,
  recentSignals,
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
