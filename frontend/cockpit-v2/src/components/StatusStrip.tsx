// One line under the toolbar: Claude 5h/7d, the fresh-token estimate, one dot
// per live agent, data freshness, the soonest rehearsal expiry. Every slot is
// a button into the screen that explains it. Reads /api/status.json.
import type { ReactNode } from 'react'
import { fmtAgo, type Remote, type StatusPayload } from '../api'
import type { Screen } from '../App'
import { STATUS_COLOR, StatusDot, asStatus } from './Shared'

function Slot({
  onClick,
  title,
  children,
}: {
  onClick?: () => void
  title?: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        height: 24,
        padding: '0 8px',
        border: 0,
        borderRadius: 'var(--r-s)',
        background: 'transparent',
        color: 'var(--label2)',
        fontSize: 11.5,
        whiteSpace: 'nowrap',
        cursor: onClick ? 'pointer' : 'default',
        flexShrink: 0,
      }}
      className="strip-slot"
    >
      {children}
    </button>
  )
}

function Sep() {
  return <span style={{ width: 1, height: 14, background: 'var(--sep)', flexShrink: 0 }} />
}

function MiniBar({ pct, status }: { pct: number; status: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 44,
        height: 4,
        borderRadius: 2,
        background: 'var(--bg3)',
        overflow: 'hidden',
        verticalAlign: 'middle',
      }}
    >
      <span
        style={{
          display: 'block',
          width: `${Math.max(0, Math.min(100, pct))}%`,
          height: '100%',
          background: STATUS_COLOR[asStatus(status)],
        }}
      />
    </span>
  )
}

export default function StatusStrip({
  status,
  now,
  navigate,
}: {
  status: Remote<StatusPayload>
  now: number
  navigate: (screen: Screen) => void
}) {
  const s = status.data
  return (
    <div
      className="strip"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 32,
        padding: '0 8px',
        borderTop: '1px solid var(--sep)',
        overflowX: 'auto',
        scrollbarWidth: 'none',
      }}
      aria-label="status"
    >
      {!s && (
        <Slot>
          {status.error ? (
            <>
              <StatusDot status="stale" /> status unavailable
            </>
          ) : (
            <span className="skeleton" style={{ width: 120 }} />
          )}
        </Slot>
      )}

      {s && (
        <>
          {/* Claude live windows or the one reason they are not available */}
          <Slot onClick={() => navigate('quota')} title="Claude live quota">
            <span style={{ fontWeight: 600, color: 'var(--label)' }}>Claude</span>
            {s.claude.available && s.claude.bars.length > 0 ? (
              s.claude.bars.map(b => (
                <span
                  key={b.key}
                  title={`${b.label} · ${b.reset_label}${b.projection_label ? ` · ${b.projection_label}` : ''}`}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                >
                  <span style={{ color: 'var(--label3)' }}>{b.label}</span>
                  <MiniBar pct={b.width_percent} status={b.status} />
                  <span className="num" style={{ color: 'var(--label)' }}>
                    {b.percent_display}
                  </span>
                </span>
              ))
            ) : (
              <span className="chip unknown" title={s.claude.unavailable_reason ?? undefined}>
                {s.claude.unavailable_reason ?? 'unavailable'}
              </span>
            )}
          </Slot>

          <Sep />

          {/* Fresh-token estimate from transcripts */}
          <Slot onClick={() => navigate('quota')} title="Fresh tokens in the current 5h window, estimated from transcripts">
            <span className="num" style={{ color: 'var(--label)' }}>
              {s.usage_estimate.topbar_label}
            </span>
          </Slot>

          <Sep />

          {/* Codex */}
          <Slot onClick={() => navigate('quota')} title={s.codex.note || undefined}>
            <span style={{ color: 'var(--label3)' }}>Codex</span>
            <span>{s.codex.label}</span>
          </Slot>

          <Sep />

          {/* Agents: one dot each */}
          <Slot onClick={() => navigate('agents')} title={`${s.agents.length} live agents`}>
            <span style={{ display: 'inline-flex', gap: 3 }}>
              {s.agents.slice(0, 14).map(([id, st]) => (
                <StatusDot
                  key={id}
                  size={7}
                  status={st === 'running' ? 'ok' : st === 'error' ? 'stale' : st === 'idle' ? 'warn' : 'unknown'}
                  title={`${id.slice(0, 8)} · ${st}`}
                />
              ))}
            </span>
            <span className="num">
              {s.agents.length === 0 ? 'no agents' : `${s.agents.filter(a => a[1] === 'running').length} running`}
              {s.agents.length > 14 ? ` · +${s.agents.length - 14}` : ''}
            </span>
          </Slot>

          <Sep />

          <Slot onClick={() => navigate('health')} title="Data freshness">
            <StatusDot status={s.data_freshness.status} />
            <span>data {s.data_freshness.label}</span>
          </Slot>

          <Sep />

          <Slot onClick={() => navigate('paper')} title="Soonest rehearsal authorization expiry">
            <StatusDot status={s.rehearsal.status} />
            <span>{s.rehearsal.label}</span>
          </Slot>

          <span style={{ flex: 1 }} />
          <span
            className="num desktop-only"
            style={{ fontSize: 11, color: 'var(--label3)', paddingRight: 6, whiteSpace: 'nowrap' }}
            title={s.generated_at}
          >
            {fmtAgo(s.generated_at, now)}
          </span>
        </>
      )}
      <style>{`.strip::-webkit-scrollbar{display:none}.strip-slot:hover{background:var(--bg3)}`}</style>
    </div>
  )
}
