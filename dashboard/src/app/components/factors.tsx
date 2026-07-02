import { Activity, AlertTriangle, CheckCircle2, Sigma } from "lucide-react";
import { Card, Tag } from "./blocks";
import { Hero } from "./hero";
import { dashboardSummary, factorCatalog } from "./data";

type FactorTagColor = "paper" | "pink" | "green" | "orange";

const statusColor = (
  status: string,
  alert: boolean,
  retiredAt: string | null,
): FactorTagColor => {
  if (retiredAt) return "paper";
  if (alert || status === "alert") return "pink";
  if (status === "healthy") return "green";
  if (status === "insufficient_data") return "orange";
  return "paper";
};

const fmt = (value: number | null) =>
  value === null || Number.isNaN(value) ? "n/a" : value.toFixed(4);

export function FactorCatalogView() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="paper"
        greeting={`Factors · ${dashboardSummary.factorCount}`}
        headline="Factor Catalog"
        meta={`${dashboardSummary.factorDecayAlertCount} decay alerts · ${factorCatalog.filter((factor) => factor.latestDecayStatus !== "unmonitored").length} monitored`}
        stat={{
          label: "Decay alerts",
          value: String(dashboardSummary.factorDecayAlertCount),
          delta: `${factorCatalog.filter((factor) => factor.retiredAt).length} retired`,
        }}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card>
          <div className="flex items-center gap-2">
            <Sigma size={15} />
            <span className="t-caption ink-muted">CATALOG SIZE</span>
          </div>
          <div className="t-title-lg mt-2">{dashboardSummary.factorCount}</div>
        </Card>
        <Card>
          <div className="flex items-center gap-2">
            <Activity size={15} />
            <span className="t-caption ink-muted">MONITORED</span>
          </div>
          <div className="t-title-lg mt-2">
            {factorCatalog.filter((factor) => factor.latestDecayStatus !== "unmonitored").length}
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} />
            <span className="t-caption ink-muted">ALERTS</span>
          </div>
          <div className="t-title-lg mt-2">{dashboardSummary.factorDecayAlertCount}</div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="overflow-hidden" style={{ borderRadius: "var(--r-xl)" }}>
          <table className="w-full t-body-sm" style={{ borderCollapse: "separate", borderSpacing: 0 }}>
            <thead>
              <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
                <th className="text-left px-5 py-2.5 t-caption ink-muted">Factor</th>
                <th className="text-left t-caption ink-muted">Family</th>
                <th className="text-left t-caption ink-muted">Decay</th>
                <th className="text-right t-caption ink-muted">3m IC</th>
                <th className="text-right t-caption ink-muted">12m IR</th>
                <th className="text-right t-caption ink-muted">Uses</th>
                <th className="text-center t-caption ink-muted">Expr</th>
                <th className="text-right pr-5 t-caption ink-muted">Alerts</th>
              </tr>
            </thead>
            <tbody>
              {factorCatalog.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-8 t-body-sm ink-muted">
                    Factor catalog is empty.
                  </td>
                </tr>
              ) : (
                factorCatalog.map((factor) => (
                  <tr
                    key={factor.factorId}
                    className="hairline-b last:border-b-0 hover:bg-[var(--paper-4)] transition-colors"
                  >
                    <td className="px-5 py-3">
                      <div className="t-title-sm">{factor.label}</div>
                      <div className="t-mono ink-subtle mt-0.5">{factor.factorId}</div>
                      <div className="t-body-xs ink-subtle mt-1">{factor.output}</div>
                    </td>
                    <td className="ink-muted">{factor.family}</td>
                    <td>
                      <Tag color={statusColor(factor.latestDecayStatus, factor.latestDecayAlert, factor.retiredAt)}>
                        {factor.retiredAt ? "retired" : factor.latestDecayStatus}
                      </Tag>
                    </td>
                    <td className="text-right t-num">{fmt(factor.latest3mRankIc)}</td>
                    <td className="text-right t-num">{fmt(factor.latest12mIr)}</td>
                    <td className="text-right t-num">{factor.usedInSpecCount}</td>
                    <td className="text-center">
                      {factor.expressionAvailable ? (
                        <CheckCircle2 size={14} className="inline-block text-[#1FB85A]" />
                      ) : (
                        <span className="ink-subtle opacity-30">-</span>
                      )}
                    </td>
                    <td className="text-right pr-5 t-num">{factor.alertCount}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
