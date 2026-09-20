import { useState, useEffect, useRef, useCallback } from 'react'
import StatusStrip from './components/StatusStrip'
import Hypotheses, { HypothesesInspector } from './screens/Hypotheses'
import Agents, { AgentsInspector } from './screens/Agents'
import Paper, { PaperInspector } from './screens/Paper'
import Quota, { QuotaInspector } from './screens/Quota'
import Health, { HealthInspector } from './screens/Health'
import Lineage, { LineageInspector } from './screens/Lineage'

type Screen = 'hypotheses' | 'lineage' | 'agents' | 'paper' | 'quota' | 'health'

const SCREENS: { id: Screen; label: string; glyph: string }[] = [
  { id: 'hypotheses', label: 'Hypotheses', glyph: '⬡' },
  { id: 'lineage', label: 'Lineage', glyph: '⋮' },
  { id: 'agents', label: 'Agents', glyph: '◉' },
  { id: 'paper', label: 'Paper', glyph: '▦' },
  { id: 'quota', label: 'Quota', glyph: '◎' },
  { id: 'health', label: 'Health', glyph: '◫' },
]

export default function App() {
  const [screen, setScreen] = useState<Screen>('hypotheses')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [mobileSheet, setMobileSheet] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  const navigate = useCallback((s: Screen) => {
    setScreen(s)
    setSelectedId(null)
    setMobileSheet(false)
  }, [])

  const select = useCallback((id: string | null) => {
    setSelectedId(id)
    if (id) setMobileSheet(true)
    else setMobileSheet(false)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey) {
        const num = parseInt(e.key)
        if (num >= 1 && num <= 6) {
          e.preventDefault()
          navigate(SCREENS[num - 1].id)
          return
        }
        if (e.key === 'f') {
          e.preventDefault()
          searchRef.current?.focus()
          return
        }
      }
      if (e.key === 'Escape') {
        setSelectedId(null)
        setMobileSheet(false)
        if (document.activeElement === searchRef.current) {
          searchRef.current?.blur()
          setSearch('')
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  const screenProps = { selectedId, onSelect: select, search }

  function Inspector() {
    if (!selectedId) return null
    switch (screen) {
      case 'hypotheses': return <HypothesesInspector id={selectedId} />
      case 'lineage': return <LineageInspector id={selectedId} />
      case 'agents': return <AgentsInspector id={selectedId} />
      case 'paper': return <PaperInspector id={selectedId} />
      case 'quota': return <QuotaInspector id={selectedId} />
      case 'health': return <HealthInspector id={selectedId} />
      default: return null
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>

      {/* ── Toolbar ────────────────────────────────────────────── */}
      <header
        className="glass"
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          borderBottom: '1px solid var(--sep)',
          height: 44,
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px',
          gap: 8,
          flexShrink: 0,
        }}
      >
        {/* App mark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 12 }}>
          <div
            style={{
              width: 22,
              height: 22,
              borderRadius: 6,
              background: 'var(--tint)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              color: 'white',
              fontWeight: 700,
            }}
          >
            C
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--label)', letterSpacing: '-0.01em' }}>
            Cockpit
          </span>
        </div>

        {/* Screen tabs — hidden on mobile */}
        <div
          style={{
            display: 'flex',
            gap: 2,
            flex: 1,
          }}
          className="desktop-tabs"
        >
          {SCREENS.map((s, i) => (
            <button
              key={s.id}
              onClick={() => navigate(s.id)}
              title={`⌘${i + 1}`}
              style={{
                padding: '4px 10px',
                borderRadius: 6,
                border: 'none',
                background: screen === s.id ? 'rgba(0,122,255,0.12)' : 'transparent',
                color: screen === s.id ? 'var(--tint)' : 'var(--label2)',
                fontSize: 13,
                fontWeight: screen === s.id ? 600 : 400,
                cursor: 'pointer',
                transition: 'background 0.1s, color 0.1s',
              }}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'var(--bg3)',
            borderRadius: 8,
            padding: '4px 10px',
            minWidth: 160,
          }}
        >
          <svg width={13} height={13} viewBox="0 0 16 16" fill="none">
            <circle cx={6.5} cy={6.5} r={5} stroke="var(--label3)" strokeWidth={1.5} />
            <line x1={10.5} y1={10.5} x2={14} y2={14} stroke="var(--label3)" strokeWidth={1.5} strokeLinecap="round" />
          </svg>
          <input
            ref={searchRef}
            type="text"
            placeholder="Filter  ⌘F"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              border: 'none',
              background: 'transparent',
              outline: 'none',
              fontSize: 12,
              color: 'var(--label)',
              width: '100%',
            }}
          />
        </div>
      </header>

      {/* ── Status strip ──────────────────────────────────────── */}
      <StatusStrip />

      {/* ── Body ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Sidebar — desktop only */}
        <nav
          className="glass"
          style={{
            width: 'var(--sidebar)',
            borderRight: '1px solid var(--sep)',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            flexShrink: 0,
            paddingTop: 8,
          }}
        >
          {SCREENS.map((s, i) => (
            <SidebarItem
              key={s.id}
              active={screen === s.id}
              glyph={s.glyph}
              label={s.label}
              shortcut={`⌘${i + 1}`}
              onClick={() => navigate(s.id)}
            />
          ))}

          <div style={{ flex: 1 }} />
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--sep)', fontSize: 11, color: 'var(--label3)' }}>
            <div>Updated 2m ago</div>
            <div style={{ marginTop: 2, color: 'var(--label3)' }}>2026-09-20 14:58</div>
          </div>
        </nav>

        {/* Main content */}
        <main
          style={{
            flex: 1,
            overflowY: 'auto',
            paddingBottom: 80,
          }}
        >
          {screen === 'hypotheses' && <Hypotheses {...screenProps} />}
          {screen === 'lineage' && <Lineage {...screenProps} />}
          {screen === 'agents' && <Agents {...screenProps} />}
          {screen === 'paper' && <Paper {...screenProps} />}
          {screen === 'quota' && <Quota {...screenProps} />}
          {screen === 'health' && <Health {...screenProps} />}
        </main>

        {/* Inspector — desktop */}
        {selectedId && (
          <aside
            className="glass slide-in"
            style={{
              width: 'var(--inspector)',
              borderLeft: '1px solid var(--sep)',
              overflowY: 'auto',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Inspector header */}
            <div
              style={{
                height: 40,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 12px 0 16px',
                borderBottom: '1px solid var(--sep)',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--label2)' }}>
                Inspector
              </span>
              <button
                onClick={() => select(null)}
                style={{
                  border: 'none',
                  background: 'var(--bg3)',
                  color: 'var(--label2)',
                  borderRadius: 6,
                  width: 22,
                  height: 22,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  fontSize: 14,
                }}
                title="Esc"
              >
                ×
              </button>
            </div>
            <Inspector />
          </aside>
        )}
      </div>

      {/* ── Mobile bottom sheet ───────────────────────────────── */}
      {mobileSheet && selectedId && (
        <>
          <div
            onClick={() => { setMobileSheet(false); setSelectedId(null) }}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.3)',
              zIndex: 80,
            }}
          />
          <div
            className="glass slide-in"
            style={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              maxHeight: '80vh',
              zIndex: 90,
              borderRadius: '20px 20px 0 0',
              overflowY: 'auto',
              borderTop: '1px solid var(--sep)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                padding: '10px 0 4px',
              }}
            >
              <div style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--sep)' }} />
            </div>
            <Inspector />
            <div style={{ height: 32 }} />
          </div>
        </>
      )}

      {/* ── Mobile floating tab bar ───────────────────────────── */}
      <div
        className="glass mobile-tabbar"
        style={{
          position: 'fixed',
          bottom: 12,
          left: 16,
          right: 16,
          borderRadius: 20,
          border: '1px solid var(--glass-bdr)',
          zIndex: 60,
          display: 'flex',
          justifyContent: 'space-around',
          padding: '8px 4px',
        }}
      >
        {SCREENS.slice(0, 5).map(s => (
          <button
            key={s.id}
            onClick={() => navigate(s.id)}
            style={{
              border: 'none',
              background: 'transparent',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              padding: '2px 8px',
              cursor: 'pointer',
              color: screen === s.id ? 'var(--tint)' : 'var(--label3)',
            }}
          >
            <span style={{ fontSize: 18, lineHeight: 1 }}>{s.glyph}</span>
            <span style={{ fontSize: 9, fontWeight: screen === s.id ? 600 : 400 }}>
              {s.label}
            </span>
          </button>
        ))}
        <button
          onClick={() => navigate('health')}
          style={{
            border: 'none',
            background: 'transparent',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 2,
            padding: '2px 8px',
            cursor: 'pointer',
            color: screen === 'health' ? 'var(--tint)' : 'var(--label3)',
          }}
        >
          <span style={{ fontSize: 18, lineHeight: 1 }}>···</span>
          <span style={{ fontSize: 9, fontWeight: screen === 'health' ? 600 : 400 }}>More</span>
        </button>
      </div>

      <style>{`
        @media (min-width: 768px) {
          .mobile-tabbar { display: none !important; }
        }
        @media (max-width: 767px) {
          nav.glass[style*="var(--sidebar)"] { display: none !important; }
          .desktop-tabs { display: none !important; }
        }
      `}</style>
    </div>
  )
}

function SidebarItem({
  active,
  glyph,
  label,
  shortcut,
  onClick,
}: {
  active: boolean
  glyph: string
  label: string
  shortcut: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 14px',
        border: 'none',
        background: active ? 'rgba(0,122,255,0.10)' : 'transparent',
        borderLeft: active ? '2px solid var(--tint)' : '2px solid transparent',
        cursor: 'pointer',
        width: '100%',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
    >
      <span
        style={{
          fontSize: 15,
          color: active ? 'var(--tint)' : 'var(--label3)',
          width: 18,
          textAlign: 'center',
        }}
      >
        {glyph}
      </span>
      <span
        style={{
          flex: 1,
          fontSize: 13,
          fontWeight: active ? 600 : 400,
          color: active ? 'var(--label)' : 'var(--label2)',
        }}
      >
        {label}
      </span>
      <span style={{ fontSize: 10, color: 'var(--label3)' }}>{shortcut}</span>
    </button>
  )
}
