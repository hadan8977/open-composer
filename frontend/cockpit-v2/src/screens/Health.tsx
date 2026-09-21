// Health: data freshness, cron jobs (selectable: the inspector shows each
// job's log tail), disk, memory and the cockpit process itself.
import { useMemo } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import { fmtAgo, fmtBytes, fmtDate, fmtPct, useJson, useNow, type CronJob, type HealthPayload } from '../api'
import {
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
  StateWord,
  StatusDot,
  matches,
  plural,
} from '../components/Shared'

function jobKey(j: CronJob): string {
  return j.name
}

export default function Health({ selectedId, onSelect, search }: ScreenProps) {
  const { data, error, loading } = useJson<HealthPayload>('/api/health.json', 60_000)
  const now = useNow()
  const jobs = useMemo(() => (data ? data.report.cron.jobs.filter(j => matches(search, j.name, j.schedule, j.command, j.note)) : []), [data, search])
  const sources = useMemo(() => (data ? data.report.data_freshness.filter(s => matches(search, s.name, s.detail)) : []), [data, search])
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null

  const rep = data.report
  const stale = rep.data_freshness.filter(s => s.status === 'stale').length
  const warn = rep.data_freshness.filter(s => s.status === 'warn').length
  const failing = rep.cron.jobs.filter(j => j.status === 'stale').length

  return (
    <div>
      <Metrics>
        <MetricCard label="Stale sources" value={stale} status={stale ? 'stale' : warn ? 'warn' : 'ok'} sub={`${warn} warn · ${rep.data_freshness.length} sources`} />
        <MetricCard
          label="Cron failing"
          value={rep.cron.available ? failing : 'unknown'}
          status={rep.cron.available ? (failing ? 'stale' : 'ok') : 'unknown'}
          sub={rep.cron.available ? `of ${plural(rep.cron.jobs.length, 'job')}` : rep.cron.error ?? 'unknown'}
          title={rep.cron.error ?? undefined}
        />
        <MetricCard
          label="Disk free"
          value={rep.disk ? fmtBytes(rep.disk.available_bytes) : 'unknown'}
          status={rep.disk?.status ?? 'unknown'}
          sub={rep.disk ? `${fmtPct(rep.disk.used_percent)} used of ${fmtBytes(rep.disk.total_bytes)} · ${rep.disk.mount}` : undefined}
        />
        <MetricCard
          label="Memory free"
          value={rep.memory ? fmtBytes(rep.memory.available_bytes) : 'unknown'}
          status={rep.memory?.status ?? 'unknown'}
          sub={rep.memory ? `${fmtPct(rep.memory.used_percent)} used of ${fmtBytes(rep.memory.total_bytes)}` : undefined}
        />
      </Metrics>

      <SectionCap aside={rep.cron.available ? plural(jobs.length, 'job') : 'unknown'}>Cron jobs</SectionCap>
      <Group>
        {!rep.cron.available && <Empty>{rep.cron.error ?? 'unknown'}</Empty>}
        {rep.cron.available && jobs.length === 0 && <Empty>None</Empty>}
        {jobs.map(j => {
          const log = j.logs[0]
          const key = jobKey(j)
          return (
            <Row key={key} selected={selectedId === key} onClick={() => onSelect(selectedId === key ? null : key)} title={j.command}>
              <StatusDot status={j.status} />
              <RowMain title={j.name} sub={<><span className="mono">{j.schedule}</span>{j.note ? ` · ${j.note}` : ''}</>} />
              <RowAside
                value={log?.mtime ? fmtAgo(log.mtime, now) : 'never'}
                sub={log?.has_error_marker ? 'error marker' : log ? `${fmtBytes(log.size_bytes)} log` : 'no log'}
                tone={log?.has_error_marker ? 'stale' : undefined}
              />
            </Row>
          )
        })}
      </Group>

      <SectionCap aside={plural(sources.length, 'source')}>Data freshness</SectionCap>
      <Group>
        {sources.length === 0 && <Empty>None</Empty>}
        {sources.map(s => (
          <Row key={s.name} static>
            <StatusDot status={s.status} />
            <RowMain title={s.name} sub={s.detail} />
            <RowAside value={fmtDate(s.latest_date)} sub={s.sessions_behind === null ? s.status : `${s.sessions_behind} session${s.sessions_behind === 1 ? '' : 's'} behind`} />
          </Row>
        ))}
      </Group>

      <SectionCap>Process</SectionCap>
      <Group>
        <Row static>
          <StatusDot status={rep.process.status} />
          <RowMain title="Cockpit" sub={<>pid <span className="num">{rep.process.pid}</span></>} />
          <RowAside value={fmtBytes(rep.process.rss_bytes)} sub="resident" />
        </Row>
      </Group>
    </div>
  )
}

export function HealthInspector({ id }: InspectorProps) {
  const { data, error, loading } = useJson<HealthPayload>('/api/health.json', 0)
  const now = useNow()
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null
  const job = data.report.cron.jobs.find(j => jobKey(j) === id)
  if (!job) return <Empty>Job not found</Empty>

  return (
    <div className="fade-in">
      <InspectorHead status={job.status} eyebrow={<span className="mono">{job.schedule}</span>} title={job.name} sub={job.note ?? undefined} />
      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Command</div>
        <pre className="mono" style={{ margin: 0, padding: '8px 10px', background: 'var(--bg3)', borderRadius: 'var(--r-s)', fontSize: 11, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{job.command}</pre>
      </section>
      {job.logs.map(log => (
        <section key={log.path} style={{ padding: '12px 16px 4px' }}>
          <div className="section-cap" style={{ marginBottom: 8 }}>Log</div>
          <KV
            rows={[
              ['Path', <span className="mono">{log.path}</span>],
              ['State', <StateWord status={log.status}>{log.exists ? (log.has_error_marker ? 'error marker' : log.status) : 'missing'}</StateWord>],
              log.mtime ? ['Written', <span className="num" title={log.mtime}>{fmtAgo(log.mtime, now)}</span>] : null,
              log.size_bytes !== null ? ['Size', <span className="num">{fmtBytes(log.size_bytes)}</span>] : null,
            ]}
          />
          {log.tail_snippet ? (
            <pre className="mono" style={{ margin: '10px 0 0', padding: '8px 10px', background: 'var(--bg3)', borderRadius: 'var(--r-s)', fontSize: 11, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 320, overflow: 'auto', color: log.has_error_marker ? 'var(--stale)' : 'var(--label2)' }}>{log.tail_snippet}</pre>
          ) : (
            <div style={{ marginTop: 10 }}><Empty>No log tail</Empty></div>
          )}
        </section>
      ))}
      {job.logs.length === 0 && <div style={{ padding: '12px 16px' }}><Empty>No log configured</Empty></div>}
    </div>
  )
}
