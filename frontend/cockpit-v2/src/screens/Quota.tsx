// Quota: live Claude windows, the transcript-based fresh-token estimate, the
// throttle calibration, credential probes, Codex. Nothing here is selectable,
// so the screen has no inspector.
import type { ReactNode } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import { fmtAgo, fmtK, fmtPct, shortModel, useJson, useNow, type QuotaPayload } from '../api'
import {
  Card,
  Chip,
  Empty,
  ErrorNote,
  Group,
  KV,
  Loading,
  MetricCard,
  Metrics,
  QuotaBar,
  Row,
  RowMain,
  SectionCap,
  StateWord,
  StatusDot,
  matches,
} from '../components/Shared'

export default function Quota({ search }: ScreenProps) {
  const { data, error, loading } = useJson<QuotaPayload>('/api/quota.json', 30_000)
  const now = useNow()
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null

  const rep = data.report
  const claude = rep.claude
  const snap = claude.snapshot
  const est = rep.usage_estimate
  const cal = rep.throttle_calibration
  const codex = rep.codex
  const first = snap.available && snap.windows.length > 0 ? snap.windows[0] : null
  const tasks = est.subagent_tasks.filter(t => matches(search, t.label, t.model))

  return (
    <div>
      <Metrics>
        <MetricCard label="Fresh 5h" value={fmtK(est.fresh_total)} sub={`main ${fmtK(est.fresh_main)} · subagents ${fmtK(est.fresh_subagent)}`} title={`${est.window_start} → ${est.window_end}`} />
        <MetricCard
          label="At last throttle"
          computing={cal.state === 'computing'}
          value={cal.available && cal.last_fresh_at_event !== null ? <>{cal.coverage !== 'full' ? <small style={{ fontSize: 14, color: 'var(--label2)' }}>≥ </small> : null}{fmtK(cal.last_fresh_at_event)}</> : <StateWord status="unknown">{cal.state === 'ready' ? 'none' : cal.state}</StateWord>}
          sub={
            cal.state === 'computing' ? 'computing'
              : cal.vs_last_throttle_ratio !== null ? `now ${cal.vs_last_throttle_ratio.toFixed(1)}× that`
              : cal.available && cal.coverage !== 'full' ? `lower bound · ${cal.coverage}`
              : cal.available ? `${cal.event_count} event${cal.event_count === 1 ? '' : 's'}`
              : 'no throttle observed'
          }
        />
        <MetricCard label="Cache reads" value={fmtK(est.cache_read_total)} sub={`not fresh · ${est.distinct_session_count} sessions`} />
        <MetricCard
          label="Live"
          value={first ? fmtPct(first.percent_used) : 'unavailable'}
          status={first ? first.status : 'unknown'}
          sub={first ? `${first.label}${claude.served_from_cache ? ' · cached' : ''}` : snap.unavailable_reason ?? 'unknown'}
          title={snap.unavailable_reason ?? undefined}
        />
      </Metrics>

      {first && (
        <>
          <SectionCap aside={`${claude.served_from_cache ? 'cached · ' : ''}${fmtAgo(snap.fetched_at, now)}`}>Live windows</SectionCap>
          <Card>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {snap.windows.map(w => (
                <QuotaBar key={w.key} value={w.percent_used} label={w.label} status={w.status} note={`resets ${w.resets_at ?? 'unknown'}`} />
              ))}
              {claude.projection.available && <div style={{ fontSize: 11, color: 'var(--label2)' }}>{claude.projection.label}</div>}
            </div>
          </Card>
        </>
      )}

      <SectionCap>Credential sources</SectionCap>
      <Group>
        {snap.credential_probes.length === 0 && <Empty>None</Empty>}
        {snap.credential_probes.map(p => (
          <Row key={p.source} static>
            <RowMain title={p.label} sub={p.token_found ? (p.cached ? 'token present · remembered, not re-sent' : 'token present') : 'no token'} />
            <Chip tone={p.outcome === 'ok' ? 'ok' : p.outcome === 'absent' ? 'unknown' : 'stale'}>{p.outcome}</Chip>
          </Row>
        ))}
        {(snap.diagnostic || claude.breaker_open || snap.http_status) && (
          <Row static>
            <RowMain
              title={<span style={{ fontWeight: 400, color: 'var(--label2)', fontSize: 12 }}>
                {snap.http_status ? `http ${snap.http_status}` : ''}
                {snap.diagnostic ? ` · ${snap.diagnostic}` : ''}
                {claude.breaker_open ? ` · breaker open until ${claude.breaker_open_until ?? '?'}` : ''}
                {claude.consecutive_failures ? ` · ${claude.consecutive_failures} consecutive failures` : ''}
              </span>}
            />
          </Row>
        )}
      </Group>

      <SectionCap aside={`${est.main_files_scanned} main · ${est.subagent_files_scanned} subagent files`}>Usage estimate</SectionCap>
      {est.by_role_model.length === 0 ? (
        <Group><Empty>No data yet</Empty></Group>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Role</th><th>Model</th><th className="r">Input</th><th className="r">Output</th><th className="r">Cache write</th><th className="r">Fresh</th><th className="r">Cache read</th></tr></thead>
            <tbody>
              {est.by_role_model.map((r, i) => (
                <tr key={i}>
                  <td>{r.role}</td>
                  <td className="mono">{shortModel(r.model)}</td>
                  <td className="r">{fmtK(r.input_tokens)}</td>
                  <td className="r">{fmtK(r.output_tokens)}</td>
                  <td className="r">{fmtK(r.cache_creation_tokens)}</td>
                  <td className="r" style={{ fontWeight: 600 }}>{fmtK(r.fresh_tokens)}</td>
                  <td className="r dim">{fmtK(r.cache_read_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SectionCap aside={String(tasks.length)}>Subagent tasks</SectionCap>
      {!est.subagent_tree_found ? (
        <Group><Empty>No subagent transcripts</Empty></Group>
      ) : tasks.length === 0 ? (
        <Group><Empty>None</Empty></Group>
      ) : (
        <div className="tbl-wrap" style={{ maxHeight: 420 }}>
          <table className="tbl">
            <thead><tr><th>Task</th><th>Model</th><th className="r">Fresh</th><th className="r">Cache read</th><th className="r">Turns</th><th className="r">First</th><th className="r">Last</th></tr></thead>
            <tbody>
              {tasks.map((t, i) => (
                <tr key={i}>
                  <td style={{ overflowWrap: 'anywhere', minWidth: 160 }} title={t.source_path}>{t.label}</td>
                  <td className="mono">{shortModel(t.model)}</td>
                  <td className="r" style={{ fontWeight: 600 }}>{fmtK(t.fresh_tokens)}</td>
                  <td className="r dim">{fmtK(t.cache_read_tokens)}</td>
                  <td className="r">{t.turns}</td>
                  <td className="r dim" style={{ whiteSpace: 'nowrap' }}>{fmtAgo(t.first_activity, now)}</td>
                  <td className="r dim" style={{ whiteSpace: 'nowrap' }}>{fmtAgo(t.last_activity, now)}{t.truncated ? ' · partial' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SectionCap>Throttle</SectionCap>
      <Card>
        <KV
          rows={[
            cal.state === 'computing'
              ? ['Events', <><span className="skeleton" /> computing</>]
              : cal.available && cal.last_event
                ? ['Last event', <><span className="num">{fmtAgo(cal.last_event.at, now)}</span> · {cal.last_event.rate_limit_type ?? 'unknown window'}{cal.last_event.resets_at ? ` · reset ${cal.last_event.resets_at}` : ''}</>]
                : ['Events', cal.state === 'ready' ? 'none observed' : cal.state],
            cal.available && cal.last_fresh_at_event !== null ? ['Fresh at event', <span className="num">{cal.coverage !== 'full' ? '≥ ' : ''}{fmtK(cal.last_fresh_at_event)}{cal.coverage !== 'full' ? <span style={{ color: 'var(--label3)' }}> ({cal.coverage})</span> : null}</span>] : null,
            cal.event_count > 1 ? [`Across ${cal.event_count} events`, <span className="num">min {fmtK(cal.min_fresh_at_event)} · median {fmtK(cal.median_fresh_at_event)}</span>] : null,
          ]}
        />
      </Card>

      <SectionCap>Codex</SectionCap>
      <Card>
        <KV
          rows={[
            ['Quota', <><StatusDot status={codex.available ? 'ok' : 'unknown'} /> {codex.label}{codex.auth_mode ? ` · ${codex.auth_mode}` : ''}{codex.note ? <span style={{ color: 'var(--label3)' }}> · {codex.note}</span> : null}</>],
            ...codex.windows.map(w => [w.limit_id, <span className="num">{w.used_percent ?? '–'}% · resets {w.resets_at ?? 'unknown'}</span>] as [string, ReactNode]),
          ]}
        />
      </Card>
    </div>
  )
}

export function QuotaInspector(_props: InspectorProps) {
  return null
}
