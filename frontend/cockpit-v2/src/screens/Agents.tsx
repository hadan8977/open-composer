import { agents } from '../data/mock'
import { StatusDot, MetricCard, Row, SectionCap, fmtK } from '../components/Shared'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
}

const STATE_STATUS = { running: 'ok', idle: 'unk', error: 'stale' } as const

export default function Agents({ selectedId, onSelect, search }: Props) {
  const filtered = agents.filter(
    a =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.model.toLowerCase().includes(search.toLowerCase()),
  )

  const running = agents.filter(a => a.state === 'running').length
  const idle = agents.filter(a => a.state === 'idle').length
  const error = agents.filter(a => a.state === 'error').length
  const freshTotal = agents.reduce((s, a) => s + a.freshTokensToday, 0)

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, padding: 16 }}>
        <MetricCard label="Running" value={running} status="ok" />
        <MetricCard label="Idle" value={idle} status="unk" />
        <MetricCard label="Error" value={error} status={error > 0 ? 'stale' : 'ok'} />
        <MetricCard label="Fresh today" value={fmtK(freshTotal)} sub="tokens" />
      </div>

      <SectionCap>Agents</SectionCap>
      {filtered.map(a => (
        <Row key={a.id} selected={selectedId === a.id} onClick={() => onSelect(selectedId === a.id ? null : a.id)}>
          <StatusDot status={STATE_STATUS[a.state]} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--label)' }}>{a.name}</span>
              <span style={{ fontSize: 10, color: 'var(--label3)' }}>{a.provider}</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {a.lastReason}
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div className="num" style={{ fontSize: 12, color: 'var(--label2)' }}>{fmtK(a.freshTokensToday)}</div>
            <div style={{ fontSize: 10, color: 'var(--label3)' }}>{a.runtimeMin}m</div>
          </div>
        </Row>
      ))}
    </div>
  )
}


export function AgentsInspector({ id }: { id: string }) {
  const a = agents.find(x => x.id === id)
  if (!a) return null

  return (
    <div className="fade-in">
      <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--sep)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <StatusDot status={STATE_STATUS[a.state]} />
          <span style={{ fontSize: 11, color: 'var(--label2)' }}>{a.provider}</span>
          <span style={{ fontSize: 11, color: 'var(--label3)' }}>·</span>
          <span className="num" style={{ fontSize: 11, color: 'var(--label3)' }}>{a.model}</span>
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)' }}>{a.name}</div>
        <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 4 }}>
          {a.state} · {a.runtimeMin}m elapsed
        </div>
      </div>

      <div style={{ padding: 16, borderBottom: '1px solid var(--sep)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{fmtK(a.freshTokensToday)}</div>
          <div style={{ fontSize: 10, color: 'var(--label3)' }}>fresh tokens today</div>
        </div>
        {a.currentFile && (
          <div>
            <div className="num" style={{ fontSize: 11, color: 'var(--label)', wordBreak: 'break-all' }}>{a.currentFile}</div>
            <div style={{ fontSize: 10, color: 'var(--label3)' }}>reading</div>
          </div>
        )}
      </div>

      <div style={{ padding: 16 }}>
        <div className="section-cap" style={{ padding: 0, marginBottom: 10, marginTop: 0, border: 0 }}>
          Activity timeline
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {a.timeline.map((t, i) => (
            <div
              key={i}
              style={{
                display: 'grid',
                gridTemplateColumns: '48px 80px 1fr 36px',
                gap: 8,
                padding: '5px 0',
                borderBottom: '1px solid var(--sep)',
                fontSize: 11,
                alignItems: 'center',
              }}
            >
              <span className="num" style={{ color: 'var(--label3)' }}>{t.time.slice(6)}</span>
              <span style={{ color: 'var(--tint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {t.tool}
              </span>
              <span style={{ color: 'var(--label2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {t.target}
              </span>
              <span
                className="num"
                style={{
                  color: t.outcome === 'error' ? 'var(--stale)' : 'var(--label3)',
                  textAlign: 'right',
                }}
              >
                {t.durationMs >= 1000 ? `${(t.durationMs / 1000).toFixed(1)}s` : `${t.durationMs}ms`}
              </span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--label2)', lineHeight: 1.6, background: 'var(--bg3)', padding: '10px 12px', borderRadius: 8 }}>
            {a.lastReason}
          </div>
        </div>
      </div>
    </div>
  )
}

