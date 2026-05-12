import { LayoutDashboard, BookMarked, GitBranch, Activity, Newspaper, Sparkles, Layers, ShieldCheck } from "lucide-react";
import logoMarkUrl from "../../../logo_optimized (2).svg";
import { dashboardSummary } from "./data";

export type NavKey =
  | "overview"
  | "strategies"
  | "versions"
  | "paper"
  | "events"
  | "llm"
  | "groups"
  | "audit";

interface Props {
  active: NavKey;
  onChange: (k: NavKey) => void;
}

function navItems(): { key: NavKey; label: string; icon: any; count?: string; accent: string }[] {
  return [
    { key: "overview",   label: "Overview",         icon: LayoutDashboard, accent: "#1FB85A" },
    { key: "strategies", label: "Strategy Library", icon: BookMarked, count: String(dashboardSummary.strategyCount), accent: "#0A0A0A" },
    { key: "versions",   label: "Versions",         icon: GitBranch, count: String(dashboardSummary.versionCount), accent: "#1AC8E8" },
    { key: "paper",      label: "Paper Monitor",    icon: Activity, count: String(dashboardSummary.paperAutoStrategyCount), accent: "#1FB85A" },
    { key: "events",     label: "Events & News",    icon: Newspaper, count: String(dashboardSummary.dataComparisonCount + dashboardSummary.contextCount + dashboardSummary.featurePacketCount), accent: "#F8A93B" },
    { key: "llm",        label: "LLM Center",       icon: Sparkles, count: String(dashboardSummary.reviewCount), accent: "#8B5CF6" },
    { key: "groups",     label: "Strategy Groups",  icon: Layers, accent: "#FF2D7A" },
    { key: "audit",      label: "Audit",            icon: ShieldCheck, count: String(dashboardSummary.auditCount), accent: "#0A0A0A" },
  ];
}

export function Sidebar({ active, onChange }: Props) {
  return (
    <aside className="w-[236px] shrink-0 p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3 px-2 pt-1 pb-3 hairline-b">
        <BrandMark />
        <div
          className="min-w-0 leading-none"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 18,
            fontWeight: 800,
            letterSpacing: 0,
            lineHeight: 1,
            whiteSpace: "nowrap",
          }}
        >
          <span className="ink">Open</span>
          <span className="grad-green-cyan"> Composer</span>
        </div>
      </div>

      <nav className="flex flex-col gap-px">
        {navItems().map(({ key, label, icon: Icon, count, accent }) => {
          const isActive = active === key;
          return (
            <button
              key={key}
              onClick={() => onChange(key)}
              className={`group relative flex items-center gap-3 pl-4 pr-3 h-9 transition-colors ${
                isActive
                  ? "bg-[#0A0A0A] text-white"
                  : "ink-muted hover:bg-[rgba(10,10,10,.05)] hover:text-[#0A0A0A]"
              }`}
              style={{ borderRadius: "var(--r-md)" }}
            >
              <span
                aria-hidden
                className="absolute"
                style={{
                  left: 6, top: "50%", transform: "translateY(-50%)",
                  width: 4, height: isActive ? 16 : 8,
                  background: accent, borderRadius: 1,
                  transition: "height .12s ease",
                }}
              />
              <Icon size={15} strokeWidth={isActive ? 2.2 : 1.8} className="shrink-0" />
              <span className="t-body-md flex-1 text-left" style={{ fontWeight: isActive ? 600 : 500 }}>{label}</span>
              {count && (
                <span
                  className={`t-num inline-flex items-center justify-center min-w-[20px] h-[18px] px-1.5 ${
                    isActive ? "bg-white/15 text-white" : "ink-muted bg-[rgba(10,10,10,.06)]"
                  }`}
                  style={{
                    borderRadius: 2,
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: 0,
                  }}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto px-3 pt-3 hairline-t">
        <div className="flex items-center gap-2 mb-1">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[#1FB85A] opacity-40 animate-ping" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-[#1FB85A]" />
          </span>
          <span className="t-body-sm ink" style={{ fontWeight: 500 }}>Local catalog synced</span>
        </div>
        <p className="t-body-sm ink-subtle leading-snug">
          File-first source of truth · read model v{dashboardSummary.readModelVersion}
        </p>
      </div>
    </aside>
  );
}

function BrandMark() {
  return (
    <img
      src={logoMarkUrl}
      alt=""
      className="shrink-0"
      aria-hidden
      width="40"
      height="40"
      style={{ display: "block" }}
    />
  );
}
