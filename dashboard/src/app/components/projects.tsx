import {
  Archive,
  CircleStop,
  FileText,
  Play,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Card, KPI, Pill, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import {
  dashboardSummary,
  projects,
  StrategyProject,
  ProjectEvidenceStatus,
} from "./data";
import { getDashboardJson, postDashboardJson } from "./runtime";
import { applyDashboardCatalog } from "./data";

const stateColor: Record<
  StrategyProject["state"],
  "green" | "orange" | "pink" | "cyan" | "paper" | "black" | "purple"
> = {
  idea: "paper",
  draft: "paper",
  researching: "cyan",
  iterating: "purple",
  candidate: "orange",
  paper_review: "cyan",
  active_paper: "green",
  retired: "paper",
  blocked: "pink",
};

export function ProjectsView({
  onSelect,
}: {
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting={`Strategy Console · ${dashboardSummary.projectCount} projects`}
        headline="Projects"
        meta="User-facing strategy projects with current state, evidence tracks, blockers, next action and linked StrategySpec artifacts."
        stat={{
          label: "Blocked / iterating",
          value: `${dashboardSummary.projectBlockedCount} / ${dashboardSummary.projectIteratingCount}`,
          delta: `${dashboardSummary.projectCandidateCount} candidate · ${dashboardSummary.projectActivePaperCount} active paper`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3">
          <KPI
            label="Projects"
            value={String(dashboardSummary.projectCount)}
            accent="black"
          />
        </div>
        <div className="col-span-3">
          <KPI
            label="Blocked"
            value={String(dashboardSummary.projectBlockedCount)}
            accent="pink"
          />
        </div>
        <div className="col-span-3">
          <KPI
            label="Iterating"
            value={String(dashboardSummary.projectIteratingCount)}
            accent="purple"
          />
        </div>
        <div className="col-span-3">
          <KPI
            label="Active paper"
            value={String(dashboardSummary.projectActivePaperCount)}
            accent="green"
          />
        </div>
      </div>

      <Card pad={false}>
        <div
          className="overflow-hidden"
          style={{ borderRadius: "var(--r-xl)" }}
        >
          <table
            className="w-full t-body-sm"
            style={{ borderCollapse: "separate", borderSpacing: 0 }}
          >
            <thead>
              <tr
                className="hairline-b"
                style={{ background: "var(--paper-4)" }}
              >
                <th className="text-left px-5 py-2.5 t-caption ink-muted">
                  Project
                </th>
                <th className="text-left t-caption ink-muted">State</th>
                <th className="text-left t-caption ink-muted">Evidence</th>
                <th className="text-left t-caption ink-muted">Gates</th>
                <th className="text-left t-caption ink-muted">Blocker</th>
                <th className="text-left pr-5 t-caption ink-muted">
                  Next action
                </th>
              </tr>
            </thead>
            <tbody>
              {projects.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 t-body-sm ink-muted">
                    No StrategyProject records are present. Use Build to create
                    one or rebuild the catalog for legacy StrategySpec fallback.
                  </td>
                </tr>
              ) : (
                projects.map((project) => (
                  <tr
                    key={project.projectId}
                    onClick={() => onSelect?.(project.projectId)}
                    className="hairline-b last:border-b-0 hover:bg-[var(--paper-4)] transition-colors cursor-pointer"
                  >
                    <td className="px-5 py-3 max-w-[300px]">
                      <div className="t-title-sm truncate">{project.name}</div>
                      <div className="t-body-xs ink-subtle truncate mt-0.5">
                        {project.thesis ||
                          project.currentSpecPath ||
                          "No thesis yet"}
                      </div>
                      {project.importedFromStrategy && (
                        <div className="t-caption ink-muted mt-1">
                          legacy fallback
                        </div>
                      )}
                    </td>
                    <td>
                      <Tag color={stateColor[project.state]}>
                        {project.state}
                      </Tag>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1.5">
                        <EvidenceBadge
                          label="Factor"
                          status={project.evidence.factorQuality.status}
                        />
                        <EvidenceBadge
                          label="Exec"
                          status={project.evidence.executionReality.status}
                        />
                        <EvidenceBadge
                          label="Alt/LLM"
                          status={project.evidence.altLLMEvidence.status}
                        />
                      </div>
                    </td>
                    <td className="t-body-xs ink-subtle">
                      <GateLine project={project} />
                    </td>
                    <td
                      className="max-w-[220px] truncate"
                      title={project.blockers.join(", ") || "none"}
                    >
                      {project.blockers[0] ??
                        project.gateSummary.blockedChecks[0] ??
                        "none"}
                    </td>
                    <td
                      className="pr-5 max-w-[240px] truncate"
                      title={project.nextAction}
                    >
                      {project.nextAction || "review_project"}
                    </td>
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

export function ProjectDetail({
  id,
  onOpenStrategy,
}: {
  id: string;
  onOpenStrategy?: (id: string) => void;
}) {
  const project = projects.find((item) => item.projectId === id);
  const [status, setStatus] = useState(
    "Project actions write lightweight state to project.yaml.",
  );
  const [busy, setBusy] = useState(false);
  if (!project) {
    return (
      <div className="px-6 pb-8">
        <Card>No project found for {id}.</Card>
      </div>
    );
  }

  const runAction = async (
    action: "continue" | "stop" | "archive" | "paper_review",
  ) => {
    setBusy(true);
    setStatus(`Applying ${action}...`);
    try {
      await postDashboardJson(`/api/projects/${project.projectId}/state`, {
        action,
      });
      const catalog = await getDashboardJson<
        Parameters<typeof applyDashboardCatalog>[0]
      >("/api/dashboard/catalog");
      applyDashboardCatalog(catalog);
      setStatus("Project state updated.");
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Project action failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-6 pb-8 space-y-3">
      <div className="dscard p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Tag color={stateColor[project.state]}>{project.state}</Tag>
              <span className="t-caption ink-muted">{project.projectId}</span>
            </div>
            <h1 className="t-title-xl mt-2 truncate">{project.name}</h1>
            <p className="t-body-sm ink-subtle mt-1 max-w-3xl">
              {project.thesis || "No thesis recorded."}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              className="pill pill-primary"
              disabled={busy}
              onClick={() => void runAction("continue")}
            >
              <Play size={13} /> Continue
            </button>
            <button
              className="pill pill-secondary"
              disabled={busy}
              onClick={() => void runAction("paper_review")}
            >
              <ShieldCheck size={13} /> Paper review
            </button>
            <button
              className="pill pill-secondary"
              disabled={busy}
              onClick={() => void runAction("stop")}
            >
              <CircleStop size={13} /> Stop
            </button>
            <button
              className="pill pill-secondary"
              disabled={busy}
              onClick={() => void runAction("archive")}
            >
              <Archive size={13} /> Archive
            </button>
          </div>
        </div>
        <div className="t-body-sm ink-subtle mt-3">{status}</div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4">
          <SectionTitle tick="ink">Summary</SectionTitle>
          <InfoRows
            rows={[
              ["Spec", project.currentSpecPath ?? "n/a"],
              ["Latest run", project.latestRunPath ?? "n/a"],
              ["Next action", project.nextAction || "review_project"],
              ["Paper", project.paperStatus],
            ]}
          />
          {project.currentSpecPath && (
            <div className="mt-4">
              <Pill onClick={() => onOpenStrategy?.(project.name)}>
                <FileText size={12} /> Open spec view
              </Pill>
            </div>
          )}
        </Card>

        <Card className="col-span-4">
          <SectionTitle tick="orange">Gates</SectionTitle>
          <InfoRows
            rows={[
              ["Workflow", gateText(project.gateSummary.workflowPass)],
              ["Research", gateText(project.gateSummary.researchPass)],
              [
                "LLM contribution",
                gateText(project.gateSummary.llmContributionPass),
              ],
              ["Paper ready", gateText(project.gateSummary.paperReadyPass)],
            ]}
          />
        </Card>

        <Card className="col-span-4">
          <SectionTitle tick="purple">Iteration</SectionTitle>
          <InfoRows
            rows={[
              ["Round", `${project.currentRound} / ${project.maxRounds}`],
              ["Mode", project.iterationMode],
              ["Stop", project.stopReason ?? "not stopped"],
              ["User stop", project.userRequestedStop ? "requested" : "no"],
            ]}
          />
        </Card>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-4">
          <SectionTitle tick="black">Artifact State</SectionTitle>
          <InfoRows
            rows={[
              ["Last step", project.artifactState.lastSuccessfulStep],
              [
                "Artifacts",
                String(
                  Object.keys(project.artifactState.latestArtifacts).length,
                ),
              ],
              ["Blocked", String(project.artifactState.blockedItems.length)],
              ["Warnings", String(project.artifactState.warningItems.length)],
            ]}
          />
          <BulletList
            items={Object.entries(project.artifactState.latestArtifacts)
              .slice(0, 5)
              .map(([key, value]) => `${key}: ${value}`)}
            empty="No artifact state has been written."
            compact
          />
        </Card>

        <Card className="col-span-4">
          <SectionTitle tick="purple">Run Ledger</SectionTitle>
          <InfoRows
            rows={[
              ["Status", project.latestRunSummary?.status ?? "n/a"],
              [
                "Round",
                project.latestRunSummary?.round === null ||
                project.latestRunSummary?.round === undefined
                  ? "n/a"
                  : String(project.latestRunSummary.round),
              ],
              ["Task", project.latestRunSummary?.taskType ?? "n/a"],
              [
                "Steps",
                String(project.latestRunSummary?.stepEvents.length ?? 0),
              ],
            ]}
          />
          <BulletList
            items={
              project.latestRunSummary?.stepEvents
                .slice(0, 5)
                .map((step) => `${step.stepName}: ${step.status}`) ?? []
            }
            empty="No run ledger has been written."
            compact
          />
        </Card>

        <Card className="col-span-4">
          <SectionTitle tick="orange">Next Minimal Actions</SectionTitle>
          <BulletList
            items={project.nextMinimalActions}
            empty="No next minimal action recorded."
            compact
          />
          <div className="mt-4">
            <SectionTitle tick="pink">Do Not Repeat</SectionTitle>
            <BulletList
              items={project.doNotRepeat}
              empty="No repeated blocker recorded."
              compact
            />
          </div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle
            tick="cyan"
            hint="Evidence is status, artifact and blocker oriented; unknown is never treated as pass."
          >
            Project Evidence
          </SectionTitle>
        </div>
        <div className="grid grid-cols-3 divide-x divide-[var(--hairline)]">
          <EvidencePanel
            title="Factor Quality"
            item={project.evidence.factorQuality}
          />
          <EvidencePanel
            title="Execution Reality"
            item={project.evidence.executionReality}
          />
          <EvidencePanel
            title="Alt/LLM Evidence"
            item={project.evidence.altLLMEvidence}
          />
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-6">
          <SectionTitle tick="pink">Blockers</SectionTitle>
          <BulletList
            items={[
              ...project.blockers,
              ...project.gateSummary.blockedChecks,
              ...(project.blockerSummary?.rootBlockers ?? []),
            ]}
            empty="No blockers recorded."
          />
        </Card>
        <Card className="col-span-6">
          <SectionTitle tick="orange">Audit</SectionTitle>
          <InfoRows
            rows={[
              ["Project file", `projects/${project.projectId}/project.yaml`],
              [
                "Artifact state",
                `projects/${project.projectId}/artifact-state.json`,
              ],
              [
                "Imported",
                project.importedFromStrategy
                  ? "legacy StrategySpec fallback"
                  : "project.yaml",
              ],
              ["Failed step", project.blockerSummary?.failedStep ?? "n/a"],
              ["Created", project.createdAt ?? "n/a"],
              ["Updated", project.updatedAt ?? "n/a"],
            ]}
          />
        </Card>
      </div>
    </div>
  );
}

function EvidencePanel({
  title,
  item,
}: {
  title: string;
  item: StrategyProject["evidence"]["factorQuality"];
}) {
  return (
    <div className="p-5 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <div className="t-title-sm truncate">{title}</div>
        <EvidenceBadge label="" status={item.status} />
      </div>
      <p className="t-body-sm ink-subtle mt-3 leading-snug">{item.summary}</p>
      <div
        className="t-mono ink-subtle mt-3 truncate"
        title={item.artifactPath ?? "No artifact"}
      >
        {item.artifactPath ?? "No artifact linked"}
      </div>
      <BulletList items={item.blockers} empty="No evidence blocker." compact />
    </div>
  );
}

function EvidenceBadge({
  label,
  status,
}: {
  label: string;
  status: ProjectEvidenceStatus;
}) {
  const color =
    status === "ok"
      ? "green"
      : status === "blocked"
        ? "pink"
        : status === "warning"
          ? "orange"
          : status === "not_applicable"
            ? "paper"
            : "black";
  return <Tag color={color}>{label ? `${label}: ${status}` : status}</Tag>;
}

function GateLine({ project }: { project: StrategyProject }) {
  return (
    <span>
      wf {gateText(project.gateSummary.workflowPass)} · res{" "}
      {gateText(project.gateSummary.researchPass)} · paper{" "}
      {gateText(project.gateSummary.paperReadyPass)}
    </span>
  );
}

function gateText(value: boolean | null) {
  if (value === true) return "pass";
  if (value === false) return "fail";
  return "unknown";
}

function InfoRows({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="mt-4 space-y-2">
      {rows.map(([label, value]) => (
        <div
          key={label}
          className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 py-1.5 hairline-b"
        >
          <span className="t-body-sm ink-subtle">{label}</span>
          <span className="t-body-sm ink truncate" title={value}>
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

function BulletList({
  items,
  empty,
  compact = false,
}: {
  items: string[];
  empty: string;
  compact?: boolean;
}) {
  const filtered = Array.from(new Set(items.filter(Boolean)));
  return (
    <div className={compact ? "mt-3 space-y-1" : "mt-4 space-y-2"}>
      {filtered.length === 0 ? (
        <div className="t-body-sm ink-subtle">{empty}</div>
      ) : (
        filtered.map((item) => (
          <div key={item} className="flex items-start gap-2 t-body-sm">
            <Send size={compact ? 10 : 12} className="mt-1 shrink-0" />
            <span className="ink-subtle">{item}</span>
          </div>
        ))
      )}
    </div>
  );
}
