import { quotaTable, subagentTasks, quota5h, quota7d } from '../data/mock'
import { MetricCard, SectionCap, QuotaBar, fmtK } from '../components/Shared'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
}

const lastThrottle = 480000
const cacheReads = quotaTable.reduce((s, r) => s + r.cacheRead, 0)

export default function Quota({ selectedId, onSelect, search }: Props) {
  const filtered5h = quota5h.fresh
  const filtered7d = quota7d.fresh

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, padding: 16 }}>
        <MetricCard
          label="5h fresh"
          value={fmtK(filtered5h)}
          sub={`of ${fmtK(quota5h.capacity)}`}
          status={filtered5h / quota5h.capacity > 0.85 ? 'warn' : 'ok'}
        />
        <MetricCard
          label="7d fresh"
          value={fmtK(filtered7d)}
          sub={`of ${fmtK(quota7d.capacity)}`}
          status={filtered7d / quota7d.capacity > 0.85 ? 'warn' : 'ok'}
        />
        <MetricCard label="At last throttle" value={fmtK(lastThrottle)} sub="empirical cap" />
        <MetricCard label="Cache reads" value={fmtK(cacheReads)} sub="all sessions" />
      </div>

      {/* Quota bars */}
      <div style={{ padding: '0 16px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <QuotaBar value={quota5h.fresh} max={quota5h.capacity} label="5h window" />
        <QuotaBar value={quota7d.fresh} max={quota7d.capacity} label="7d window" color="var(--ok)" />
      </div>

      {/* Table by role × model */}
      <SectionCap>Usage by role & model</SectionCap>
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 12,
          }}
        >
          <thead>
            <tr style={{ color: 'var(--label3)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {['Role', 'Model', 'Input', 'Output', 'Cache write', 'Fresh', 'Cache read'].map(h => (
                <th key={h} style={{ padding: '6px 16px', textAlign: 'right', fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {quotaTable.map((r, i) => (
              <tr
                key={i}
                style={{ borderTop: '1px solid var(--sep)' }}
              >
                <td style={{ padding: '7px 16px', color: 'var(--label2)', whiteSpace: 'nowrap' }}>{r.role}</td>
                <td style={{ padding: '7px 16px', color: 'var(--tint)', whiteSpace: 'nowrap' }} className="num">{r.model}</td>
                <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label)' }}>{fmtK(r.input)}</td>
                <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label)' }}>{fmtK(r.output)}</td>
                <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label3)' }}>{fmtK(r.cacheWrite)}</td>
                <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--ok)', fontWeight: 600 }}>{fmtK(r.fresh)}</td>
                <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label3)' }}>{fmtK(r.cacheRead)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Subagent tasks */}
      <SectionCap>Subagent tasks by fresh tokens</SectionCap>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ color: 'var(--label3)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {['Task', 'Model', 'Fresh', 'Cache read', 'Turns', 'First', 'Last'].map(h => (
                <th key={h} style={{ padding: '6px 16px', textAlign: 'right', fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {subagentTasks
              .sort((a, b) => b.fresh - a.fresh)
              .filter(t => t.label.toLowerCase().includes(search.toLowerCase()))
              .map((t, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--sep)' }}>
                  <td style={{ padding: '7px 16px', color: 'var(--label)', whiteSpace: 'nowrap' }} className="num">{t.label}</td>
                  <td style={{ padding: '7px 16px', color: 'var(--tint)', whiteSpace: 'nowrap' }} className="num">{t.model}</td>
                  <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--ok)', fontWeight: 600 }}>{fmtK(t.fresh)}</td>
                  <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label3)' }}>{fmtK(t.cacheRead)}</td>
                  <td className="num" style={{ padding: '7px 16px', textAlign: 'right' }}>{t.turns}</td>
                  <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label3)' }}>{t.firstActivity}</td>
                  <td className="num" style={{ padding: '7px 16px', textAlign: 'right', color: 'var(--label3)' }}>{t.lastActivity}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function QuotaInspector({ id }: { id: string }) {
  return (
    <div className="fade-in" style={{ padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--label)', marginBottom: 12 }}>Credential sources</div>
      {[
        { source: 'ANTHROPIC_API_KEY (env)', outcome: 'ok' as const },
        { source: 'OPENAI_API_KEY (env)', outcome: 'ok' as const },
        { source: 'AWS_BEDROCK_KEY', outcome: 'absent' as const },
      ].map((c, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--sep)', fontSize: 12 }}>
          <span className="num" style={{ color: 'var(--label2)' }}>{c.source}</span>
          <span style={{ color: c.outcome === 'ok' ? 'var(--ok)' : 'var(--label3)', fontSize: 11 }}>{c.outcome}</span>
        </div>
      ))}
      <div style={{ marginTop: 16, fontSize: 12, color: 'var(--label3)' }}>
        Circuit breaker: <span style={{ color: 'var(--ok)' }}>closed</span>
      </div>
      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--label3)' }}>
        Cache age: <span className="num" style={{ color: 'var(--label)' }}>4m 12s</span>
      </div>
    </div>
  )
}
