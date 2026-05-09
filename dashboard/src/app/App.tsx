import { useState } from "react";
import { Sidebar, NavKey } from "./components/sidebar";
import { TopBar } from "./components/topbar";
import { Overview } from "./components/overview";
import { Library } from "./components/library";
import { Versions, Paper, Events, LLM, Groups, Audit } from "./components/sections";
import { StrategyDetail } from "./components/strategy-detail";
import { StatusFooter } from "./components/footer";

export default function App() {
  const [tab, setTab] = useState<NavKey>("overview");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);

  const handleNav = (key: NavKey) => {
    setSelectedStrategyId(null);
    setTab(key);
  };

  return (
    <div className="size-full flex bg-paper">
      <Sidebar active={tab} onChange={handleNav} />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0 hairline-l">
        <TopBar
          back={selectedStrategyId ? "Library" : undefined}
          onBack={selectedStrategyId ? () => setSelectedStrategyId(null) : undefined}
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
              </>
            )}
          </div>
          <StatusFooter />
        </div>
      </main>
    </div>
  );
}
