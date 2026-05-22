import { FormEvent, useState } from "react";
import { Bot, CheckCircle2, FilePlus2, Send } from "lucide-react";
import { Card, KPI, Pill, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import { getDashboardJson, postDashboardJson } from "./runtime";
import { applyDashboardCatalog } from "./data";

type Template = {
  id: string;
  name: string;
  thesis: string;
  idea: string;
  tag: string;
};

const templates: Template[] = [
  {
    id: "qqq-momentum",
    name: "QQQ Trend / Momentum",
    thesis: "Follow QQQ trend or intraday momentum with bounded drawdown and simple execution.",
    idea: "Create a QQQ trend or momentum StrategySpec with bounded parameter ranges, benchmark family, Factor Quality, Execution Reality, and no paper readiness claim until gates pass.",
    tag: "single-symbol",
  },
  {
    id: "sector-rotation",
    name: "Sector / Theme Rotation",
    thesis: "Rotate across ETFs or a constrained stock universe using transparent factors and turnover control.",
    idea: "Create a sector or theme rotation StrategySpec with bounded factor variants, candidate budget, benchmark family, Factor Quality, Execution Reality, and capacity review.",
    tag: "rotation",
  },
  {
    id: "risk-switch",
    name: "Equity / Bond Risk Switch",
    thesis: "Switch exposure between risk assets and defensive assets based on regime or trend evidence.",
    idea: "Create a SPY or QQQ versus TLT risk-switch StrategySpec with simple regime factors, OOS validation, cost sensitivity, and clear paper-readiness blockers.",
    tag: "allocation",
  },
];

export function BuildView() {
  const [selected, setSelected] = useState<Template | null>(templates[0]);
  const [name, setName] = useState(templates[0].name);
  const [thesis, setThesis] = useState(templates[0].thesis);
  const [idea, setIdea] = useState(templates[0].idea);
  const [maxRounds, setMaxRounds] = useState(5);
  const [useLLM, setUseLLM] = useState(false);
  const [status, setStatus] = useState("Select a template or write a strategy idea. Clear ideas create a project directly; vague ideas should be refined before submission.");
  const [busy, setBusy] = useState(false);

  const choose = (template: Template) => {
    setSelected(template);
    setName(template.name);
    setThesis(template.thesis);
    setIdea(template.idea);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = missingFields(name, thesis, idea);
    if (missing.length > 0) {
      setStatus(`Clarify before creating: ${missing.join(", ")}.`);
      return;
    }
    setBusy(true);
    setStatus("Creating StrategyProject and agent request...");
    try {
      const response = await postDashboardJson<{
        project_path: string;
        context_path: string;
        agent_request_path?: string;
      }>("/api/projects", {
        name,
        thesis,
        idea,
        template_id: selected?.id ?? null,
        max_rounds: maxRounds,
        use_llm: useLLM,
        tags: selected ? [selected.tag] : [],
      });
      const catalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
        "/api/dashboard/catalog",
      );
      applyDashboardCatalog(catalog);
      setStatus(`Created ${response.project_path}; context ${response.context_path}; request ${response.agent_request_path ?? "not created"}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Project creation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting="Build · StrategyProject"
        headline="New Strategy"
        meta="Create a persistent project, compile worker context, and open an agent request without asking the user to re-explain the repository."
        stat={{ label: "Default rounds", value: String(maxRounds), delta: "auto until stop" }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Fast path" value="Direct" delta="clear idea" accent="green" /></div>
        <div className="col-span-3"><KPI label="Clarify path" value="1-2" delta="missing fields" accent="orange" /></div>
        <div className="col-span-3"><KPI label="Evidence" value="3 tracks" delta="Factor / Exec / Alt-LLM" accent="cyan" /></div>
        <div className="col-span-3"><KPI label="Paper" value="Gated" delta="no auto live writes" accent="black" /></div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="green">Starter templates</SectionTitle>
          </div>
          <div className="p-3 space-y-2">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => choose(template)}
                className={`w-full text-left p-3 transition-colors ${selected?.id === template.id ? "bg-[#0A0A0A] text-white" : "bg-[var(--paper-3)] hover:bg-[var(--paper-4)] ink"}`}
                style={{ borderRadius: "var(--r-md)" }}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="t-title-sm">{template.name}</div>
                  <Tag color={selected?.id === template.id ? "white" : "paper"}>{template.tag}</Tag>
                </div>
                <div className={`t-body-sm mt-2 leading-snug ${selected?.id === template.id ? "text-white/70" : "ink-subtle"}`}>
                  {template.thesis}
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="col-span-8">
          <SectionTitle tick="cyan" hint={status}>Project request</SectionTitle>
          <form className="mt-4 space-y-3" onSubmit={submit}>
            <label className="block">
              <span className="t-caption ink-muted">Project name</span>
              <input className="ds-input mt-1 w-full h-10 px-3 t-body-sm" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="block">
              <span className="t-caption ink-muted">Thesis</span>
              <input className="ds-input mt-1 w-full h-10 px-3 t-body-sm" value={thesis} onChange={(event) => setThesis(event.target.value)} />
            </label>
            <label className="block">
              <span className="t-caption ink-muted">Natural language request</span>
              <textarea
                className="ds-input mt-1 w-full min-h-[132px] px-3 py-2 t-body-sm"
                value={idea}
                onChange={(event) => setIdea(event.target.value)}
              />
            </label>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 t-body-sm ink-subtle">
                <span>Max rounds</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={maxRounds}
                  onChange={(event) => setMaxRounds(Number(event.target.value))}
                  className="ds-input w-16 h-9 px-2 t-num"
                />
              </label>
              <label className="flex items-center gap-2 t-body-sm ink-subtle">
                <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                Allow LLM/news/alternative-data evidence if the spec needs it
              </label>
              <div className="ml-auto flex gap-2">
                <Pill variant="ghost" onClick={() => {
                  setSelected(null);
                  setName("");
                  setThesis("");
                  setIdea("");
                }}>
                  <Bot size={12} /> Blank
                </Pill>
                <button className="pill pill-primary" disabled={busy}>
                  {busy ? <CheckCircle2 size={13} /> : <FilePlus2 size={13} />}
                  Create project
                </button>
              </div>
            </div>
          </form>
        </Card>
      </div>

      <Card>
        <SectionTitle tick="orange">Worker handoff</SectionTitle>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            ["Context", "projects/{project}/context.md gives the worker project memory, spec path and evidence requirements."],
            ["Evidence", "Factor Quality, Execution Reality and Alt/LLM Evidence are required as project evidence states."],
            ["Boundary", "The worker can research and edit specs; paper orders remain gated product actions."],
          ].map(([title, body]) => (
            <div key={title} className="bg-[var(--paper-3)] p-3" style={{ borderRadius: "var(--r-md)" }}>
              <div className="flex items-center gap-2 t-title-sm"><Send size={12} /> {title}</div>
              <div className="t-body-sm ink-subtle mt-2 leading-snug">{body}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function missingFields(name: string, thesis: string, idea: string) {
  const missing: string[] = [];
  if (!name.trim()) missing.push("project name");
  if (!thesis.trim()) missing.push("thesis");
  if (!idea.trim()) missing.push("request");
  const text = `${name} ${thesis} ${idea}`.toLowerCase();
  if (!/(qqq|spy|tlt|iwm|sector|theme|etf|stock|universe|symbol)/.test(text)) {
    missing.push("tradable symbol or universe");
  }
  if (!/(day|daily|1m|5m|15m|hour|intraday|weekly|timeframe|周期)/.test(text)) {
    missing.push("timeframe");
  }
  return missing;
}
