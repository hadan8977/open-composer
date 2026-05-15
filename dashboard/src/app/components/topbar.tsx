import { Search, Plus, Bell, ChevronLeft } from "lucide-react";
import { dashboardSummary } from "./data";
import type { DashboardCatalogSyncState } from "./runtime";

export function TopBar({
  back,
  onBack,
  deploymentMode = "Local",
  owner,
  onLogout,
  onNotifications,
  catalogSync,
}: {
  back?: string;
  onBack?: () => void;
  deploymentMode?: "Local" | "Remote Commands Enabled";
  owner?: string | null;
  onLogout?: () => Promise<void>;
  onNotifications?: () => void;
  catalogSync?: DashboardCatalogSyncState;
}) {
  const catalogLabel =
    catalogSync?.status === "error"
      ? `catalog error · ${catalogSync.error ?? "unknown"}`
      : catalogSync?.lastSyncedAt
        ? `catalog synced · ${new Date(catalogSync.lastSyncedAt).toLocaleTimeString()}`
        : `catalog v${dashboardSummary.readModelVersion}`;
  return (
    <header className="px-6 pt-4 pb-3 hairline-b">
      <div className="flex items-center gap-3">
        {back ? (
          <button onClick={onBack} className="pill pill-secondary">
            <ChevronLeft size={14} strokeWidth={2.2} /> {back}
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span
              className="block-green inline-block"
              style={{ width: 8, height: 8, borderRadius: 2 }}
            />
            <div className="t-caption ink-muted">DASHBOARD · {catalogLabel}</div>
          </div>
        )}

        <label className="ds-input ml-auto flex items-center gap-2 w-80 h-9 px-3.5">
          <Search size={14} className="ink-subtle shrink-0" strokeWidth={2.2} />
          <input
            placeholder="Search strategies, versions, signals…"
            className="bg-transparent outline-none flex-1 t-body-md placeholder:text-[#9A988F]"
          />
          <kbd
            className="t-num ink-subtle inline-flex items-center justify-center bg-[#EEF2F7]"
            style={{ borderRadius: 3, fontSize: 10, fontWeight: 600, height: 18, padding: "0 5px" }}
          >⌘K</kbd>
        </label>

        <button
          className="relative pill pill-secondary"
          style={{ width: 36, padding: 0, justifyContent: "center" }}
          aria-label="Notifications"
          onClick={onNotifications}
        >
          <Bell size={15} strokeWidth={2.0} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-[#FF2D7A]" />
        </button>

        <span className="pill pill-secondary">
          {deploymentMode}
          {owner ? ` · ${owner}` : ""}
        </span>
        {onLogout && (
          <button className="pill pill-secondary" onClick={() => void onLogout()}>
            Logout
          </button>
        )}

        <button className="pill pill-primary opacity-70" disabled title="Use the CLI workflow to create or modify StrategySpecs.">
          <Plus size={14} strokeWidth={2.6} /> CLI gated
        </button>
      </div>
    </header>
  );
}
