import { hypotheses, lineageEdges } from '../data/mock'
import { StatusDot, MetricCard, SectionCap } from '../components/Shared'
import { HypothesesInspector } from './Hypotheses'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  search: string
}

function buildTree() {
  const childrenOf = new Map<string, string[]>()
  const hasParent = new Set<string>()

  for (const e of lineageEdges) {
    if (!childrenOf.has(e.from)) childrenOf.set(e.from, [])
    childrenOf.get(e.from)!.push(e.to)
    hasParent.add(e.to)
  }

  const allConnected = new Set<string>()
  for (const e of lineageEdges) {
    allConnected.add(e.from)
    allConnected.add(e.to)
  }

  const roots = [...allConnected].filter(id => !hasParent.has(id))
  const isolated = hypotheses.filter(h => !allConnected.has(h.id))

  return { roots, childrenOf, isolated }
}

type NodePos = { id: string; x: number; y: number }

function layoutGraph(): NodePos[] {
  const positions: NodePos[] = []
  const levels: Map<string, number> = new Map()

  const { roots, childrenOf } = buildTree()

  function assignLevel(id: string, level: number) {
    if (!levels.has(id) || levels.get(id)! < level) {
      levels.set(id, level)
      for (const child of (childrenOf.get(id) ?? [])) {
        assignLevel(child, level + 1)
      }
    }
  }
  for (const r of roots) assignLevel(r, 0)

  const byLevel = new Map<number, string[]>()
  for (const [id, lvl] of levels) {
    if (!byLevel.has(lvl)) byLevel.set(lvl, [])
    byLevel.get(lvl)!.push(id)
  }

  const COLS = 3
  const COL_W = 180
  const ROW_H = 70

  for (const [lvl, ids] of byLevel) {
    ids.forEach((id, i) => {
      positions.push({ id, x: (i % COLS) * COL_W + 20, y: lvl * ROW_H + 20 })
    })
  }

  return positions
}

export default function Lineage({ selectedId, onSelect, search }: Props) {
  const { isolated } = buildTree()
  const positions = layoutGraph()
  const declaredEdges = lineageEdges.filter(e => e.type === 'declares').length
  const mentionedEdges = lineageEdges.filter(e => e.type === 'mentions').length
  const roots = positions.length > 0 ? new Set(positions.filter(p => p.y < 40).map(p => p.id)).size : 0

  const posMap = new Map(positions.map(p => [p.id, p]))
  const svgH = Math.max(...positions.map(p => p.y), 0) + 80

  const filteredIsolated = isolated.filter(h =>
    h.title.toLowerCase().includes(search.toLowerCase()) ||
    h.id.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, padding: 16 }}>
        <MetricCard label="Declared edges" value={declaredEdges} status="ok" />
        <MetricCard label="Mentioned edges" value={mentionedEdges} status="unk" />
        <MetricCard label="Roots" value={roots} />
      </div>

      {/* Graph */}
      <div style={{ padding: '0 16px 16px' }}>
        <div className="section-cap" style={{ padding: '0 0 8px', border: 0 }}>Connected graph</div>
        <div
          style={{
            background: 'var(--bg2)',
            borderRadius: 12,
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <svg
            width="100%"
            viewBox={`0 0 600 ${svgH}`}
            style={{ display: 'block' }}
          >
            {/* Edges */}
            {lineageEdges.map((e, i) => {
              const from = posMap.get(e.from)
              const to = posMap.get(e.to)
              if (!from || !to) return null
              return (
                <line
                  key={i}
                  x1={from.x + 70}
                  y1={from.y + 16}
                  x2={to.x + 70}
                  y2={to.y + 16}
                  stroke={e.type === 'declares' ? 'var(--tint)' : 'var(--label3)'}
                  strokeWidth={e.type === 'declares' ? 1.5 : 1}
                  strokeDasharray={e.type === 'mentions' ? '4 3' : undefined}
                  opacity={0.6}
                />
              )
            })}

            {/* Nodes */}
            {positions.map(p => {
              const h = hypotheses.find(x => x.id === p.id)
              if (!h) return null
              const sel = selectedId === h.id
              return (
                <g
                  key={p.id}
                  transform={`translate(${p.x}, ${p.y})`}
                  style={{ cursor: 'pointer' }}
                  onClick={() => onSelect(sel ? null : h.id)}
                >
                  <rect
                    width={140}
                    height={40}
                    rx={8}
                    fill={sel ? 'var(--tint)' : 'var(--bg3)'}
                    opacity={sel ? 1 : 0.9}
                  />
                  <circle cx={14} cy={20} r={4} fill={
                    h.status === 'ok' ? 'var(--ok)' :
                    h.status === 'warn' ? 'var(--warn)' :
                    h.status === 'stale' ? 'var(--stale)' : 'var(--unk)'
                  } />
                  <text x={26} y={14} fontSize={9} fill={sel ? 'rgba(255,255,255,0.7)' : 'var(--label3)'} fontFamily="ui-monospace, monospace">
                    {h.id.slice(-8)}
                  </text>
                  <text x={26} y={28} fontSize={10} fill={sel ? 'white' : 'var(--label)'} fontFamily="-apple-system, sans-serif">
                    {h.title.slice(0, 16)}{h.title.length > 16 ? '…' : ''}
                  </text>
                </g>
              )
            })}
          </svg>

          {/* Legend */}
          <div style={{ display: 'flex', gap: 16, padding: '8px 16px 12px', borderTop: '1px solid var(--sep)', fontSize: 11, color: 'var(--label3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <svg width={24} height={6}><line x1={0} y1={3} x2={24} y2={3} stroke="var(--tint)" strokeWidth={1.5} /></svg>
              declares
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <svg width={24} height={6}><line x1={0} y1={3} x2={24} y2={3} stroke="var(--label3)" strokeWidth={1} strokeDasharray="4 3" /></svg>
              mentions
            </div>
          </div>
        </div>
      </div>

      {/* Isolated */}
      {filteredIsolated.length > 0 && (
        <div style={{ padding: '0 16px 16px' }}>
          <SectionCap>Isolated</SectionCap>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
            {filteredIsolated.map(h => (
              <div
                key={h.id}
                onClick={() => onSelect(selectedId === h.id ? null : h.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 10px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  background: selectedId === h.id ? 'rgba(0,122,255,0.10)' : 'var(--bg2)',
                }}
              >
                <StatusDot status={h.status} />
                <span className="num" style={{ fontSize: 11, color: 'var(--label3)' }}>{h.id.slice(-8)}</span>
                <span style={{ fontSize: 12, color: 'var(--label)' }}>{h.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function LineageInspector({ id }: { id: string }) {
  return <HypothesesInspector id={id} />
}
