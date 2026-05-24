import { useEffect, useState } from "react";
import { RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import { getDashboardJson, postDashboardJson } from "./runtime";

type EnvironmentPayload = {
  schema_version: number;
  generated_at: string;
  status: "ok" | "warning" | "blocked" | string;
  root: string;
  serve_root: string;
  auth_required: boolean;
  sections: Array<{
    section: string;
    title: string;
    items: Array<{
      name: string;
      status: "ok" | "warning" | "blocked" | string;
      detail: string;
      required: boolean;
      next_action?: string;
    }>;
  }>;
  blocked_items: string[];
  warning_items: string[];
  notes: string[];
};

type CapabilitiesPayload = {
  registry_version: number;
  evaluation_path: string | null;
  capabilities: Array<Record<string, any>>;
};

type AgentBackendPayload = {
  backend: string;
  configured_backend: string;
  available: string[];
  project_statuses: Array<Record<string, any>>;
};

export function SettingsView() {
  const [environment, setEnvironment] = useState<EnvironmentPayload | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesPayload | null>(null);
  const [backend, setBackend] = useState<AgentBackendPayload | null>(null);
  const [status, setStatus] = useState("Loading settings.");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setBusy(true);
    setStatus("Refreshing settings.");
    try {
      const [env, caps, agent] = await Promise.all([
        getDashboardJson<EnvironmentPayload>("/api/settings/environment"),
        getDashboardJson<CapabilitiesPayload>("/api/settings/capabilities"),
        getDashboardJson<AgentBackendPayload>("/api/settings/agent-backend"),
      ]);
      setEnvironment(env);
      setCapabilities(caps);
      setBackend(agent);
      setStatus("Settings loaded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Settings refresh failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const items = environment?.sections.flatMap((section) => section.items) ?? [];
  const okCount = items.filter((item) => item.status === "ok").length;
  const warningCount = items.filter((item) => item.status === "warning").length;
  const blockedCount = items.filter((item) => item.status === "blocked").length;

  const testCapabilities = async () => {
    setBusy(true);
    try {
      await postDashboardJson("/api/settings/capabilities/test", {});
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const switchBackend = async (value: string) => {
    if (value !== backend?.backend && !confirmBackendSwitch(value)) {
      setStatus("Agent backend switch cancelled.");
      return;
    }
    setBusy(true);
    try {
      await postDashboardJson("/api/settings/agent-backend", { backend: value });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting="Settings · Environment"
        headline="Runtime Setup"
        meta={status}
        stat={{
          label: "Status",
          value: environment?.status ?? "loading",
          delta: `${blockedCount} blocked · ${warningCount} warnings`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Ready" value={String(okCount)} accent="green" /></div>
        <div className="col-span-3"><KPI label="Warnings" value={String(warningCount)} accent="orange" /></div>
        <div className="col-span-3"><KPI label="Blocked" value={String(blockedCount)} accent="pink" /></div>
        <div className="col-span-3"><KPI label="Backend" value={backend?.backend ?? "file_queue"} accent="cyan" /></div>
      </div>

      <Card>
        <SectionTitle
          tick="ink"
          hint={environment ? `${environment.root} · generated ${formatTimestamp(environment.generated_at)}` : "Environment status is not loaded yet."}
          action={<button className="pill pill-secondary" disabled={busy} onClick={() => void refresh()}><RefreshCw size={14} strokeWidth={2.2} /> Refresh</button>}
        >
          Environment Map
        </SectionTitle>
        <div className="mt-4 grid grid-cols-12 gap-3">
          {(environment?.sections ?? []).map((section) => (
            <div key={section.section} className="col-span-6 rounded-md hairline overflow-hidden">
              <div className="px-4 py-3 bg-[var(--paper-3)] hairline-b">
                <div className="t-title-sm">{section.title}</div>
              </div>
              <div className="divide-y divide-[var(--hairline)]">
                {section.items.map((item) => (
                  <div key={`${section.section}-${item.name}`} className="grid grid-cols-[minmax(0,1fr)_88px] gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        {item.status === "ok" ? <ShieldCheck size={14} strokeWidth={2.2} /> : <TriangleAlert size={14} strokeWidth={2.2} />}
                        <span className="t-body-sm ink truncate" style={{ fontWeight: 650 }}>{item.name}</span>
                      </div>
                      <div className="t-body-xs ink-subtle mt-1 truncate" title={item.detail}>{item.detail}</div>
                      {item.next_action && <div className="t-mono ink-subtle mt-2 truncate" title={item.next_action}>{item.next_action}</div>}
                    </div>
                    <div className="flex justify-end">
                      <Tag color={statusColor(item.status)}>{item.status}</Tag>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-6">
          <SectionTitle tick="orange" action={<button className="pill pill-secondary" disabled={busy} onClick={() => void testCapabilities()}>Re-evaluate</button>}>Capabilities</SectionTitle>
          <div className="mt-4 space-y-2">
            {(capabilities?.capabilities ?? []).map((item) => (
              <div key={item.id ?? item.capability_id} className="rounded-md bg-[var(--paper-3)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="t-title-sm">{item.id ?? item.capability_id}</span>
                  <Tag color={statusColor(item.evaluation?.passed ? "ok" : "warning")}>{item.evaluation?.passed ? "approved" : "trial"}</Tag>
                </div>
                <div className="t-body-xs ink-subtle mt-1">{item.provider ?? "provider n/a"} · {item.kind ?? "unknown"}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-3">
          <SectionTitle tick="purple">Agent Backend</SectionTitle>
          <div className="mt-4 space-y-2">
            {["file_queue", "codex_sdk"].map((item) => (
              <button key={item} className={`pill ${backend?.backend === item ? "pill-primary" : "pill-secondary"} w-full justify-start`} disabled={busy} onClick={() => void switchBackend(item)}>
                <Tag color={backend?.backend === item ? "white" : "paper"}>{backend?.backend === item ? "active" : "switch"}</Tag> {item}
              </button>
            ))}
          </div>
        </Card>

        <Card className="col-span-3">
          <SectionTitle tick="green">Notifications</SectionTitle>
          <div className="mt-4 space-y-2">
            {(environment?.notes ?? []).slice(0, 5).map((note) => (
              <div key={note} className="t-body-sm ink-subtle leading-snug">{note}</div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function confirmBackendSwitch(value: string) {
  return window.prompt(`Switch agent backend to ${value}?\n\nType exactly: SWITCH AGENT BACKEND`) === "SWITCH AGENT BACKEND";
}

function statusColor(status: string): "green" | "orange" | "pink" | "paper" {
  if (status === "ok") return "green";
  if (status === "blocked") return "pink";
  if (status === "warning") return "orange";
  return "paper";
}

function formatTimestamp(value: string): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
