import { useState } from "react";
import type { FormEvent } from "react";
import { Sidebar, NavKey } from "./components/sidebar";
import { TopBar } from "./components/topbar";
import { Overview } from "./components/overview";
import { Library } from "./components/library";
import { ActivityView, ResearchView } from "./components/sections";
import { StrategyDetail } from "./components/strategy-detail";
import { BuildView } from "./components/build";
import { FactorCatalogView } from "./components/factors";
import { LiveView } from "./components/live";
import { ProjectDetail, ProjectsView } from "./components/projects";
import { StatusFooter } from "./components/footer";
import { SettingsView } from "./components/settings";
import { Card } from "./components/blocks";
import { dashboardSummary } from "./components/data";
import {
  loginDashboard,
  useDashboardCatalogSync,
  useDashboardSession,
} from "./components/runtime";

export default function App() {
  const catalogSync = useDashboardCatalogSync();
  const session = useDashboardSession();
  const [tab, setTab] = useState<NavKey>("overview");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(
    null,
  );
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null,
  );

  const handleNav = (key: NavKey) => {
    setSelectedStrategyId(null);
    setSelectedProjectId(null);
    setTab(key);
  };
  const emptyWorkspace =
    dashboardSummary.strategyCount === 0 &&
    dashboardSummary.projectCount === 0 &&
    dashboardSummary.runCount === 0;

  if (session.loading) {
    return <RemoteGate status="Checking session" />;
  }

  if (session.remote && !session.authenticated) {
    return (
      <RemoteLogin onAuthenticated={session.refresh} error={session.error} />
    );
  }

  return (
    <div className="size-full flex bg-paper">
      <Sidebar active={tab} onChange={handleNav} catalogSync={catalogSync} />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0 hairline-l">
        <TopBar
          back={
            selectedStrategyId
              ? "Strategy"
              : selectedProjectId
                ? "Projects"
                : undefined
          }
          onBack={
            selectedStrategyId
              ? () => setSelectedStrategyId(null)
              : selectedProjectId
                ? () => setSelectedProjectId(null)
                : undefined
          }
          deploymentMode={session.remote ? "Remote Commands Enabled" : "Local"}
          owner={session.owner}
          onLogout={session.remote ? session.logout : undefined}
          onNotifications={() => handleNav("activity")}
          catalogSync={catalogSync}
        />
        <div className="flex-1 overflow-auto flex flex-col">
          <div className="flex-1 pt-3">
            {selectedStrategyId ? (
              <StrategyDetail id={selectedStrategyId} />
            ) : selectedProjectId ? (
              <ProjectDetail
                id={selectedProjectId}
                onOpenStrategy={(id) => {
                  setSelectedProjectId(null);
                  setSelectedStrategyId(id);
                }}
              />
            ) : (
              <>
                {tab === "overview" && (
                  emptyWorkspace ? <OnboardingHero onBuild={() => handleNav("build")} /> : <Overview />
                )}
                {tab === "projects" && (
                  <ProjectsView onSelect={(id) => setSelectedProjectId(id)} />
                )}
                {tab === "build" && <BuildView />}
                {tab === "live" && <LiveView />}
                {tab === "research" && <ResearchView />}
                {tab === "activity" && <ActivityView />}
                {tab === "catalog" && (
                  <Library onSelect={(id) => setSelectedStrategyId(id)} />
                )}
                {tab === "factors" && <FactorCatalogView />}
                {tab === "settings" && <SettingsView />}
              </>
            )}
          </div>
          <StatusFooter />
        </div>
      </main>
    </div>
  );
}

function OnboardingHero({ onBuild }: { onBuild: () => void }) {
  return (
    <div className="px-6 pb-8 space-y-3">
      <section
        className="relative overflow-hidden bg-white"
        style={{ borderRadius: "var(--r-xl)", boxShadow: "var(--e2)" }}
      >
        <span aria-hidden className="absolute inset-y-0 left-0 w-1 bg-[#1FB85A]" />
        <div className="p-7 md:p-8">
          <div className="t-caption ink-subtle">WELCOME TO OPEN COMPOSER</div>
          <h1
            className="mt-2"
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 800,
              fontSize: "clamp(36px, 5vw, 70px)",
              lineHeight: 0.98,
              letterSpacing: 0,
            }}
          >
            Build your first strategy
          </h1>
          <p className="t-body-md ink-muted mt-4 max-w-3xl">
            Start from a sample idea, create a Strategy Project, then continue research from the Strategy Detail workbench. Files remain the source of truth, but ordinary workflow starts here.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-6">
            <StartCard
              title="Try a sample"
              body="Use sample data and a bounded QQQ idea to see the full evidence loop."
              action="Open Build"
              onClick={onBuild}
            />
            <StartCard
              title="Build from idea"
              body="Describe the thesis, choose pure quant or LLM-assisted, and create a project."
              action="Create Draft"
              onClick={onBuild}
            />
            <StartCard
              title="Import YAML"
              body="Place a StrategySpec in strategy_specs/drafts and rebuild the catalog."
              action="Use Catalog"
              onClick={onBuild}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

function StartCard({
  title,
  body,
  action,
  onClick,
}: {
  title: string;
  body: string;
  action: string;
  onClick: () => void;
}) {
  return (
    <Card>
      <div className="t-title-md">{title}</div>
      <div className="t-body-sm ink-subtle mt-2 min-h-[44px]">{body}</div>
      <button className="pill pill-primary mt-4" onClick={onClick}>{action}</button>
    </Card>
  );
}

function RemoteGate({ status }: { status: string }) {
  return (
    <div className="size-full grid place-items-center bg-paper">
      <div className="dscard w-full max-w-sm p-6">
        <div className="t-caption ink-muted">OPEN COMPOSER</div>
        <div className="t-title-lg mt-2">{status}</div>
      </div>
    </div>
  );
}

function RemoteLogin({
  onAuthenticated,
  error,
}: {
  onAuthenticated: () => Promise<void>;
  error: string | null;
}) {
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState(error ?? "");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      await loginDashboard(password);
      await onAuthenticated();
    } catch (loginError) {
      setStatus(
        loginError instanceof Error ? loginError.message : "Login failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="size-full grid place-items-center bg-paper px-4">
      <form className="dscard w-full max-w-sm p-6 space-y-4" onSubmit={submit}>
        <div>
          <div className="t-caption ink-muted">REMOTE DASHBOARD</div>
          <h1 className="t-title-lg mt-2">Open Composer</h1>
        </div>
        <label className="ds-input flex items-center h-11 px-3">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="bg-transparent outline-none flex-1 t-body-md"
            placeholder="Dashboard password"
          />
        </label>
        <button
          className="pill pill-primary w-full justify-center"
          disabled={busy || !password}
        >
          {busy ? "Signing in" : "Sign in"}
        </button>
        {status && <div className="t-body-sm ink-subtle">{status}</div>}
      </form>
    </div>
  );
}
