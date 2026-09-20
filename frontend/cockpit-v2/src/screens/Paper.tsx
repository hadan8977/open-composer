import { strategies } from '../data/mock'
import { StatusDot, MetricCard, Row, SectionCap, AuthChipBadge, fmtUSD } from '../components/Shared'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
}

export default function Paper({ selectedId, onSelect, search }: Props) {
  const filtered = strategies.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()),
  )

  const totalEquity = strategies.reduce((s, x) => s + x.equity, 0)
  const totalPnl = strategies.reduce((s, x) => s + x.dayPnl, 0)
  const openOrders = 3
  const soonestExpiry = strategies
    .filter(s => s.auth === 'authorized' && s.daysToExpiry > 0)
    .sort((a, b) => a.daysToExpiry - b.daysToExpiry)[0]

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, padding: 16 }}>
        <MetricCard
          label="Account equity"
          value={`$${(totalEquity / 1000).toFixed(0)}K`}
          status="ok"
        />
        <MetricCard
          label="Day P&L"
          value={fmtUSD(totalPnl)}
          status={totalPnl >= 0 ? 'ok' : 'stale'}
        />
        <MetricCard label="Open orders" value={openOrders} />
        <MetricCard
          label="Soonest expiry"
          value={soonestExpiry ? `${soonestExpiry.daysToExpiry}d` : '—'}
          sub={soonestExpiry?.name}
          status={soonestExpiry && soonestExpiry.daysToExpiry <= 7 ? 'warn' : 'ok'}
        />
      </div>

      <SectionCap>Strategies</SectionCap>
      {filtered.map(s => (
        <Row key={s.id} selected={selectedId === s.id} onClick={() => onSelect(selectedId === s.id ? null : s.id)}>
          <StatusDot status={s.status} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--label)' }}>{s.name}</span>
              <AuthChipBadge auth={s.auth} />
            </div>
            <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 2 }}>
              {s.daysToExpiry > 0 ? `expires in ${s.daysToExpiry}d` : 'expired'} · last cycle {s.lastCycle}
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div
              className="num"
              style={{
                fontSize: 13,
                color: s.dayPnl > 0 ? 'var(--ok)' : s.dayPnl < 0 ? 'var(--stale)' : 'var(--label3)',
              }}
            >
              {s.dayPnl !== 0 ? fmtUSD(s.dayPnl) : '—'}
            </div>
            <div style={{ fontSize: 10, color: 'var(--label3)' }}>{s.auth === 'authorized' ? `fill ${Math.round(s.fillRate * 100)}%` : s.auth}</div>
          </div>
        </Row>
      ))}
    </div>
  )
}

export function PaperInspector({ id }: { id: string }) {
  const s = strategies.find(x => x.id === id)
  if (!s) return null

  return (
    <div className="fade-in">
      <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--sep)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <StatusDot status={s.status} />
          <AuthChipBadge auth={s.auth} />
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)' }}>{s.name}</div>
        {s.auth === 'expired' && (
          <div style={{ marginTop: 8, padding: '8px 10px', background: 'rgba(255,59,48,0.10)', borderRadius: 8, fontSize: 12, color: 'var(--stale)' }}>
            Authorization expired — orders have stopped silently.
          </div>
        )}
        {s.auth === 'observation-only' && (
          <div style={{ marginTop: 8, padding: '8px 10px', background: 'rgba(255,149,0,0.10)', borderRadius: 8, fontSize: 12, color: 'var(--warn)' }}>
            Observation only — signals computed, no orders placed.
          </div>
        )}
      </div>

      <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, borderBottom: '1px solid var(--sep)' }}>
        <div>
          <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>${s.equity.toLocaleString()}</div>
          <div style={{ fontSize: 10, color: 'var(--label3)' }}>equity</div>
        </div>
        <div>
          <div className="num" style={{ fontSize: 20, fontWeight: 600, color: s.dayPnl >= 0 ? 'var(--ok)' : 'var(--stale)' }}>
            {s.dayPnl !== 0 ? fmtUSD(s.dayPnl) : '—'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--label3)' }}>day P&L</div>
        </div>
        <div>
          <div className="num" style={{ fontSize: 14, fontWeight: 500 }}>
            {Math.round(s.targetWeight * 100)}% / {Math.round(s.actualWeight * 100)}%
          </div>
          <div style={{ fontSize: 10, color: 'var(--label3)' }}>target / actual weight</div>
        </div>
        <div>
          <div className="num" style={{ fontSize: 14, fontWeight: 500 }}>
            {s.daysToExpiry > 0 ? `${s.daysToExpiry}d` : 'expired'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--label3)' }}>to expiry</div>
        </div>
      </div>

      <div style={{ padding: 16 }}>
        <div className="section-cap" style={{ padding: 0, marginBottom: 10, marginTop: 0, border: 0 }}>
          Recent fills
        </div>
        {s.fills.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--label3)' }}>No fills</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {s.fills.map((f, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '36px 36px 36px 1fr 50px 40px',
                  gap: 8,
                  padding: '5px 0',
                  borderBottom: '1px solid var(--sep)',
                  fontSize: 11,
                  alignItems: 'center',
                }}
              >
                <span className="num" style={{ color: 'var(--label3)' }}>{f.time}</span>
                <span style={{ color: f.side === 'BUY' ? 'var(--ok)' : 'var(--stale)', fontWeight: 600 }}>{f.side}</span>
                <span className="num">{f.qty}</span>
                <span style={{ color: 'var(--label2)' }}>{f.symbol}</span>
                <span className="num" style={{ textAlign: 'right' }}>{f.price.toFixed(2)}</span>
                <span className="num" style={{ color: 'var(--label3)', textAlign: 'right' }}>{f.slippageBp}bp</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <div className="section-cap" style={{ padding: 0, marginBottom: 8, marginTop: 0, border: 0 }}>
            Last order
          </div>
          <div className="num" style={{ fontSize: 12, color: 'var(--label2)' }}>{s.lastOrder}</div>
        </div>
      </div>
    </div>
  )
}
