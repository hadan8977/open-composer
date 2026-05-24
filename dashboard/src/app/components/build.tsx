import { FormEvent, useEffect, useState } from "react";
import { Bot, CheckCircle2, FilePlus2, Sparkles } from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import { getDashboardJson, postDashboardJson } from "./runtime";
import { applyDashboardCatalog } from "./data";

type BuildTemplate = {
  id: string;
  name: string;
  strategy_kind: "pure_quant" | "quant_with_llm_review" | "quant_with_llm_factor" | "router";
  thesis: string;
  idea: string;
  tag: string;
};

type BuildTemplatesPayload = {
  templates: BuildTemplate[];
  strategy_kinds: Array<{ id: string; label: string; description: string }>;
};

export function BuildView() {
  const [templates, setTemplates] = useState<BuildTemplate[]>([]);
  const [selected, setSelected] = useState<BuildTemplate | null>(null);
  const [strategyKind, setStrategyKind] = useState<BuildTemplate["strategy_kind"]>("pure_quant");
  const [name, setName] = useState("");
  const [thesis, setThesis] = useState("");
  const [idea, setIdea] = useState("");
  const [maxRounds, setMaxRounds] = useState(5);
  const [useLLM, setUseLLM] = useState(false);
  const [status, setStatus] = useState("Choose a template or write a new idea. Clear ideas can go straight into a project.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getDashboardJson<BuildTemplatesPayload>("/api/build/templates")
      .then((payload) => {
        setTemplates(payload.templates);
        const first = payload.templates[0] ?? null;
        setSelected(first);
        if (first) {
          setStrategyKind(first.strategy_kind);
          setName(first.name);
          setThesis(first.thesis);
          setIdea(first.idea);
        }
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : "Template load failed."));
  }, []);

  const choose = (template: BuildTemplate) => {
    setSelected(template);
    setStrategyKind(template.strategy_kind);
    setName(template.name);
    setThesis(template.thesis);
    setIdea(template.idea);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || !thesis.trim() || !idea.trim()) {
      setStatus("Fill name, thesis, and idea before creating a project.");
      return;
    }
    setBusy(true);
    setStatus("Creating draft spec and project.");
    try {
      const response = await postDashboardJson<Record<string, unknown>>("/api/build/draft", {
        name,
        thesis,
        idea,
        template_id: selected?.id ?? null,
        strategy_kind: strategyKind,
        max_rounds: maxRounds,
        use_llm: useLLM,
      });
      const catalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
        "/api/dashboard/catalog",
      );
      applyDashboardCatalog(catalog);
      setStatus(
        `Created ${String(response.project_path ?? "project")}; queued ${String(
          response.queue_command_id ?? "n/a",
        )}.`,
      );
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
        meta="Create a persistent project, draft the first StrategySpec, and hand the work to the agent without forcing the user into CLI."
        stat={{ label: "Flow", value: "Build → Queue → Detail", delta: "Dashboard-first" }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Templates" value={String(templates.length)} accent="green" /></div>
        <div className="col-span-3"><KPI label="Strategy kind" value={strategyKind.replace(/_/g, " ")} accent="cyan" /></div>
        <div className="col-span-3"><KPI label="Rounds" value={String(maxRounds)} accent="orange" /></div>
        <div className="col-span-3"><KPI label="LLM" value={useLLM ? "On" : "Off"} accent={useLLM ? "purple" : "paper"} /></div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b"><SectionTitle tick="green">Starter templates</SectionTitle></div>
          <div className="p-3 space-y-2">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => choose(template)}
                className={`w-full text-left p-3 transition-colors ${
                  selected?.id === template.id ? "bg-[#0A0A0A] text-white" : "bg-[var(--paper-3)] hover:bg-[var(--paper-4)] ink"
                }`}
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
              <span className="t-caption ink-muted">Strategy kind</span>
              <select className="ds-input mt-1 w-full h-10 px-3 t-body-sm" value={strategyKind} onChange={(event) => setStrategyKind(event.target.value as BuildTemplate["strategy_kind"])}>
                <option value="pure_quant">Pure quant</option>
                <option value="quant_with_llm_review">Quant + LLM review</option>
                <option value="quant_with_llm_factor">Quant + LLM factor</option>
                <option value="router">Router</option>
              </select>
            </label>
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
                Allow LLM-assisted drafting
              </label>
              <div className="ml-auto flex gap-2">
                <button
                  type="button"
                  className="pill pill-secondary"
                  onClick={() => {
                    setSelected(null);
                    setName("");
                    setThesis("");
                    setIdea("");
                  }}
                >
                  <Bot size={12} /> Blank
                </button>
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
              <div className="flex items-center gap-2 t-title-sm"><Sparkles size={12} /> {title}</div>
              <div className="t-body-sm ink-subtle mt-2 leading-snug">{body}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
