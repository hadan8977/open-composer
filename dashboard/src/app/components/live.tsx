import { useEffect, useMemo, useState } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import {
  dashboardSummary,
  paperOrders,
  paperPositions,
  projects,
  recentSignals,
} from "./data";
import { Notifications } from "./notifications";
import { PaperPnlChart } from "./charts/paper-pnl";
import { getDashboardJson, postDashboardJson } from "./runtime";
import { applyDashboardCatalog } from "./data";

export function LiveView() {
  const activePaperProjects = projects.filter((project) => project.state === "active_paper");
  const [status, setStatus] = useState("Paper monitor is ready.");
  const [busy, setBusy] = useState<string | null>(null);
  const [positionRows, setPositionRows] = useState(paperPositions);
  const [orderRows, setOrderRows] = useState(paperOrders);
  const [alertStatus, setAlertStatus] = useState<Record<string, any> | null>(null);
  const liveUnrealizedPnl = useMemo(
    () => positionRows.reduce((total, position) => total + Number(position.upnl ?? 0), 0),
    [positionRows],
  );

  const refreshCatalog = async () => {
    const catalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
      "/api/dashboard/catalog",
    );
    applyDashboardCatalog(catalog);
  };

  const refreshPaperData = async () => {
    const [positionsPayload, ordersPayload, alertsPayload] = await Promise.all([
      getDashboardJson<{ positions: typeof paperPositions }>("/api/paper/positions"),
      getDashboardJson<{ orders: typeof paperOrders }>("/api/paper/orders"),
      getDashboardJson<Record<string, any>>("/api/paper/alerts"),
    ]);
    setPositionRows(positionsPayload.positions ?? positionRows);
    setOrderRows(ordersPayload.orders ?? orderRows);
    setAlertStatus(alertsPayload.alerts ?? alertsPayload.status ?? null);
    setStatus("Paper data refreshed.");
  };

  useEffect(() => {
    void refreshPaperData().catch(() => {
      setStatus("Paper polling failed; keeping last successful data.");
    });
    const timer = window.setInterval(() => {
      void refreshPaperData().catch(() => {
        setStatus("Paper polling failed; keeping last successful data.");
      });
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const runPaperAction = async (action: "kill" | "clear" | "sync" | "monitor") => {
    if ((action === "kill" || action === "clear") && !confirmPaperPhrase()) {
      setStatus("Paper kill switch action cancelled.");
      return;
    }
    setBusy(action);
    try {
      if (action === "kill" || action === "clear") {
        await postDashboardJson("/api/paper/kill-switch", {
          enabled: action === "kill",
          reason: action === "kill" ? "Dashboard operator enabled kill switch." : "Dashboard operator cleared kill switch.",
        });
      } else if (action === "sync") {
        await postDashboardJson("/api/paper/sync", {});
      } else {
        await postDashboardJson("/api/paper/monitor/refresh", {});
      }
      await refreshCatalog();
      await refreshPaperData();
      setStatus(`${action} submitted.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Paper action failed.");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting="Live · read-only operations"
        headline="Paper & Alerts"
        meta={status}
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
        <div className="col-span-3"><KPI label="Unrealized PnL" value={money(liveUnrealizedPnl)} accent={liveUnrealizedPnl >= 0 ? "green" : "pink"} /></div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4">
          <SectionTitle tick="green" action={<button className="pill pill-secondary" disabled={!!busy} onClick={() => void runPaperAction("monitor")}><RefreshCw size={12} /> Refresh</button>}>
            Paper status
          </SectionTitle>
          <div className="mt-4 space-y-2">
            <StatusRow label="Account snapshot" value={dashboardSummary.paperAccountSnapshotAt ?? "missing"} />
            <StatusRow label="Positions snapshot" value={dashboardSummary.paperPositionsSnapshotAt ?? "missing"} />
            <StatusRow label="Reconciliation" value={dashboardSummary.paperReconciliationStatus} />
            <StatusRow label="Alerts" value={String(alertStatus?.status ?? dashboardSummary.paperAlertStatus)} />
            <StatusRow label="Kill switch" value={dashboardSummary.paperKillSwitchEnabled ? "enabled" : "clear"} danger={dashboardSummary.paperKillSwitchEnabled} />
          </div>
        </Card>

        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="cyan">Positions</SectionTitle>
          </div>
          <div className="divide-y divide-[var(--hairline)]">
            {positionRows.length === 0 ? (
              <div className="px-5 py-8 t-body-sm ink-muted">No paper positions are present.</div>
            ) : positionRows.map((position) => (
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
        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick={dashboardSummary.paperTotalUnrealizedPl >= 0 ? "green" : "pink"}>Paper PnL</SectionTitle>
          </div>
          <div className="p-4"><PaperPnlChart value={liveUnrealizedPnl} /></div>
          <div className="px-5 pb-4 flex flex-wrap gap-2">
            <button className="pill pill-secondary" disabled={!!busy} onClick={() => void runPaperAction("sync")}>
              <RefreshCw size={13} /> Queue Sync
            </button>
            <button className="pill pill-secondary" disabled={!!busy} onClick={() => void runPaperAction(dashboardSummary.paperKillSwitchEnabled ? "clear" : "kill")}>
              <ShieldAlert size={13} /> {dashboardSummary.paperKillSwitchEnabled ? "Clear Kill Switch" : "Kill Switch"}
            </button>
          </div>
        </Card>

        <Card className="col-span-8" pad={false}>
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
                {orderRows.length === 0 ? (
                  <tr><td colSpan={5} className="px-5 py-8 t-body-sm ink-muted">No paper orders are present.</td></tr>
                ) : orderRows.slice().reverse().slice(0, 12).map((order) => (
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

        <Card className="col-span-12" pad={false}>
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

function confirmPaperPhrase() {
  return window.prompt("Type exactly: CONFIRM PAPER COMMAND") === "CONFIRM PAPER COMMAND";
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
