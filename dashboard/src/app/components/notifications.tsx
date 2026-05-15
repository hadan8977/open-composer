import { useEffect, useState } from "react";
import { Bell, RefreshCw, Send, ShieldCheck, TriangleAlert } from "lucide-react";
import { Card, KPI, SectionTitle, Tag } from "./blocks";
import { getDashboardJson, postDashboardJson } from "./runtime";

type NotificationPolicy = {
  kind: string;
  channels: string[];
  min_severity: string;
};

type NotificationConfigStatus = {
  config_path: string;
  config_exists: boolean;
  log_path: string;
  telegram_enabled: boolean;
  telegram_bot_token_env: string;
  telegram_bot_token_present: boolean;
  telegram_chat_id_env: string;
  telegram_chat_id_present: boolean;
  telegram_parse_mode: string;
  policies: NotificationPolicy[];
};

type NotificationDelivery = {
  channel: string;
  status: string;
  message?: string;
};

type NotificationRecord = {
  id: string;
  created_at: string;
  kind: string;
  severity: string;
  title: string;
  body?: string;
  requested_channels?: string[];
  deliveries?: NotificationDelivery[];
};

export function Notifications() {
  const [config, setConfig] = useState<NotificationConfigStatus | null>(null);
  const [records, setRecords] = useState<NotificationRecord[]>([]);
  const [status, setStatus] = useState("Loading notifications…");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setStatus("Refreshing notifications…");
    try {
      const [configPayload, logPayload] = await Promise.all([
        getDashboardJson<NotificationConfigStatus>("/api/notifications/config"),
        getDashboardJson<{ notifications: NotificationRecord[] }>("/api/notifications/log"),
      ]);
      setConfig(configPayload);
      setRecords(logPayload.notifications ?? []);
      setStatus("Notifications loaded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Notification refresh failed.");
    }
  };

  const sendTest = async (dryRun: boolean) => {
    setBusy(true);
    setStatus(dryRun ? "Recording dry run…" : "Sending test notification…");
    try {
      await postDashboardJson<{ notification: NotificationRecord }>("/api/notifications/test", {
        kind: "signal_actionable",
        severity: "info",
        dry_run: dryRun,
      });
      await refresh();
      setStatus(dryRun ? "Dry run recorded." : "Test notification recorded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Test notification failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const telegramReady =
    Boolean(config?.telegram_enabled) &&
    Boolean(config?.telegram_bot_token_present) &&
    Boolean(config?.telegram_chat_id_present);

  return (
    <div className="px-6 pb-8 space-y-3">
      <div
        className="dscard relative overflow-hidden"
        style={{ borderRadius: "var(--r-2xl)", padding: "22px 26px" }}
      >
        <div className="relative z-10 flex items-start justify-between gap-6">
          <div>
            <div className="t-caption ink-muted">OUTBOUND NOTIFICATIONS</div>
            <h1 className="t-title-xl mt-2">Notifications</h1>
            <p className="t-body-sm ink-subtle mt-2 max-w-2xl">{status}</p>
          </div>
          <div className="flex gap-2">
            <button className="pill pill-secondary" onClick={() => void refresh()}>
              <RefreshCw size={14} strokeWidth={2.2} /> Refresh
            </button>
            <button className="pill pill-secondary" disabled={busy} onClick={() => void sendTest(true)}>
              <ShieldCheck size={14} strokeWidth={2.2} /> Dry run
            </button>
            <button className="pill pill-primary" disabled={busy} onClick={() => void sendTest(false)}>
              <Send size={14} strokeWidth={2.2} /> Send test
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3">
          <KPI label="Telegram" value={telegramReady ? "Ready" : "Not ready"} accent={telegramReady ? "green" : "orange"} />
        </div>
        <div className="col-span-3">
          <KPI label="Policies" value={String(config?.policies.length ?? 0)} accent="cyan" />
        </div>
        <div className="col-span-3">
          <KPI label="Recent log" value={String(records.length)} accent="black" />
        </div>
        <div className="col-span-3">
          <KPI label="Config" value={config?.config_exists ? "Present" : "Default"} accent={config?.config_exists ? "green" : "paper"} />
        </div>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Card className="col-span-5">
          <SectionTitle tick="green" hint={config?.config_path ?? "config/notifications.yaml"}>
            Channel status
          </SectionTitle>
          <div className="mt-4 space-y-2">
            <StatusRow label="Telegram enabled" ok={Boolean(config?.telegram_enabled)} />
            <StatusRow label={config?.telegram_bot_token_env ?? "TELEGRAM_BOT_TOKEN"} ok={Boolean(config?.telegram_bot_token_present)} />
            <StatusRow label={config?.telegram_chat_id_env ?? "TELEGRAM_CHAT_ID"} ok={Boolean(config?.telegram_chat_id_present)} />
            <div className="grid grid-cols-[1fr_auto] gap-3 py-2 hairline-b">
              <span className="t-body-sm ink-subtle">Parse mode</span>
              <span className="t-body-sm ink">{config?.telegram_parse_mode ?? "unknown"}</span>
            </div>
          </div>
        </Card>

        <Card className="col-span-7">
          <SectionTitle tick="cyan" hint={config?.log_path ?? "reports/notifications/log.jsonl"}>
            Policies
          </SectionTitle>
          <div className="mt-4 overflow-hidden rounded-md hairline">
            <table className="w-full text-left">
              <thead className="bg-[var(--paper-3)]">
                <tr className="t-caption ink-subtle">
                  <th className="px-3 py-2">Kind</th>
                  <th className="px-3 py-2">Min</th>
                  <th className="px-3 py-2">Channels</th>
                </tr>
              </thead>
              <tbody>
                {(config?.policies ?? []).map((policy) => (
                  <tr key={policy.kind} className="hairline-t">
                    <td className="px-3 py-2 t-body-sm ink">{policy.kind}</td>
                    <td className="px-3 py-2"><Tag color={severityColor(policy.min_severity)}>{policy.min_severity}</Tag></td>
                    <td className="px-3 py-2 t-body-sm ink-subtle">{policy.channels.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card>
        <SectionTitle tick="orange" hint={config?.log_path ?? "reports/notifications/log.jsonl"}>
          Recent notifications
        </SectionTitle>
        <div className="mt-4 space-y-2">
          {records.length === 0 ? (
            <div className="flex items-center gap-2 t-body-sm ink-subtle">
              <Bell size={14} strokeWidth={2.2} /> No notification records.
            </div>
          ) : (
            records.slice().reverse().map((record) => (
              <div key={record.id} className="grid grid-cols-[140px_120px_minmax(0,1fr)_180px] gap-3 rounded-md bg-[var(--paper-3)] p-3">
                <div className="t-body-sm ink-subtle">{formatTimestamp(record.created_at)}</div>
                <div className="flex items-center gap-2">
                  <Tag color={severityColor(record.severity)}>{record.severity}</Tag>
                  <span className="t-caption ink-subtle">{record.kind}</span>
                </div>
                <div className="min-w-0">
                  <div className="t-body-sm ink truncate" style={{ fontWeight: 650 }}>{record.title}</div>
                  {record.body && <div className="t-body-sm ink-subtle truncate">{record.body}</div>}
                </div>
                <div className="t-body-sm ink-subtle truncate">
                  {(record.deliveries ?? []).map((item) => `${item.channel}:${item.status}`).join(", ")}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-3 py-2 hairline-b">
      <span className="t-body-sm ink-subtle">{label}</span>
      <span className={`inline-flex items-center gap-1.5 t-body-sm ${ok ? "ink" : "ink-subtle"}`}>
        {ok ? <ShieldCheck size={14} strokeWidth={2.2} /> : <TriangleAlert size={14} strokeWidth={2.2} />}
        {ok ? "ok" : "missing"}
      </span>
    </div>
  );
}

function severityColor(value: string): "green" | "orange" | "pink" | "paper" {
  if (value === "red") {
    return "pink";
  }
  if (value === "warn") {
    return "orange";
  }
  if (value === "info") {
    return "green";
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
