// Agents: one row per Paseo session, the heavy systemd jobs, and an inspector
// with the audited tool timeline that keeps growing over SSE.
import { useEffect, useMemo, useRef, useState } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import {
  agentDot,
  fmtAgo,
  fmtBytes,
  fmtDur,
  fmtHms,
  fmtInt,
  shortModel,
  useJson,
  useNow,
  type AgentPayload,
  type AgentsPayload,
  type AgentSummary,
  type TimelineEntry,
} from '../api'
import {
  Chip,
  Details,
  Empty,
  ErrorNote,
  Group,
  InspectorHead,
  KV,
  Loading,
  MetricCard,
  Metrics,
  Row,
  RowAside,
  RowMain,
  SectionCap,
  StatusDot,
  Warnings,
  matches,
  plural,
} from '../components/Shared'

const ORDER: Record<string, number> = { running: 0, error: 1, idle: 2, closed: 3 }

function agentTitle(a: AgentSummary): string {
  return a.record.title || a.record.id.slice(0, 8)
}

export default function Agents({ selectedId, onSelect, search }: ScreenProps) {
  const { data, error, loading } = useJson<AgentsPayload>('/api/agents.json', 20_000)
  const now = useNow()

  const rows = useMemo(() => {
    if (!data) return []
    return data.agents
      .filter(a =>
        matches(search, agentTitle(a), a.record.id, a.record.model, a.record.provider, a.record.cwd),
      )
      .sort((a, b) => {
        const o = (ORDER[a.record.last_status] ?? 9) - (ORDER[b.record.last_status] ?? 9)
        if (o !== 0) return o
        return (b.record.last_activity_at ?? '').localeCompare(a.record.last_activity_at ?? '')
      })
  }, [data, search])

  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null

  const live = rows.filter(a => a.record.last_status !== 'closed')
  const closed = rows.filter(a => a.record.last_status === 'closed')
  const heavy = data.heavy

  return (
    <div>
      <Metrics>
        <MetricCard label="Running" value={data.counts.running} status={data.counts.running > 0 ? 'ok' : 'unknown'} sub={`${data.counts.idle} idle`} />
        <MetricCard label="Errors" value={data.counts.error} status={data.counts.error > 0 ? 'stale' : 'ok'} sub={`${data.counts.closed} closed`} />
        <MetricCard
          label="Heavy jobs"
          value={heavy.available ? heavy.jobs.length : 'unknown'}
          status={heavy.available ? (heavy.jobs.length ? 'ok' : 'unknown') : 'unknown'}
          sub={heavy.jobs[0] ? heavy.jobs[0].unit : heavy.available ? 'none' : heavy.warnings[0] ?? 'systemd unavailable'}
        />
        <MetricCard
          label="Last activity"
          value={live[0]?.record.last_activity_at ? fmtAgo(live[0].record.last_activity_at, now) : '–'}
          sub={live[0] ? agentTitle(live[0]) : 'no live agents'}
        />
      </Metrics>

      <SectionCap aside={plural(live.length, 'agent')}>Live</SectionCap>
      <Group>
        {live.length === 0 && <Empty>None</Empty>}
        {live.map(a => (
          <AgentRow key={a.record.id} a={a} now={now} selected={selectedId === a.record.id} onClick={() => onSelect(selectedId === a.record.id ? null : a.record.id)} />
        ))}
      </Group>

      <SectionCap aside={heavy.available ? plural(heavy.jobs.length, 'job') : 'unknown'}>Heavy jobs</SectionCap>
      <Group>
        {!heavy.available && <Empty>{heavy.warnings[0] ?? 'unknown'}</Empty>}
        {heavy.available && heavy.jobs.length === 0 && <Empty>None</Empty>}
        {heavy.jobs.map(j => (
          <Row key={j.unit} static>
            <StatusDot status={j.warning ? 'warn' : 'ok'} />
            <RowMain title={<span className="mono">{j.unit}</span>} sub={j.warning ?? (j.started_at ? `started ${fmtAgo(j.started_at, now)}` : 'start time unknown')} />
            <RowAside
              value={fmtDur(j.elapsed_seconds)}
              sub={`${fmtBytes(j.memory_current_bytes)} of ${j.memory_max_unlimited ? '∞' : fmtBytes(j.memory_max_bytes)}`}
            />
          </Row>
        ))}
      </Group>

      {closed.length > 0 && (
        <Details summary={`${plural(closed.length, 'closed agent')}`}>
          <Group>
            {closed.map(a => (
              <AgentRow key={a.record.id} a={a} now={now} selected={selectedId === a.record.id} onClick={() => onSelect(selectedId === a.record.id ? null : a.record.id)} />
            ))}
          </Group>
        </Details>
      )}
    </div>
  )
}

function AgentRow({ a, now, selected, onClick }: { a: AgentSummary; now: number; selected: boolean; onClick: () => void }) {
  const act = a.activity
  const sub = [a.record.provider, shortModel(a.record.model), act?.current_file || act?.last_text || act?.warning || null]
    .filter(Boolean)
    .join(' · ')
  return (
    <Row selected={selected} onClick={onClick} title={a.record.cwd ?? undefined}>
      <StatusDot status={agentDot(a.record.last_status)} />
      <RowMain title={agentTitle(a)} sub={sub} />
      <RowAside value={fmtAgo(a.record.last_activity_at, now)} sub={a.record.last_status} />
    </Row>
  )
}

// ── inspector ──────────────────────────────────────────────────────────────

interface StreamRow {
  at: string
  kind: 'text' | 'tool' | 'result'
  tool_name: string | null
  content: string | null
  duration_seconds: number | null
  is_error: boolean
}

function toRow(e: TimelineEntry): StreamRow {
  return {
    at: fmtHms(e.at),
    kind: e.kind,
    tool_name: e.tool_name,
    content: e.target || e.detail,
    duration_seconds: e.duration_seconds,
    is_error: e.is_error,
  }
}

function What({ r }: { r: StreamRow }) {
  if (r.kind === 'tool') return <Chip tone="tool">{r.tool_name || 'tool'}</Chip>
  if (r.kind === 'result') return <Chip>↳ {r.tool_name || 'result'}</Chip>
  return <Chip>text</Chip>
}

function Timeline({ rows, stream }: { rows: StreamRow[]; stream?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !stream) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 140) el.scrollTop = el.scrollHeight
  }, [rows.length, stream])
  if (rows.length === 0) return <Empty>None</Empty>
  return (
    <div ref={ref} className={`tbl-wrap${stream ? ' stream' : ''}`} style={{ margin: 0 }}>
      <table className="tbl tl" style={{ tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: 66 }} />
          <col style={{ width: 92 }} />
          <col />
          <col style={{ width: 52 }} />
          <col style={{ width: 22 }} />
        </colgroup>
        <thead>
          <tr>
            <th>Time</th>
            <th>What</th>
            <th>Target</th>
            <th className="r">Dur</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`${r.is_error ? 'is-error' : ''}${i >= rows.length - 1 && stream ? ' is-new' : ''}`}>
              <td className="mono dim" style={{ whiteSpace: 'nowrap', fontSize: 10.5 }}>{r.at}</td>
              <td style={{ overflow: 'hidden' }}><What r={r} /></td>
              <td title={r.content ?? undefined}>
                <span className="clamp3" style={{ overflowWrap: 'anywhere' }}>{r.content || '–'}</span>
              </td>
              <td className="r dim" style={{ whiteSpace: 'nowrap' }}>{r.duration_seconds === null ? '' : fmtDur(r.duration_seconds)}</td>
              <td style={{ paddingLeft: 4 }}>{r.kind === 'result' ? <StatusDot status={r.is_error ? 'stale' : 'ok'} size={7} /> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AgentsInspector({ id }: InspectorProps) {
  const { data, error, loading } = useJson<AgentPayload>(`/api/agents/${encodeURIComponent(id)}.json`, 0)
  const now = useNow()
  const [live, setLive] = useState<StreamRow[]>([])

  // Append rows from the SSE tail from the moment the detail was loaded.
  useEffect(() => {
    setLive([])
    if (!data?.detail.transcript_available || typeof EventSource === 'undefined') return
    const es = new EventSource(`/agents/${encodeURIComponent(id)}/stream`)
    es.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data) as StreamRow
        setLive(rows => [...rows.slice(-400), d])
      } catch {
        /* keep-alive comments never reach onmessage; malformed data is ignored */
      }
    }
    return () => es.close()
  }, [id, data?.detail.transcript_available])

  if (!data) return loading ? <Loading label="Loading transcript" /> : error ? <ErrorNote error={error} /> : null
  const d = data.detail
  const r = d.record
  const rows = [...d.entries.map(toRow), ...live]

  return (
    <div className="fade-in">
      <InspectorHead
        status={agentDot(r.last_status)}
        eyebrow={
          <>
            <span>{r.provider}</span>
            <span style={{ color: 'var(--label3)' }}>·</span>
            <span className="mono">{shortModel(r.model)}</span>
          </>
        }
        title={r.title || r.id.slice(0, 8)}
        sub={`${r.last_status} · last activity ${fmtAgo(r.last_activity_at, now)}`}
      />

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--sep)' }}>
        <KV
          rows={[
            ['Session', <span className="mono">{r.id}</span>],
            ['Directory', r.cwd ? <span className="mono">{r.cwd}</span> : 'None'],
            ['Transcript', d.transcript_available ? d.transcript_kind : 'none'],
            r.created_at ? ['Created', fmtAgo(r.created_at, now)] : null,
          ]}
        />
      </div>

      <div style={{ padding: '12px 16px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span className="section-cap">Timeline</span>
          <span className="num" style={{ fontSize: 11, color: 'var(--label3)' }}>
            {fmtInt(d.entries.length + live.length)} of {fmtInt(d.entries_total + live.length)}
            {live.length > 0 ? ` · ${live.length} live` : ''}
          </span>
        </div>
        {d.transcript_available ? <Timeline rows={rows} stream /> : <Empty>No transcript</Empty>}
      </div>

      <div style={{ padding: '12px 16px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span className="section-cap">Subagents</span>
          <span className="num" style={{ fontSize: 11, color: 'var(--label3)' }}>{d.subagents.length}</span>
        </div>
        {d.subagents.length === 0 && <Empty>None</Empty>}
        {d.subagents.map(t => (
          <details key={t.id} style={{ marginBottom: 8, fontSize: 12 }}>
            <summary style={{ cursor: 'pointer', color: 'var(--label2)', padding: '4px 0' }}>
              <span className="mono">{t.id}</span> · <span className="num">{fmtInt(t.entries.length)} of {fmtInt(t.entries_total)}</span>
              {t.warning ? ` · ${t.warning}` : ''}
            </summary>
            <div style={{ paddingTop: 6 }}>
              <Timeline rows={t.entries.map(toRow)} />
            </div>
          </details>
        ))}
      </div>

      <Warnings items={d.warnings} />
    </div>
  )
}
