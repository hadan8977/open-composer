// Shell. Figma Make's structure kept: a 44px glass toolbar, a status strip,
// a glass sidebar and a right inspector on desktop; a floating tab bar and a
// bottom sheet on the phone. Routing is the URL hash (`#/agents/<id>`) so a
// selected record survives reload and can be shared.
import { useCallback, useEffect, useRef, useState, type ReactNode, type UIEvent } from 'react'
import StatusStrip from './components/StatusStrip'
import { fmtAgo, useJson, useNow, type StatusPayload } from './api'
import Hypotheses, { HypothesesInspector } from './screens/Hypotheses'
import Lineage, { LineageInspector } from './screens/Lineage'
import Agents, { AgentsInspector } from './screens/Agents'
import Paper, { PaperInspector } from './screens/Paper'
import Quota, { QuotaInspector } from './screens/Quota'
import Health, { HealthInspector } from './screens/Health'

export type Screen = 'hypotheses' | 'lineage' | 'agents' | 'paper' | 'quota' | 'health'

export interface ScreenProps {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
  navigate: (screen: Screen, id?: string) => void
}
export interface InspectorProps {
  id: string
  onSelect: (id: string | null) => void
  navigate: (screen: Screen, id?: string) => void
}

function Icon({ d, extra }: { d: string; extra?: ReactNode }) {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
      {extra}
    </svg>
  )
}

const SCREENS: { id: Screen; label: string; icon: ReactNode; inspector: string }[] = [
  { id: 'hypotheses', label: 'Hypotheses', icon: <Icon d="M3 4.5h10M3 8h10M3 11.5h6" />, inspector: 'Card' },
  { id: 'lineage', label: 'Lineage', icon: <Icon d="M6 4.5l4 3M6 11.5l4-3" extra={<><circle cx={4} cy={4} r={2} /><circle cx={12} cy={8} r={2} /><circle cx={4} cy={12} r={2} /></>} />, inspector: 'Card' },
  { id: 'agents', label: 'Agents', icon: <Icon d="M8 2.2v1.6M8 12.2v1.6M2.2 8h1.6M12.2 8h1.6" extra={<circle cx={8} cy={8} r={3} />} />, inspector: 'Agent' },
  { id: 'paper', label: 'Paper', icon: <Icon d="M2 12l3.5-4.5 3 2.5L14 4" />, inspector: 'Strategy' },
  { id: 'quota', label: 'Quota', icon: <Icon d="M8 4.5V8l2.5 1.5" extra={<circle cx={8} cy={8} r={6} />} />, inspector: 'Quota' },
  { id: 'health', label: 'Health', icon: <Icon d="M2 8h3l2-4 2.5 8 2-4H14" />, inspector: 'Job' },
]

const ID_RE = /^[A-Za-z0-9._~%-]{1,160}$/

function parseHash(): { screen: Screen; id: string | null } {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [s, rawId] = raw.split('/')
  const screen = SCREENS.some(x => x.id === s) ? (s as Screen) : 'hypotheses'
  let id: string | null = null
  if (rawId && ID_RE.test(rawId)) {
    try {
      id = decodeURIComponent(rawId)
    } catch {
      id = null
    }
  }
  return { screen, id }
}

function hashFor(screen: Screen, id?: string): string {
  return id ? `#/${screen}/${encodeURIComponent(id)}` : `#/${screen}`
}

function useMedia(query: string): boolean {
  const [m, setM] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const h = () => setM(mq.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [query])
  return m
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const { screen, id: selectedId } = route
  const [search, setSearch] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const narrow = useMedia('(max-width: 767px)')
  const status = useJson<StatusPayload>('/api/status.json', 30_000)
  const now = useNow()
  const [tabMin, setTabMin] = useState(false)
  const lastY = useRef(0)

  useEffect(() => {
    const h = () => setRoute(parseHash())
    window.addEventListener('hashchange', h)
    return () => window.removeEventListener('hashchange', h)
  }, [])

  const navigate = useCallback((s: Screen, id?: string) => {
    const next = hashFor(s, id)
    if (window.location.hash !== next) window.location.hash = next
  }, [])

  const select = useCallback(
    (id: string | null) => navigate(screen, id ?? undefined),
    [navigate, screen],
  )

  const meta = SCREENS.find(s => s.id === screen)!

  useEffect(() => {
    document.title = `${meta.label} · Cockpit`
    setSearch('')
    setTabMin(false)
    if (mainRef.current) mainRef.current.scrollTop = 0
  }, [screen, meta.label])

  // Keyboard: ⌘1–6 screens, ⌘F filter, Esc close, j/k or arrows move the selection.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const inField = (e.target as HTMLElement | null)?.tagName === 'INPUT'
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        const n = Number.parseInt(e.key, 10)
        if (n >= 1 && n <= 6) {
          e.preventDefault()
          navigate(SCREENS[n - 1].id)
          return
        }
        if (e.key === 'f') {
          e.preventDefault()
          searchRef.current?.focus()
          searchRef.current?.select()
          return
        }
        return
      }
      if (e.key === 'Escape') {
        if (inField) {
          searchRef.current?.blur()
          setSearch('')
          return
        }
        if (selectedId) select(null)
        return
      }
      if (inField) return
      if (e.key === 'j' || e.key === 'k' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const rows = Array.from(
          mainRef.current?.querySelectorAll<HTMLButtonElement>('button[data-row]') ?? [],
        ).filter(r => r.offsetParent !== null)
        if (rows.length === 0) return
        e.preventDefault()
        const delta = e.key === 'j' || e.key === 'ArrowDown' ? 1 : -1
        const cur = rows.findIndex(r => r.classList.contains('is-selected'))
        const next = rows[Math.max(0, Math.min(rows.length - 1, cur + delta))]
        next.click()
        next.scrollIntoView({ block: 'nearest' })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate, select, selectedId])

  const onMainScroll = (e: UIEvent<HTMLElement>) => {
    const y = e.currentTarget.scrollTop
    const dy = y - lastY.current
    if (dy > 6 && y > 48) setTabMin(true)
    else if (dy < -6 || y < 48) setTabMin(false)
    lastY.current = y
  }

  const screenProps: ScreenProps = { selectedId, onSelect: select, search, navigate }
  const inspectorProps: InspectorProps | null = selectedId
    ? { id: selectedId, onSelect: select, navigate }
    : null

  function Inspector() {
    if (!inspectorProps) return null
    switch (screen) {
      case 'hypotheses':
        return <HypothesesInspector {...inspectorProps} />
      case 'lineage':
        return <LineageInspector {...inspectorProps} />
      case 'agents':
        return <AgentsInspector {...inspectorProps} />
      case 'paper':
        return <PaperInspector {...inspectorProps} />
      case 'quota':
        return <QuotaInspector {...inspectorProps} />
      case 'health':
        return <HealthInspector {...inspectorProps} />
      default:
        return null
    }
  }

  const showInspector = Boolean(selectedId) && screen !== 'quota'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      {/* ── Toolbar + status strip (one glass block) ─────────────────── */}
      <header className="glass" style={{ position: 'sticky', top: 0, zIndex: 40, borderLeft: 0, borderRight: 0, borderTop: 0, flexShrink: 0 }}>
        <div style={{ height: 'var(--toolbar)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8 }}>
            <div
              aria-hidden
              style={{ width: 22, height: 22, borderRadius: 6, background: 'var(--tint)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}
            >
              C
            </div>
            <span className="desktop-only" style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.01em' }}>Cockpit</span>
            <span className="mobile-only" style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.01em' }}>{meta.label}</span>
          </div>

          <div className="desktop-only" style={{ display: 'flex', gap: 2, flex: 1 }}>
            {SCREENS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                onClick={() => navigate(s.id)}
                title={`⌘${i + 1}`}
                aria-current={screen === s.id ? 'page' : undefined}
                style={{
                  padding: '4px 10px',
                  borderRadius: 'var(--r-s)',
                  border: 'none',
                  background: screen === s.id ? 'var(--tint-bg)' : 'transparent',
                  color: screen === s.id ? 'var(--tint)' : 'var(--label2)',
                  fontSize: 13,
                  fontWeight: screen === s.id ? 600 : 400,
                  cursor: 'pointer',
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
          <span className="mobile-only" style={{ flex: 1 }} />

          <label
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--bg3)', borderRadius: 8, padding: '4px 10px', minWidth: narrow ? 120 : 180, flexShrink: 1 }}
          >
            <svg width={13} height={13} viewBox="0 0 16 16" fill="none" aria-hidden>
              <circle cx={6.5} cy={6.5} r={5} stroke="var(--label3)" strokeWidth={1.5} />
              <line x1={10.5} y1={10.5} x2={14} y2={14} stroke="var(--label3)" strokeWidth={1.5} strokeLinecap="round" />
            </svg>
            <input
              ref={searchRef}
              type="search"
              placeholder={narrow ? 'Filter' : 'Filter  ⌘F'}
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Filter"
              style={{ border: 'none', background: 'transparent', outline: 'none', fontSize: 12.5, color: 'var(--label)', width: '100%', minWidth: 0 }}
            />
          </label>
        </div>
        <StatusStrip status={status} now={now} navigate={navigate} />
      </header>

      {/* ── Body ─────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <nav
          className="glass desktop-only"
          style={{ width: 'var(--sidebar)', borderTop: 0, borderBottom: 0, borderLeft: 0, display: 'flex', flexDirection: 'column', overflowY: 'auto', flexShrink: 0, paddingTop: 8 }}
          aria-label="screens"
        >
          {SCREENS.map((s, i) => (
            <SidebarItem key={s.id} active={screen === s.id} icon={s.icon} label={s.label} shortcut={`⌘${i + 1}`} onClick={() => navigate(s.id)} />
          ))}
          <div style={{ flex: 1 }} />
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--sep)', fontSize: 11, color: 'var(--label3)', display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div className="num" title={status.data?.generated_at}>
              Updated {status.data ? fmtAgo(status.data.generated_at, now) : '–'}
            </div>
            <div>Read-only · Cloudflare Access at the edge</div>
            <a href="/" style={{ color: 'var(--label2)' }}>Native view</a>
          </div>
        </nav>

        <main
          ref={mainRef}
          onScroll={onMainScroll}
          style={{ flex: 1, minWidth: 0, overflowY: 'auto', paddingBottom: narrow ? 96 : 40, overscrollBehavior: 'contain' }}
        >
          {screen === 'hypotheses' && <Hypotheses {...screenProps} />}
          {screen === 'lineage' && <Lineage {...screenProps} />}
          {screen === 'agents' && <Agents {...screenProps} />}
          {screen === 'paper' && <Paper {...screenProps} />}
          {screen === 'quota' && <Quota {...screenProps} />}
          {screen === 'health' && <Health {...screenProps} />}
        </main>

        {showInspector && !narrow && (
          <aside
            key={selectedId}
            className="slide-in inspector"
            style={{ width: 'var(--inspector)', borderLeft: '1px solid var(--sep)', background: 'var(--bg2)', overflowY: 'auto', flexShrink: 0, display: 'flex', flexDirection: 'column' }}
            aria-label="inspector"
          >
            <div
              className="glass"
              style={{ position: 'sticky', top: 0, zIndex: 2, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 10px 0 16px', borderLeft: 0, borderRight: 0, borderTop: 0, flexShrink: 0 }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--label2)' }}>{meta.inspector}</span>
              <CloseButton onClick={() => select(null)} />
            </div>
            <Inspector />
          </aside>
        )}
      </div>

      {/* ── Phone: bottom sheet ──────────────────────────────────────── */}
      {showInspector && narrow && (
        <>
          <div onClick={() => select(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.32)', zIndex: 80 }} />
          <div
            key={selectedId}
            className="slide-up inspector"
            role="dialog"
            aria-label={meta.inspector}
            style={{ position: 'fixed', bottom: 0, left: 0, right: 0, maxHeight: '88vh', zIndex: 90, borderRadius: '20px 20px 0 0', overflowY: 'auto', background: 'var(--bg2)', boxShadow: 'var(--glass-shadow)', paddingBottom: 'env(safe-area-inset-bottom)' }}
          >
            <div style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px 6px 16px' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--label2)' }}>{meta.inspector}</span>
              <div aria-hidden style={{ position: 'absolute', left: '50%', top: 6, width: 36, height: 4, borderRadius: 2, background: 'var(--bg4)', transform: 'translateX(-50%)' }} />
              <CloseButton onClick={() => select(null)} />
            </div>
            <Inspector />
            <div style={{ height: 24 }} />
          </div>
        </>
      )}

      {/* ── Phone: floating tab bar ──────────────────────────────────── */}
      <nav
        className={`glass mobile-only tabbar${tabMin ? ' is-min' : ''}`}
        aria-label="screens"
        style={{ position: 'fixed', bottom: 'max(12px, env(safe-area-inset-bottom))', left: 14, right: 14, borderRadius: 22, boxShadow: 'var(--glass-shadow)', zIndex: 60, display: 'flex', justifyContent: 'space-around', padding: '6px 4px' }}
      >
        {SCREENS.map(s => (
          <button
            key={s.id}
            type="button"
            onClick={() => navigate(s.id)}
            aria-current={screen === s.id ? 'page' : undefined}
            style={{ border: 'none', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, padding: '4px 6px', minWidth: 48, cursor: 'pointer', color: screen === s.id ? 'var(--tint)' : 'var(--label2)' }}
          >
            <span style={{ display: 'inline-flex', transform: 'scale(1.2)' }}>{s.icon}</span>
            <span style={{ fontSize: 9.5, fontWeight: screen === s.id ? 600 : 500 }}>{s.label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Close (Esc)"
      aria-label="Close"
      style={{ border: 'none', background: 'var(--bg3)', color: 'var(--label2)', borderRadius: '50%', width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}
    >
      ×
    </button>
  )
}

function SidebarItem({ active, icon, label, shortcut, onClick }: { active: boolean; icon: ReactNode; label: string; shortcut: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        margin: '1px 8px',
        padding: '7px 10px',
        border: 'none',
        borderRadius: 'var(--r-s)',
        background: active ? 'var(--tint-bg)' : 'transparent',
        cursor: 'pointer',
        textAlign: 'left',
        color: active ? 'var(--tint)' : 'var(--label2)',
      }}
    >
      <span style={{ display: 'inline-flex', width: 18, justifyContent: 'center' }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 13, fontWeight: active ? 600 : 500, color: active ? 'var(--label)' : 'var(--label)' }}>{label}</span>
      <span className="num" style={{ fontSize: 10, color: 'var(--label3)' }}>{shortcut}</span>
    </button>
  )
}
