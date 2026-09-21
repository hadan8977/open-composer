// Small presentational pieces shared by every screen. Figma Make's five
// screens imported these by name; the props are reconstructed from that
// usage and then tightened (four states, "None" / "No data yet" for empty).
import type { ReactNode } from 'react'
import type { AuthState, Status } from '../api'

export const STATUS_COLOR: Record<Status, string> = {
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  stale: 'var(--stale)',
  unknown: 'var(--unk)',
}

export function asStatus(s: string | null | undefined): Status {
  if (s === 'ok' || s === 'warn' || s === 'stale') return s
  return 'unknown'
}

export function StatusDot({
  status,
  size = 8,
  title,
}: {
  status: Status | string
  size?: number
  title?: string
}) {
  return (
    <span
      title={title}
      aria-label={typeof status === 'string' ? status : undefined}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        background: STATUS_COLOR[asStatus(status)],
        flexShrink: 0,
      }}
    />
  )
}

/** Dot + state word, the only way a state is ever shown as text. */
export function StateWord({ status, children }: { status: Status | string; children?: ReactNode }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
      <StatusDot status={status} />
      <span>{children ?? asStatus(status)}</span>
    </span>
  )
}

export function Metrics({ children }: { children: ReactNode }) {
  return (
    <div
      className="metrics"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: 10,
        padding: 16,
      }}
    >
      {children}
    </div>
  )
}

export function MetricCard({
  label,
  value,
  sub,
  status,
  computing,
  onClick,
  title,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  status?: Status | string
  computing?: boolean
  onClick?: () => void
  title?: string
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      onClick={onClick}
      title={title}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: '12px 14px',
        minWidth: 0,
        textAlign: 'left',
        background: 'var(--bg2)',
        border: 0,
        borderRadius: 'var(--r-m)',
        boxShadow: '0 0 0 1px var(--sep) inset',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--label2)' }}>{label}</span>
      <span
        className="num"
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 8,
          fontSize: 24,
          fontWeight: 600,
          lineHeight: 1.1,
          letterSpacing: '-0.02em',
          color: 'var(--label)',
          minHeight: 26,
        }}
      >
        {status ? (
          <span style={{ alignSelf: 'center', display: 'inline-flex' }}>
            <StatusDot status={status} size={9} />
          </span>
        ) : null}
        {computing ? <span className="skeleton" aria-label="computing" /> : value}
      </span>
      <span
        className="ellipsis"
        style={{ fontSize: 11, color: 'var(--label3)', minHeight: 14 }}
      >
        {sub ?? ' '}
      </span>
    </Tag>
  )
}

export function SectionCap({
  children,
  aside,
  first,
}: {
  children: ReactNode
  aside?: ReactNode
  first?: boolean
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 12,
        padding: first ? '0 16px 6px' : '8px 16px 6px',
        margin: '0 16px',
        marginTop: first ? 0 : 4,
      }}
      className="section-cap-wrap"
    >
      <span className="section-cap">{children}</span>
      {aside !== undefined && (
        <span className="num" style={{ fontSize: 11, color: 'var(--label3)', whiteSpace: 'nowrap' }}>
          {aside}
        </span>
      )}
    </div>
  )
}

export function Group({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <div className="group" id={id}>
      {children}
    </div>
  )
}

export function Row({
  selected,
  onClick,
  children,
  title,
  static: isStatic,
}: {
  selected?: boolean
  onClick?: () => void
  children: ReactNode
  title?: string
  static?: boolean
}) {
  if (isStatic || !onClick) {
    return (
      <div className="row static" title={title}>
        {children}
      </div>
    )
  }
  return (
    <button
      type="button"
      className={`row${selected ? ' is-selected' : ''}`}
      onClick={onClick}
      title={title}
      aria-pressed={selected}
      data-row
    >
      {children}
    </button>
  )
}

/** The left, growing part of a row: an optional id, a title, a sub line. */
export function RowMain({
  id,
  title,
  sub,
}: {
  id?: ReactNode
  title: ReactNode
  sub?: ReactNode
}) {
  return (
    <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span className="ellipsis row-title" style={{ fontSize: 13, color: 'var(--label)' }}>
        {id !== undefined && (
          <span className="mono row-id" style={{ color: 'var(--label2)', marginRight: 8 }}>
            {id}
          </span>
        )}
        <span style={{ fontWeight: 500 }}>{title}</span>
      </span>
      {sub !== undefined && (
        <span className="ellipsis" style={{ fontSize: 11, color: 'var(--label3)' }}>
          {sub}
        </span>
      )}
    </span>
  )
}

/** The right, fixed part of a row: a number and a word under it. */
export function RowAside({
  value,
  sub,
  tone,
}: {
  value: ReactNode
  sub?: ReactNode
  tone?: Status | 'tint'
}) {
  const color =
    tone === 'tint' ? 'var(--tint)' : tone ? STATUS_COLOR[tone] : 'var(--label)'
  return (
    <span style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span className="num" style={{ fontSize: 13, fontWeight: 500, color }}>
        {value}
      </span>
      {sub !== undefined && (
        <span style={{ fontSize: 10.5, color: 'var(--label3)', whiteSpace: 'nowrap' }}>{sub}</span>
      )}
    </span>
  )
}

export function Chip({
  tone,
  children,
  title,
}: {
  tone?: Status | 'tool'
  children: ReactNode
  title?: string
}) {
  return (
    <span className={`chip${tone ? ` ${tone}` : ''}`} title={title}>
      {children}
    </span>
  )
}

const AUTH_TONE: Record<AuthState, Status> = {
  authorized: 'ok',
  observation_only: 'warn',
  expired: 'stale',
}

export function AuthChipBadge({ auth, label }: { auth: AuthState; label?: string }) {
  return <Chip tone={AUTH_TONE[auth] ?? 'unknown'}>{label ?? auth.replace('_', ' ')}</Chip>
}

/** A thin usage bar. `value` is a percentage 0-100. */
export function QuotaBar({
  value,
  label,
  status = 'ok',
  right,
  note,
}: {
  value: number | null
  label: ReactNode
  status?: Status | string
  right?: ReactNode
  note?: ReactNode
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, gap: 8 }}>
        <span style={{ color: 'var(--label)' }}>{label}</span>
        <span className="num" style={{ color: 'var(--label2)' }}>
          {right ?? (value === null ? '–' : `${Math.round(pct)}%`)}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ height: 5, borderRadius: 3, background: 'var(--bg3)', overflow: 'hidden' }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 3,
            background: STATUS_COLOR[asStatus(status)],
            transition: 'width 0.4s var(--ease)',
          }}
        />
      </div>
      {note !== undefined && <div style={{ fontSize: 11, color: 'var(--label3)' }}>{note}</div>}
    </div>
  )
}

export function Empty({ children = 'None' }: { children?: ReactNode }) {
  return (
    <div
      style={{
        padding: '14px 16px',
        fontSize: 12,
        color: 'var(--label3)',
        background: 'var(--bg2)',
      }}
    >
      {children}
    </div>
  )
}

export function Card({ children, pad = 14 }: { children: ReactNode; pad?: number }) {
  return (
    <div
      style={{
        margin: '0 16px 16px',
        padding: pad,
        background: 'var(--bg2)',
        borderRadius: 'var(--r-m)',
        boxShadow: '0 0 0 1px var(--sep) inset',
      }}
      className="card"
    >
      {children}
    </div>
  )
}

/** Label / value pairs. Values wrap; labels never do. */
export function KV({ rows }: { rows: Array<[ReactNode, ReactNode] | null | false> }) {
  const real = rows.filter((r): r is [ReactNode, ReactNode] => Boolean(r))
  if (real.length === 0) return <Empty>None</Empty>
  return (
    <dl
      style={{
        display: 'grid',
        gridTemplateColumns: 'max-content 1fr',
        columnGap: 14,
        rowGap: 6,
        margin: 0,
        fontSize: 12,
      }}
    >
      {real.map(([k, v], i) => (
        <div key={i} style={{ display: 'contents' }}>
          <dt style={{ color: 'var(--label2)', whiteSpace: 'nowrap' }}>{k}</dt>
          <dd style={{ margin: 0, color: 'var(--label)', minWidth: 0, overflowWrap: 'anywhere' }}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function InspectorHead({
  status,
  eyebrow,
  title,
  sub,
}: {
  status?: Status | string
  eyebrow?: ReactNode
  title: ReactNode
  sub?: ReactNode
}) {
  return (
    <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--sep)' }}>
      {(status || eyebrow) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 6,
            fontSize: 11,
            color: 'var(--label2)',
          }}
        >
          {status && <StatusDot status={status} />}
          {eyebrow}
        </div>
      )}
      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--label)', overflowWrap: 'anywhere' }}>
        {title}
      </div>
      {sub !== undefined && (
        <div style={{ fontSize: 11, color: 'var(--label3)', marginTop: 4 }}>{sub}</div>
      )}
    </div>
  )
}

export function InspectorSection({
  title,
  aside,
  children,
}: {
  title: ReactNode
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section style={{ padding: '12px 16px 4px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 8,
          gap: 8,
        }}
      >
        <span className="section-cap">{title}</span>
        {aside !== undefined && (
          <span className="num" style={{ fontSize: 11, color: 'var(--label3)' }}>
            {aside}
          </span>
        )}
      </div>
      {children}
    </section>
  )
}

export function Stat({ value, label, tone }: { value: ReactNode; label: ReactNode; tone?: Status }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        className="num"
        style={{
          fontSize: 20,
          fontWeight: 600,
          letterSpacing: '-0.02em',
          color: tone ? STATUS_COLOR[tone] : 'var(--label)',
          overflowWrap: 'anywhere',
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--label3)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

export function StatGrid({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        padding: 16,
        borderBottom: '1px solid var(--sep)',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 14,
      }}
    >
      {children}
    </div>
  )
}

export function Details({
  summary,
  children,
  open,
}: {
  summary: ReactNode
  children: ReactNode
  open?: boolean
}) {
  return (
    <details open={open} style={{ margin: '0 16px 12px', fontSize: 12 }}>
      <summary style={{ cursor: 'pointer', color: 'var(--label2)', padding: '6px 0' }}>{summary}</summary>
      <div style={{ paddingTop: 6 }}>{children}</div>
    </details>
  )
}

export function Warnings({ items }: { items: string[] | undefined }) {
  if (!items || items.length === 0) return null
  return (
    <Details summary={`${items.length} warning${items.length === 1 ? '' : 's'}`}>
      <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--label3)', fontSize: 11, lineHeight: 1.5 }}>
        {items.map((w, i) => (
          <li key={i} style={{ overflowWrap: 'anywhere' }}>
            {w}
          </li>
        ))}
      </ul>
    </Details>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div style={{ padding: 24, fontSize: 12, color: 'var(--label3)' }}>
      <span className="skeleton" /> {label}
    </div>
  )
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <div style={{ padding: '12px 16px', fontSize: 12, color: 'var(--stale)' }}>
      <StateWord status="stale">request failed · {error}</StateWord>
    </div>
  )
}

export function Faint({ children }: { children: ReactNode }) {
  return <span style={{ color: 'var(--label3)' }}>{children}</span>
}

export function Dash() {
  return <span style={{ color: 'var(--label3)' }}>–</span>
}

/** Case-insensitive substring filter over a list of strings. */
export function matches(search: string, ...fields: Array<string | null | undefined>): boolean {
  const q = search.trim().toLowerCase()
  if (!q) return true
  return fields.some(f => (f ?? '').toLowerCase().includes(q))
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}
