import { cronJobs, dataSources } from '../data/mock'
import { StatusDot, MetricCard, SectionCap, Row } from '../components/Shared'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
}

export default function Health({ selectedId, onSelect, search }: Props) {
  const stale = dataSources.filter(d => d.status === 'stale' || d.status === 'warn').length
  const failed = cronJobs.filter(c => c.exitCode !== 0).length

  const filteredCron = cronJobs.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()),
  )
  const filteredSrc = dataSources.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, padding: 16 }}>
        <MetricCard label="Stale sources" value={stale} status={stale > 0 ? 'warn' : 'ok'} />
        <MetricCard label="Failed cron" value={failed} status={failed > 0 ? 'stale' : 'ok'} />
        <MetricCard label="Disk free" value="48.3 GB" status="ok" />
        <MetricCard label="Memory free" value="12.1 GB" status="ok" />
      </div>

      <SectionCap>Cron jobs</SectionCap>
      {filteredCron.map(c => (
        <Row
          key={c.name}
          selected={selectedId === c.name}
          onClick={() => onSelect(selectedId === c.name ? null : c.name)}
        >
          <StatusDot status={c.status} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="num" style={{ fontSize: 13, color: 'var(--label)' }}>{c.name}</div>
            <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 1 }}>
              {c.schedule} · last run {c.lastRun}
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div
              className="num"
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: c.exitCode === 0 ? 'var(--ok)' : 'var(--stale)',
              }}
            >
              exit {c.exitCode}
            </div>
            {!c.logFresh && (
              <div style={{ fontSize: 10, color: 'var(--warn)' }}>log stale</div>
            )}
          </div>
        </Row>
      ))}

      <SectionCap>Data sources</SectionCap>
      {filteredSrc.map(d => (
        <Row key={d.name} selected={false}>
          <StatusDot status={d.status} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="num" style={{ fontSize: 13, color: 'var(--label)' }}>{d.name}</div>
          </div>
          <div className="num" style={{ fontSize: 12, color: 'var(--label3)' }}>{d.latestDate}</div>
        </Row>
      ))}
    </div>
  )
}

export function HealthInspector({ id }: { id: string }) {
  const job = cronJobs.find(c => c.name === id)
  if (!job) return null

  return (
    <div className="fade-in">
      <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--sep)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <StatusDot status={job.status} />
          <span
            className="num"
            style={{
              fontSize: 11,
              color: job.exitCode === 0 ? 'var(--ok)' : 'var(--stale)',
            }}
          >
            exit {job.exitCode}
          </span>
        </div>
        <div className="num" style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)' }}>{job.name}</div>
        <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 4 }}>
          {job.schedule} · last run {job.lastRun}
        </div>
      </div>

      <div style={{ padding: 16 }}>
        <div className="section-cap" style={{ padding: 0, marginBottom: 10, marginTop: 0, border: 0 }}>
          Log tail
        </div>
        <div
          style={{
            background: 'var(--bg3)',
            borderRadius: 8,
            padding: '10px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          {job.lastLogLines.map((line, i) => (
            <div
              key={i}
              className="num"
              style={{
                fontSize: 11,
                color: job.exitCode !== 0 && i > 0 ? 'var(--stale)' : 'var(--label2)',
                lineHeight: 1.5,
              }}
            >
              {line}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
