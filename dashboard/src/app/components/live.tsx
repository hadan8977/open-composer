import { RefreshCw, ShieldAlert } from "lucide-react";
import { Card, KPI, Pill, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import {
  dashboardSummary,
  paperOrders,
  paperPositions,
  projects,
  recentSignals,
} from "./data";
import { Notifications } from "./notifications";

export function LiveView() {
  const activePaperProjects = projects.filter((project) => project.state === "active_paper");
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting="Live · read-only operations"
        headline="Paper & Alerts"
        meta="Paper account, paper orders, positions and notification log in one Dashboard view. Live brokerage content is notification-only for this MVP."
        stat={{
          label: "Paper equity",
          value: dashboardSummary.paperAccountEquity ? money(dashboardSummary.paperAccountEquity) : "n/a",
          delta: `${dashboardSummary.paperOpenOrderCount} open orders · kill switch ${dashboardSummary.paperKillSwitchEnabled ? "on" : "off"}`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Equity" value={dashboardSummary.paperAccountEquity ? money(dashboardSummary.paperAccountEquity) : "n/a"} accent="green" /></div>
        <div className="col-span-3"><KPI label="Cash" value={dashboardSummary.paperAccountCash ? money(dashboardSummary.paperAccountCash) : "n/a"} accent="cyan" /></div>
        <div className="col-span-3"><KPI label="Open orders" value={String(dashboardSummary.paperOpenOrderCount)} accent="orange" /></div>
        <div className="col-span-3"><KPI label="Unrealized PnL" value={money(dashboardSummary.paperTotalUnrealizedPl)} accent={dashboardSummary.paperTotalUnrealizedPl >= 0 ? "green" : "pink"} /></div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4">
          <SectionTitle tick="green" action={<Pill><RefreshCw size={12} /> Refresh via command</Pill>}>
            Paper status
          </SectionTitle>
          <div className="mt-4 space-y-2">
            <StatusRow label="Account snapshot" value={dashboardSummary.paperAccountSnapshotAt ?? "missing"} />
            <StatusRow label="Positions snapshot" value={dashboardSummary.paperPositionsSnapshotAt ?? "missing"} />
            <StatusRow label="Reconciliation" value={dashboardSummary.paperReconciliationStatus} />
            <StatusRow label="Alerts" value={dashboardSummary.paperAlertStatus} />
            <StatusRow label="Kill switch" value={dashboardSummary.paperKillSwitchEnabled ? "enabled" : "clear"} danger={dashboardSummary.paperKillSwitchEnabled} />
          </div>
        </Card>

        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="cyan">Positions</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {paperPositions.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">No paper positions are present.</div>
            ) : paperPositions.map((position) => (
              <div key={`${position.sym}-${position.strat}`} className="grid grid-cols-[1fr_70px_90px] gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="t-title-sm truncate">{position.sym}</div>
                  <div className="t-body-xs ink-subtle truncate">{position.strat}</div>
                </div>
                <div className="text-right t-num">{position.qty}</div>
                <div className="text-right t-num" style={{ color: position.upnl >= 0 ? "#0A6E3B" : "#C81E5C" }}>{money(position.upnl)}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="orange">Active paper projects</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {activePaperProjects.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">No StrategyProject is active in paper mode.</div>
            ) : activePaperProjects.map((project) => (
              <div key={project.projectId} className="px-5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="t-title-sm truncate">{project.name}</div>
                  <Tag color="green">active_paper</Tag>
                </div>
                <div className="t-body-xs ink-subtle truncate mt-1">{project.currentSpecPath ?? "no spec"}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-7" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="pink">Paper orders</SectionTitle>
          </div>
          <div className="overflow-hidden">
            <table className="w-full t-body-sm">
              <thead>
                <tr className="hairline-b bg-[var(--paper-4)]">
                  <th className="text-left px-5 py-2 t-caption ink-muted">Submitted</th>
                  <th className="text-left t-caption ink-muted">Strategy</th>
                  <th className="text-left t-caption ink-muted">Symbol</th>
                  <th className="text-right t-caption ink-muted">Qty</th>
                  <th className="text-left pr-5 t-caption ink-muted">Status</th>
                </tr>
              </thead>
              <tbody>
                {paperOrders.length === 0 ? (
                  <tr><td colSpan={5} className="px-5 py-8 t-body-sm ink-muted">No paper orders are present.</td></tr>
                ) : paperOrders.slice().reverse().slice(0, 12).map((order) => (
                  <tr key={order.id} className="hairline-b last:border-b-0">
                    <td className="px-5 py-2.5 ink-subtle">{order.submittedAt}</td>
                    <td>{order.strategy}</td>
                    <td>{order.symbol}</td>
                    <td className="text-right t-num">{order.qty}</td>
                    <td className="pr-5"><Tag color="paper">{order.status}</Tag></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="col-span-5" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="green">Latest signals</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {recentSignals.slice(0, 8).map((signal) => (
              <div key={signal.id} className="grid grid-cols-[64px_1fr_74px] gap-3 px-5 py-3">
                <div className="t-num ink-subtle">{signal.t}</div>
                <div className="min-w-0">
                  <div className="t-title-sm truncate">{signal.strat}</div>
                  <div className="t-body-xs ink-subtle truncate">{signal.tag}</div>
                </div>
                <div className="text-right"><Tag color={signal.side === "BUY" ? "green" : "black"}>{signal.side}</Tag></div>
              </div>
            ))}
            {recentSignals.length === 0 && <div className="px-5 py-8 t-body-sm ink-muted">No signals are present.</div>}
          </div>
        </Card>
      </div>

      <div className="dscard p-4 flex items-center gap-3">
        <ShieldAlert size={16} />
        <div className="t-body-sm ink-subtle">
          Live broker content is notification-only in this MVP. Real-money broker write access remains out of scope.
        </div>
      </div>

      <Notifications />
    </div>
  );
}

function StatusRow({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 py-2 hairline-b">
      <span className="t-body-sm ink-subtle">{label}</span>
      <span className={`t-body-sm truncate ${danger ? "text-[#C81E5C]" : "ink"}`} title={value}>{value}</span>
    </div>
  );
}

function money(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}
