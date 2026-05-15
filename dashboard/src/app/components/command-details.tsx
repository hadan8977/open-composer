import { FileText, ListTree } from "lucide-react";
import type { DashboardCommandPlanResponse, DashboardCommandRunResponse } from "./runtime";

export function CommandResultDetails({
  plan,
  result,
}: {
  plan?: DashboardCommandPlanResponse | null;
  result?: DashboardCommandRunResponse | null;
}) {
  if (!plan && !result) {
    return null;
  }
  const rows = [
    ["Plan", plan?.plan_path],
    ["Command", result?.command_id ?? plan?.command_id],
    ["Job", result?.job_id],
    ["Job record", result?.job_path],
    ["Log", result?.log_path],
    ["Events", result?.events_path],
    ["Result", result?.result_path],
    ["Backup", result?.backup_manifest_path],
  ].filter(([, value]) => Boolean(value));
  const outputs = result?.output_paths ?? [];
  return (
    <div className="rounded-lg bg-[var(--paper-3)] p-3 space-y-2">
      <div className="flex items-center gap-2 t-caption ink-subtle">
        <ListTree size={13} strokeWidth={2.2} />
        Command artifacts
      </div>
      <div className="grid gap-1.5">
        {rows.map(([label, value]) => (
          <div key={`${label}-${value}`} className="grid grid-cols-[92px_minmax(0,1fr)] gap-2">
            <span className="t-caption ink-subtle">{label}</span>
            <code className="t-body-sm ink break-all">{value}</code>
          </div>
        ))}
      </div>
      {outputs.length > 0 && (
        <div className="pt-1 space-y-1">
          <div className="flex items-center gap-2 t-caption ink-subtle">
            <FileText size={13} strokeWidth={2.2} />
            Outputs
          </div>
          {outputs.map((path) => (
            <code key={path} className="block t-body-sm ink break-all">
              {path}
            </code>
          ))}
        </div>
      )}
    </div>
  );
}
