import { useEffect, useState } from "react";
import { applyDashboardCatalog } from "./data";

const DASHBOARD_TOKEN_STORAGE_KEY = "openComposerDashboardToken";

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
    headers: dashboardApiHeaders({
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

function dashboardApiToken(): string | null {
  if (typeof window === "undefined") {
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
