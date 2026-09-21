// Read-only client for the cockpit JSON API (`open_composer/cockpit/api.py`).
// Every shape here mirrors a dataclass in `open_composer/cockpit/data/*.py`
// field-for-field; nothing is invented on the client. The app is mounted at
// /v2/ on the same origin as the API, so paths are absolute.

import { useEffect, useRef, useState } from 'react'

export type Status = 'ok' | 'warn' | 'stale' | 'unknown'
export type AuthState = 'authorized' | 'observation_only' | 'expired'

// ── status strip ───────────────────────────────────────────────────────────
export interface TopbarQuotaBar {
  key: string
  label: string
  percent_display: string
  width_percent: number
  status: Status
  reset_label: string
  projection_label: string | null
}
export interface TopbarQuota {
  available: boolean
  unavailable_reason: string | null
  bars: TopbarQuotaBar[]
}
export interface CodexWindow {
  limit_id: string
  used_percent: number | null
  resets_at: string | null
  window_duration_mins: number | null
}
export interface CodexQuota {
  auth_mode: string | null
  subscription_capable: boolean
  available: boolean
  label: string
  windows: CodexWindow[]
  note: string
}
export interface RoleModelUsage {
  role: 'main' | 'subagent'
  model: string
  input_tokens: number
  output_tokens: number
  cache_creation_tokens: number
  fresh_tokens: number
  cache_read_tokens: number
}
export interface SubagentTaskUsage {
  label: string
  model: string
  input_tokens: number
  output_tokens: number
  cache_creation_tokens: number
  fresh_tokens: number
  cache_read_tokens: number
  turns: number
  first_activity: string | null
  last_activity: string | null
  file_size_bytes: number
  truncated: boolean
  source_path: string
}
export interface UsageEstimate {
  window_start: string
  window_end: string
  by_role_model: RoleModelUsage[]
  subagent_tasks: SubagentTaskUsage[]
  fresh_main: number
  fresh_subagent: number
  fresh_total: number
  cache_read_main: number
  cache_read_subagent: number
  cache_read_total: number
  distinct_session_count: number
  main_files_scanned: number
  subagent_files_scanned: number
  subagent_tree_found: boolean
  topbar_label: string
  generated_at: string
}
export interface Badge {
  status: Status
  label: string
}
export interface StatusPayload {
  generated_at: string
  claude: TopbarQuota
  codex: CodexQuota
  usage_estimate: UsageEstimate
  agents: [string, string][]
  data_freshness: Badge
  rehearsal: Badge
}

// ── hypotheses ─────────────────────────────────────────────────────────────
export interface Criterion {
  name: string
  threshold: unknown
  direction: string | null
}
export interface CardFrontMatter {
  card_id: string | null
  status: string | null
  lane: string | null
  previous: string | null
  criteria: Criterion[]
}
export interface Card {
  id: string
  kind: string
  title: string
  status_text: string
  lane: string
  lane_reason: string | null
  script: string | null
  output_dir: string | null
  layer: string | null
  data_layer: string | null
  lesson_ref: string | null
  previous: string | null
  referenced_ids: string[]
  front_matter: CardFrontMatter | null
  path: string
  parse_warnings: string[]
}
export interface CardListItem extends Card {
  headlines: string[]
}
export interface Lane {
  lane: string
  status: Status
  cards: CardListItem[]
}
export interface HypothesesPayload {
  generated_at: string
  lanes: Lane[]
  warnings: string[]
}
export interface CriteriaSection {
  heading: string
  level: number
  markdown: string
  html: string
}
export interface ResultFacts {
  card_id: string
  iteration_id: string
  path: string
  cell_count: number | null
  windows: Record<string, unknown> | null
  incumbent_to_beat: Record<string, unknown> | null
  benchmarks: Record<string, unknown>[] | null
  family_picks: Record<string, unknown>[] | null
  generated_at: string | null
  raw_keys: string[]
  headline: string
}
export interface LineageEdge {
  source: string
  target: string
  kind: string
}
export interface NeighbourCard {
  id: string
  title: string
  lane: string
  status: Status
}
export interface CardPayload {
  generated_at: string
  card: Card & { body_markdown: string }
  body_html: string
  criteria: CriteriaSection[]
  results: ResultFacts[]
  neighbours: LineageEdge[]
  neighbour_cards: Record<string, NeighbourCard>
}

// ── lineage ────────────────────────────────────────────────────────────────
export interface LineageNode {
  card_id: string
  title: string
  lane: string
  kind: string
}
export interface LineageLayout {
  positions: Record<string, [number, number]>
  width: number
  height: number
}
export interface MobileLineageRow {
  card_id: string
  title: string
  lane: string
  depth: number
  edge_label: string | null
  is_cycle_repeat: boolean
}
export interface LineagePayload {
  generated_at: string
  nodes: LineageNode[]
  edges: LineageEdge[]
  node_status: Record<string, Status>
  layout: LineageLayout
  isolated: LineageNode[]
  mobile_rows: MobileLineageRow[]
}

// ── agents ─────────────────────────────────────────────────────────────────
export type AgentStatus = 'running' | 'idle' | 'error' | 'closed' | string
export interface AgentRecord {
  id: string
  provider: string
  cwd: string | null
  workspace_id: string | null
  title: string | null
  created_at: string | null
  updated_at: string | null
  last_activity_at: string | null
  last_user_message_at: string | null
  last_status: AgentStatus
  model: string | null
  session_id: string | null
}
export interface AgentActivity {
  transcript_kind: 'claude' | 'codex' | 'none'
  transcript_path: string | null
  current_file: string | null
  last_text: string | null
  last_entry_at: string | null
  warning: string | null
}
export interface AgentSummary {
  record: AgentRecord
  activity: AgentActivity | null
}
export interface HeavyJob {
  unit: string
  started_at: string | null
  elapsed_seconds: number | null
  memory_current_bytes: number | null
  memory_max_bytes: number | null
  memory_max_unlimited: boolean
  warning: string | null
}
export interface HeavyJobs {
  jobs: HeavyJob[]
  available: boolean
  warnings: string[]
}
export interface AgentsPayload {
  generated_at: string
  counts: { running: number; idle: number; error: number; closed: number }
  agents: AgentSummary[]
  heavy: HeavyJobs
}
export interface TimelineEntry {
  at: string | null
  kind: 'text' | 'tool' | 'result'
  tool_name: string | null
  target: string | null
  detail: string | null
  is_error: boolean
  duration_seconds: number | null
  tool_use_id: string | null
}
export interface SubagentTask {
  id: string
  entries: TimelineEntry[]
  entries_total: number
  warning: string | null
}
export interface AgentDetail {
  record: AgentRecord
  entries: TimelineEntry[]
  entries_total: number
  subagents: SubagentTask[]
  transcript_kind: 'claude' | 'codex' | 'none'
  transcript_available: boolean
  warnings: string[]
}
export interface AgentPayload {
  generated_at: string
  detail: AgentDetail
}

// ── paper ──────────────────────────────────────────────────────────────────
export interface Authorization {
  strategy_name: string
  state: AuthState
  status: Status
  authorization_id: string | null
  authorized_at: string | null
  expires_at: string | null
  days_remaining: number | null
  limits: Record<string, unknown> | null
  scope: string | null
  paper_only: boolean | null
  below_contract_acknowledged: boolean | null
  broker_account_id_hash_prefix: string | null
  gate_status_note: string | null
  warnings: string[]
}
export interface StrategySummary {
  name: string
  authorization: Authorization
  generated_at: string | null
  session: string | null
  cycle_status: string | null
  positions_agreement: string
  latest_fill_rate: number | null
  latest_fill_session: string | null
  last_order_at: string | null
  warnings: string[]
}
export interface AccountSnapshot {
  generated_at: string | null
  equity: number | null
  cash: number | null
  buying_power: number | null
  portfolio_value: number | null
  age_hours: number | null
  status: Status
  broker_account_id_hash_prefix: string | null
  warnings: string[]
}
export interface KillSwitch {
  enabled: boolean | null
  reason: string | null
  updated_at: string | null
  status: Status
  warnings: string[]
}
export interface PaperPayload {
  generated_at: string
  report: {
    generated_at: string
    account: AccountSnapshot
    kill_switch: KillSwitch
    open_order_count: number | null
    strategies: StrategySummary[]
    warnings: string[]
  }
  auth_state_labels: Record<AuthState, string>
}
export interface PositionRow {
  symbol: string
  action: string | null
  decision: string | null
  reason: string | null
  target_weight: number | null
  target_qty: number | null
  current_qty: number | null
  ledger_qty: number | null
  broker_qty: number | null
  market_value: number | null
  unrealized_pl: number | null
}
export interface OrderRecord {
  recorded_at: string | null
  session: string | null
  symbol: string
  side: string | null
  qty: number | null
  notional: number | null
  order_style: string | null
  broker_status: string | null
  broker_order_id: string | null
}
export interface FillSession {
  session: string
  orders: number | null
  filled_full: number | null
  filled_partial: number | null
  unfilled: number | null
  cancelled_before_open: number | null
  fill_rate_by_notional: number | null
  median_slippage_vs_reference_bps: number | null
  order_styles: string[]
}
export interface EquityPoint {
  at: string
  equity: number
  source: string
}
export interface StrategyDetail {
  name: string
  authorization: Authorization
  generated_at: string | null
  session: string | null
  cycle_status: string | null
  equity_at_last_cycle: number | null
  has_dedicated_ledger: boolean
  decision_counts: Record<string, number>
  positions: PositionRow[]
  positions_agreement: string
  orders: OrderRecord[]
  orders_window_truncated: boolean
  fills: {
    strategy_name: string
    available: boolean
    generated_at: string | null
    sessions: FillSession[]
    warnings: string[]
  }
  equity_series: {
    strategy_name: string
    points: EquityPoint[]
    has_history: boolean
    note: string
    warnings: string[]
  }
  warnings: string[]
}
export interface EquityChart {
  bars: { x: number; y: number; width: number; height: number; title: string; value: number }[]
  width: number
  height: number
  min_value: number
  max_value: number
}
export interface StrategyPayload {
  generated_at: string
  detail: StrategyDetail
  chart: EquityChart | null
  auth_state_labels: Record<AuthState, string>
}

// ── quota ──────────────────────────────────────────────────────────────────
export interface ClaudeWindow {
  key: string
  label: string
  percent_used: number | null
  resets_at: string | null
  status: Status
}
export interface CredentialProbe {
  source: 'env' | 'paseo' | 'credentials_file'
  label: string
  token_found: boolean
  outcome: string
  cached: boolean
}
export interface ThrottleEvent {
  kind: 'event'
  at: string | null
  rate_limit_type: string | null
  status: string | null
  resets_at: string | null
  overage_status: string | null
  source_path: string
}
export interface QuotaPayload {
  generated_at: string
  report: {
    generated_at: string
    claude: {
      snapshot: {
        fetched_at: string
        available: boolean
        windows: ClaudeWindow[]
        extra_usage: { present: boolean; summary: Record<string, string> } | null
        unavailable_reason: string | null
        diagnostic: string | null
        http_status: number | null
        credential_probes: CredentialProbe[]
      }
      served_from_cache: boolean
      cache_age_seconds: number
      breaker_open: boolean
      breaker_open_until: string | null
      consecutive_failures: number
      projection: {
        available: boolean
        eta: string | null
        rate_percent_per_hour: number | null
        label: string
      }
    }
    claude_throttle_event: ThrottleEvent | null
    codex: CodexQuota
    usage_estimate: UsageEstimate
    throttle_calibration: {
      available: boolean
      last_event: ThrottleEvent | null
      last_fresh_at_event: number | null
      event_count: number
      min_fresh_at_event: number | null
      median_fresh_at_event: number | null
      vs_last_throttle_ratio: number | null
      coverage: string
      state: 'ready' | 'computing'
    }
  }
}

// ── health ─────────────────────────────────────────────────────────────────
export interface CronLog {
  path: string
  exists: boolean
  mtime: string | null
  size_bytes: number | null
  has_error_marker: boolean
  tail_snippet: string | null
  status: Status
}
export interface CronJob {
  name: string
  schedule: string
  command: string
  logs: CronLog[]
  status: Status
  note: string | null
}
export interface DataFreshness {
  name: string
  detail: string
  latest_date: string | null
  sessions_behind: number | null
  status: Status
}
export interface HealthPayload {
  generated_at: string
  report: {
    generated_at: string
    cron: { jobs: CronJob[]; available: boolean; error: string | null }
    data_freshness: DataFreshness[]
    disk: {
      mount: string
      total_bytes: number
      used_bytes: number
      available_bytes: number
      used_percent: number
      status: Status
    } | null
    memory: {
      total_bytes: number
      used_bytes: number
      available_bytes: number
      used_percent: number
      status: Status
    } | null
    process: { pid: number; rss_bytes: number; status: Status }
  }
}

// ── fetching ───────────────────────────────────────────────────────────────
export interface Remote<T> {
  data: T | null
  error: string | null
  loading: boolean
  at: number | null
  reload: () => void
}

/** GET `path` as JSON, re-fetching every `refreshMs` (slower when the tab is
 *  hidden). A `null` path fetches nothing. Changing the path drops the old
 *  data immediately so an inspector never shows the previous record. */
export function useJson<T>(path: string | null, refreshMs = 30_000): Remote<T> {
  const [state, setState] = useState<Omit<Remote<T>, 'reload'>>({
    data: null,
    error: null,
    loading: path !== null,
    at: null,
  })
  const [tick, setTick] = useState(0)
  const lastPath = useRef<string | null>(null)

  useEffect(() => {
    if (lastPath.current !== path) {
      lastPath.current = path
      setState({ data: null, error: null, loading: path !== null, at: null })
    }
    if (path === null) return
    const ctrl = new AbortController()
    let alive = true
    let timer: number | undefined

    const run = async () => {
      try {
        const res = await fetch(path, {
          signal: ctrl.signal,
          cache: 'no-store',
          headers: { Accept: 'application/json' },
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = (await res.json()) as T
        if (alive) setState({ data: json, error: null, loading: false, at: Date.now() })
      } catch (err) {
        if (!alive || (err as Error).name === 'AbortError') return
        setState(s => ({ ...s, error: (err as Error).message || 'error', loading: false }))
      }
      if (alive && refreshMs > 0) {
        timer = window.setTimeout(run, document.hidden ? refreshMs * 4 : refreshMs)
      }
    }
    void run()
    return () => {
      alive = false
      ctrl.abort()
      if (timer) window.clearTimeout(timer)
    }
  }, [path, refreshMs, tick])

  return { ...state, reload: () => setTick(t => t + 1) }
}

/** Ticks once a minute so relative times ("2m ago") stay honest. */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}

// ── formatting ─────────────────────────────────────────────────────────────
export function fmtK(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  const abs = Math.abs(n)
  if (abs < 1000) return String(Math.round(n))
  if (abs < 10_000) return `${(n / 1000).toFixed(1)}K`
  if (abs < 1_000_000) return `${Math.round(n / 1000)}K`
  if (abs < 10_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  return `${(n / 1_000_000).toFixed(1)}M`
}

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

export function fmtMoney(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  const sign = n < 0 ? '−' : ''
  return `${sign}$${Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

export function fmtPct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  return `${n.toFixed(digits)}%`
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'never'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  const diff = (now - t) / 1000
  const future = diff < 0
  const s = Math.abs(diff)
  let out: string
  if (s < 45) out = future ? 'now' : 'just now'
  else if (s < 3600) out = `${Math.round(s / 60)}m`
  else if (s < 86_400) out = `${Math.round(s / 3600)}h`
  else if (s < 86_400 * 14) out = `${(s / 86_400).toFixed(s < 86_400 * 2 ? 1 : 0)}d`
  else out = new Date(t).toISOString().slice(0, 10)
  if (s < 45) return out
  return future ? `in ${out}` : `${out} ago`
}

export function fmtHms(iso: string | null | undefined): string {
  if (!iso) return '–'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleTimeString('en-GB', { hour12: false })
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  return iso.slice(0, 10)
}

export function fmtDur(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '–'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '–'
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(0)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}

export function shortModel(model: string | null | undefined): string {
  if (!model) return '–'
  return model.replace(/^claude-/, '')
}

export function normStatus(s: string | null | undefined): Status {
  if (s === 'ok' || s === 'warn' || s === 'stale') return s
  return 'unknown'
}

export function agentDot(status: AgentStatus): Status {
  if (status === 'running') return 'ok'
  if (status === 'error') return 'stale'
  if (status === 'idle') return 'warn'
  return 'unknown'
}
