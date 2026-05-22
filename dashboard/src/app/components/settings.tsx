import { useEffect, useState } from "react";
import { RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { Hero } from "./hero";
import { getDashboardJson } from "./runtime";

type EnvironmentItem = {
  name: string;
  status: "ok" | "warning" | "blocked" | string;
  detail: string;
  required: boolean;
  next_action?: string;
};

type EnvironmentSection = {
  section: string;
  title: string;
  items: EnvironmentItem[];
};

type EnvironmentPayload = {
  schema_version: number;
  generated_at: string;
  status: "ok" | "warning" | "blocked" | string;
  root: string;
  serve_root: string;
  auth_required: boolean;
  sections: EnvironmentSection[];
  blocked_items: string[];
  warning_items: string[];
  notes: string[];
};

export function SettingsView() {
  const [payload, setPayload] = useState<EnvironmentPayload | null>(null);
  const [status, setStatus] = useState("Loading environment status.");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setBusy(true);
    setStatus("Refreshing environment status.");
    try {
      const data = await getDashboardJson<EnvironmentPayload>(
        "/api/dashboard/environment",
      );
      setPayload(data);
      setStatus("Environment status loaded.");
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Environment refresh failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const items = payload?.sections.flatMap((section) => section.items) ?? [];
  const okCount = items.filter((item) => item.status === "ok").length;
  const warningCount = items.filter((item) => item.status === "warning").length;
  const blockedCount = items.filter((item) => item.status === "blocked").length;
  const nextActions = items
    .map((item) => item.next_action)
    .filter((item): item is string => Boolean(item));

  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting="Settings · Environment"
        headline="Runtime Setup"
        meta={status}
        stat={{
          label: "Status",
          value: payload?.status ?? "loading",
          delta: `${blockedCount} blocked · ${warningCount} warnings`,
        }}
      />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3">
          <KPI label="Ready" value={String(okCount)} accent="green" />
        </div>
        <div className="col-span-3">
          <KPI label="Warnings" value={String(warningCount)} accent="orange" />
        </div>
        <div className="col-span-3">
          <KPI label="Blocked" value={String(blockedCount)} accent="pink" />
        </div>
        <div className="col-span-3">
          <KPI
            label="API auth"
            value={payload?.auth_required ? "On" : "Off"}
            accent={payload?.auth_required ? "green" : "orange"}
          />
        </div>
      </div>

      <Card>
        <SectionTitle
          tick="ink"
          hint={
            payload
              ? `${payload.root} · generated ${formatTimestamp(payload.generated_at)}`
              : "Environment status is not loaded yet."
          }
          action={
            <button
              className="pill pill-secondary"
              disabled={busy}
              onClick={() => void refresh()}
            >
              <RefreshCw size={14} strokeWidth={2.2} /> Refresh
            </button>
          }
        >
          Environment Map
        </SectionTitle>
        <div className="mt-4 grid grid-cols-12 gap-3">
          {(payload?.sections ?? []).map((section) => (
            <div
              key={section.section}
              className="col-span-6 rounded-md hairline overflow-hidden"
            >
              <div className="px-4 py-3 bg-[var(--paper-3)] hairline-b">
                <div className="t-title-sm">{section.title}</div>
              </div>
              <div className="divide-y divide-[var(--hairline)]">
                {section.items.map((item) => (
                  <div
                    key={`${section.section}-${item.name}`}
                    className="grid grid-cols-[minmax(0,1fr)_88px] gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        {item.status === "ok" ? (
                          <ShieldCheck size={14} strokeWidth={2.2} />
                        ) : (
                          <TriangleAlert size={14} strokeWidth={2.2} />
                        )}
                        <span
                          className="t-body-sm ink truncate"
                          style={{ fontWeight: 650 }}
                        >
                          {item.name}
                        </span>
                      </div>
                      <div
                        className="t-body-xs ink-subtle mt-1 truncate"
                        title={item.detail}
                      >
                        {item.detail}
                      </div>
                      {item.next_action && (
                        <div
                          className="t-mono ink-subtle mt-2 truncate"
                          title={item.next_action}
                        >
                          {item.next_action}
                        </div>
                      )}
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
        <Card className="col-span-7">
          <SectionTitle tick="orange">Next Actions</SectionTitle>
          <BulletList
            items={nextActions}
            empty="No setup action is currently required."
          />
        </Card>
        <Card className="col-span-5">
          <SectionTitle tick="purple">Safety</SectionTitle>
          <BulletList
            items={payload?.notes ?? []}
            empty="Secrets are masked; Dashboard shows presence only."
          />
        </Card>
      </div>
    </div>
  );
}

function BulletList({ items, empty }: { items: string[]; empty: string }) {
  const unique = Array.from(new Set(items.filter(Boolean)));
  if (unique.length === 0) {
    return <div className="t-body-sm ink-subtle mt-4">{empty}</div>;
  }
  return (
    <div className="mt-4 space-y-2">
      {unique.map((item) => (
        <div
          key={item}
          className="grid grid-cols-[8px_minmax(0,1fr)] gap-2 t-body-sm"
        >
          <span className="mt-2 h-1.5 w-1.5 bg-[var(--ink)]" />
          <span className="ink-subtle">{item}</span>
        </div>
      ))}
    </div>
  );
}

function statusColor(status: string): "green" | "orange" | "pink" | "paper" {
  if (status === "ok") {
    return "green";
  }
  if (status === "blocked") {
    return "pink";
  }
  if (status === "warning") {
    return "orange";
  }
  return "paper";
}

function formatTimestamp(value: string): string {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
