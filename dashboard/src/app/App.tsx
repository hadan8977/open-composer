import { useState } from "react";
import type { FormEvent } from "react";
import { Sidebar, NavKey } from "./components/sidebar";
import { TopBar } from "./components/topbar";
import { Overview } from "./components/overview";
import { Library } from "./components/library";
import { Versions, Paper, Events, LLM, Groups, Audit } from "./components/sections";
import { StrategyDetail } from "./components/strategy-detail";
import { Notifications } from "./components/notifications";
import { StatusFooter } from "./components/footer";
import { loginDashboard, useDashboardCatalogSync, useDashboardSession } from "./components/runtime";

export default function App() {
  const catalogSync = useDashboardCatalogSync();
  const session = useDashboardSession();
  const [tab, setTab] = useState<NavKey>("overview");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);

  const handleNav = (key: NavKey) => {
    setSelectedStrategyId(null);
    setTab(key);
  };

  if (session.loading) {
    return <RemoteGate status="Checking session" />;
  }

  if (session.remote && !session.authenticated) {
    return <RemoteLogin onAuthenticated={session.refresh} error={session.error} />;
  }

  return (
    <div className="size-full flex bg-paper">
      <Sidebar active={tab} onChange={handleNav} catalogSync={catalogSync} />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0 hairline-l">
        <TopBar
          back={selectedStrategyId ? "Library" : undefined}
          onBack={selectedStrategyId ? () => setSelectedStrategyId(null) : undefined}
          deploymentMode={session.remote ? "Remote Commands Enabled" : "Local"}
          owner={session.owner}
          onLogout={session.remote ? session.logout : undefined}
          onNotifications={() => handleNav("notifications")}
          catalogSync={catalogSync}
        />
        <div className="flex-1 overflow-auto flex flex-col">
          <div className="flex-1 pt-3">
            {selectedStrategyId ? (
              <StrategyDetail id={selectedStrategyId} />
            ) : (
              <>
                {tab === "overview"   && <Overview />}
                {tab === "strategies" && <Library onSelect={(id) => setSelectedStrategyId(id)} />}
                {tab === "versions"   && <Versions />}
                {tab === "paper"      && <Paper />}
                {tab === "events"     && <Events />}
                {tab === "llm"        && <LLM />}
                {tab === "groups"     && <Groups />}
                {tab === "audit"      && <Audit />}
                {tab === "notifications" && <Notifications />}
              </>
            )}
          </div>
          <StatusFooter />
        </div>
      </main>
    </div>
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
      setStatus(loginError instanceof Error ? loginError.message : "Login failed.");
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
        <button className="pill pill-primary w-full justify-center" disabled={busy || !password}>
          {busy ? "Signing in" : "Sign in"}
        </button>
        {status && <div className="t-body-sm ink-subtle">{status}</div>}
      </form>
    </div>
  );
}
