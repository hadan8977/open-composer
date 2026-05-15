import { useEffect, useState } from "react";
import { applyDashboardCatalog } from "./data";

const DASHBOARD_TOKEN_STORAGE_KEY = "openComposerDashboardToken";
const REMOTE_JOB_TERMINAL_STATUSES = new Set(["executed", "blocked", "failed", "timed_out"]);

export type DashboardSession = {
  loading: boolean;
  remote: boolean;
  authenticated: boolean;
  owner: string | null;
  csrf: string | null;
  error: string | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

export type DashboardCommandPlanResponse = {
  command_id: string;
  action: string;
  confirmation_phrase: string;
  warnings?: string[];
  plan_path?: string | null;
  remote?: {
    risk_level: "green" | "yellow" | "red";
    backup_required: boolean;
    double_confirmation_required: boolean;
    double_confirmation_phrase?: string | null;
    job_timeout_seconds: number;
  };
};

export type DashboardCommandRunResponse = {
  command_id: string;
  action: string;
  status: string;
  message: string;
  job_id?: string;
  job_path?: string;
  log_path?: string;
  events_path?: string;
  result_path?: string | null;
  backup_manifest_path?: string | null;
  output_paths?: string[];
};

export function useDashboardCatalogSync(intervalMs = 15000): void {
  const [, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const handleUpdate = () => {
      setRevision((value) => value + 1);
    };

    const refresh = async () => {
      try {
        const response = await fetch("/api/dashboard/catalog", {
          headers: dashboardApiHeaders({
            Accept: "application/json",
          }),
          cache: "no-store",
        });
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as Parameters<typeof applyDashboardCatalog>[0];
        if (!cancelled) {
          applyDashboardCatalog(payload);
        }
      } catch {
        return;
      }
    };

    window.addEventListener("dashboard-catalog-updated", handleUpdate);
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, intervalMs);

    return () => {
      cancelled = true;
      window.removeEventListener("dashboard-catalog-updated", handleUpdate);
      window.clearInterval(timer);
    };
  }, [intervalMs]);
}

export function dashboardApiHeaders(
  headers: Record<string, string> = {},
): Record<string, string> {
  const token = dashboardApiToken();
  if (!token) {
    return headers;
  }
  return {
    ...headers,
    "X-Open-Composer-Token": token,
  };
}

export async function postDashboardJson<T>(
  path: string,
  payload: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: await dashboardPostHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  });
  return parseDashboardResponse<T>(response);
}

export async function getDashboardJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: dashboardApiHeaders({
      Accept: "application/json",
    }),
    cache: "no-store",
  });
  return parseDashboardResponse<T>(response);
}

export async function parseDashboardResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  let data: Record<string, unknown> = {};
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    throw new Error("Dashboard command API unavailable; run make dashboard-serve.");
  }
  if (!response.ok) {
    throw new Error(String(data.error ?? data.message ?? `HTTP ${response.status}`));
  }
  return data as T;
}

export function useDashboardSession(): DashboardSession {
  const [loading, setLoading] = useState(true);
  const [remote, setRemote] = useState(isRemoteDashboard());
  const [authenticated, setAuthenticated] = useState(!isRemoteDashboard());
  const [owner, setOwner] = useState<string | null>(null);
  const [csrf, setCsrf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    if (!isRemoteDashboard()) {
      setRemote(false);
      setAuthenticated(true);
      setLoading(false);
      return;
    }
    try {
      const response = await fetch("/api/session", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      const data = await parseDashboardResponse<{
        remote?: boolean;
        authenticated?: boolean;
        owner?: string | null;
        csrf?: string | null;
      }>(response);
      setRemote(Boolean(data.remote));
      setAuthenticated(Boolean(data.authenticated));
      setOwner(data.owner ?? null);
      setCsrf(data.csrf ?? null);
      setError(null);
    } catch (sessionError) {
      setRemote(false);
      setAuthenticated(true);
      setError(sessionError instanceof Error ? sessionError.message : "Session check failed.");
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    if (!remote) {
      return;
    }
    await fetch("/api/logout", {
      method: "POST",
      headers: await dashboardPostHeaders({ "Content-Type": "application/json" }),
      body: "{}",
    });
    await refresh();
  };

  useEffect(() => {
    void refresh();
  }, []);

  return { loading, remote, authenticated, owner, csrf, error, refresh, logout };
}

export async function loginDashboard(password: string): Promise<void> {
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  await parseDashboardResponse(response);
}

export async function promptDashboardConfirmations(
  plan: DashboardCommandPlanResponse,
  promptText: string,
): Promise<{ confirm: string; double_confirm: string } | null> {
  const confirmation = window.prompt(`${promptText}\n\n${plan.confirmation_phrase}`, plan.confirmation_phrase);
  if (confirmation === null) {
    return null;
  }
  let doubleConfirm = "";
  const doublePhrase = plan.remote?.double_confirmation_phrase;
  if (doublePhrase) {
    const second = window.prompt(
      `Type the remote double confirmation phrase.\n\n${doublePhrase}`,
      doublePhrase,
    );
    if (second === null) {
      return null;
    }
    doubleConfirm = second;
  }
  return { confirm: confirmation, double_confirm: doubleConfirm };
}

export async function resolveDashboardCommandRun(
  response: DashboardCommandRunResponse,
  onUpdate?: (job: DashboardCommandRunResponse) => void,
): Promise<DashboardCommandRunResponse> {
  if (!response.job_id) {
    return response;
  }
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const job = await getDashboardJson<DashboardCommandRunResponse>(
      `/api/dashboard/jobs/${response.job_id}`,
    );
    onUpdate?.(job);
    if (REMOTE_JOB_TERMINAL_STATUSES.has(job.status)) {
      return job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  return {
    ...response,
    status: "timed_out",
    message: "Timed out waiting for remote job status.",
  };
}

function dashboardApiToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  if (isRemoteDashboard()) {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get("token") ?? params.get("dashboard_token");
  if (queryToken) {
    window.localStorage.setItem(DASHBOARD_TOKEN_STORAGE_KEY, queryToken);
    return queryToken;
  }
  return window.localStorage.getItem(DASHBOARD_TOKEN_STORAGE_KEY);
}

async function dashboardPostHeaders(
  headers: Record<string, string> = {},
): Promise<Record<string, string>> {
  const result = dashboardApiHeaders(headers);
  if (!isRemoteDashboard()) {
    return result;
  }
  try {
    const response = await fetch("/api/session", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const session = await parseDashboardResponse<{ csrf?: string | null }>(response);
    if (session.csrf) {
      result["X-OC-CSRF"] = session.csrf;
    }
  } catch {
    return result;
  }
  return result;
}

function isRemoteDashboard(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const host = window.location.hostname;
  if (host === "127.0.0.1" || host === "localhost" || host === "") {
    return false;
  }
  return window.location.protocol === "https:" || host.endsWith(".vercel.app");
}
