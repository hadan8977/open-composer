// Lineage: the connected part of the card graph, laid out by the server
// (columns = depth from a root), plus the isolated cards as a list. On the
// phone the same graph is an indented list. Same inspector as Hypotheses.
import { useMemo } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import { useJson, type LineagePayload } from '../api'
import { Card, Empty, ErrorNote, Group, Loading, MetricCard, Metrics, Row, RowAside, RowMain, SectionCap, StatusDot, matches, plural } from '../components/Shared'
import { STATUS_COLOR } from '../components/Shared'
import { HypothesesInspector, edgeLabel } from './Hypotheses'

const NODE_W = 196
const NODE_H = 40

/** Cut a title so it fits the node box: CJK glyphs are about twice as wide
 *  as Latin ones at 11px, so they cost two units each. */
function fitTitle(title: string, units = 27): string {
  let used = 0
  let out = ''
  for (const ch of title) {
    const w = /[\u1100-\u115f\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe30-\ufe4f\uff00-\uff60\uffe0-\uffe6\u3000-\u303f]/.test(ch) ? 2 : 1
    if (used + w > units) return `${out}…`
    used += w
    out += ch
  }
  return out
}

export default function Lineage({ selectedId, onSelect, search }: ScreenProps) {
  const { data, error, loading } = useJson<LineagePayload>('/api/lineage.json', 60_000)
  const byId = useMemo(() => new Map((data?.nodes ?? []).map(n => [n.card_id, n])), [data])
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null

  const declared = data.edges.filter(e => e.kind === 'explicit_previous').length
  const mentioned = data.edges.length - declared
  const positions = data.layout.positions
  const connected = Object.keys(positions)
  const isolated = data.isolated.filter(n => matches(search, n.card_id, n.title, n.lane))
  const q = search.trim().toLowerCase()
  const dim = (id: string) => q !== '' && !matches(search, id, byId.get(id)?.title, byId.get(id)?.lane)

  return (
    <div>
      <Metrics>
        <MetricCard label="Declared edges" value={declared} status={declared ? 'ok' : 'unknown'} sub="previous: field" />
        <MetricCard label="Mentioned edges" value={mentioned} status="unknown" sub="id cited in body" />
        <MetricCard label="Connected" value={connected.length} sub={`of ${plural(data.nodes.length, 'card')}`} />
        <MetricCard label="Isolated" value={data.isolated.length} sub="no edge either way" />
      </Metrics>

      <SectionCap aside={`${connected.length} nodes · ${data.edges.length} edges`}>Connected graph</SectionCap>
      {connected.length === 0 ? (
        <Group>
          <Empty>None</Empty>
        </Group>
      ) : (
        <>
          <div className="desktop-only">
            <Card pad={0}>
              <div style={{ overflow: 'auto', padding: 8 }}>
                <svg
                  viewBox={`0 0 ${data.layout.width} ${data.layout.height}`}
                  width={data.layout.width}
                  height={data.layout.height}
                  style={{ display: 'block', minWidth: Math.min(data.layout.width, 640), maxWidth: '100%', height: 'auto' }}
                  role="img"
                  aria-label="lineage graph"
                >
                  {data.edges.map((e, i) => {
                    const a = positions[e.source]
                    const b = positions[e.target]
                    if (!a || !b) return null
                    const x1 = a[0] + NODE_W
                    const y1 = a[1] + NODE_H / 2
                    const x2 = b[0]
                    const y2 = b[1] + NODE_H / 2
                    const dx = Math.max(24, (x2 - x1) / 2)
                    const declaredEdge = e.kind === 'explicit_previous'
                    return (
                      <path
                        key={i}
                        d={`M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
                        fill="none"
                        stroke={declaredEdge ? 'var(--tint)' : 'var(--label3)'}
                        strokeWidth={declaredEdge ? 1.6 : 1}
                        strokeDasharray={declaredEdge ? undefined : '4 3'}
                        opacity={dim(e.source) || dim(e.target) ? 0.25 : 0.8}
                      >
                        <title>{`${e.source} → ${e.target} · ${edgeLabel(e.kind)}`}</title>
                      </path>
                    )
                  })}
                  <defs>
                    <clipPath id="node-clip">
                      <rect width={NODE_W} height={NODE_H} rx={8} />
                    </clipPath>
                  </defs>
                  {connected.map(id => {
                    const n = byId.get(id)
                    const [x, y] = positions[id]
                    const sel = selectedId === id
                    const status = data.node_status[id] ?? 'unknown'
                    const title = n?.title ?? ''
                    return (
                      <g key={id} transform={`translate(${x}, ${y})`} style={{ cursor: 'pointer' }} onClick={() => onSelect(sel ? null : id)} opacity={dim(id) ? 0.35 : 1} clipPath="url(#node-clip)">
                        <rect width={NODE_W} height={NODE_H} rx={8} fill={sel ? 'var(--tint)' : 'var(--bg3)'} stroke={sel ? 'var(--tint)' : 'var(--sep)'} />
                        <circle cx={14} cy={NODE_H / 2} r={4} fill={sel ? 'white' : STATUS_COLOR[status]} />
                        <text x={26} y={16} fontSize={10} fill={sel ? 'rgba(255,255,255,0.75)' : 'var(--label2)'} fontFamily="var(--mono)">
                          {id}
                        </text>
                        <text x={26} y={30} fontSize={11} fill={sel ? 'white' : 'var(--label)'} fontFamily="var(--font)">
                          {fitTitle(title)}
                        </text>
                        <title>{`${id} · ${title} · ${n?.lane ?? ''}`}</title>
                      </g>
                    )
                  })}
                </svg>
              </div>
              <div style={{ display: 'flex', gap: 16, padding: '8px 14px 10px', borderTop: '1px solid var(--sep)', fontSize: 11, color: 'var(--label3)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <svg width={24} height={6}><line x1={0} y1={3} x2={24} y2={3} stroke="var(--tint)" strokeWidth={1.6} /></svg>
                  declared
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <svg width={24} height={6}><line x1={0} y1={3} x2={24} y2={3} stroke="var(--label3)" strokeWidth={1} strokeDasharray="4 3" /></svg>
                  mentioned
                </span>
                <span>left to right = earlier to later</span>
              </div>
            </Card>
          </div>

          <div className="mobile-only" style={{ flexDirection: 'column' }}>
            <Group>
              {data.mobile_rows.map((r, i) => (
                <Row key={`${r.card_id}-${i}`} selected={selectedId === r.card_id} onClick={() => onSelect(selectedId === r.card_id ? null : r.card_id)}>
                  <span style={{ width: r.depth * 14, flexShrink: 0 }} aria-hidden />
                  <StatusDot status={data.node_status[r.card_id] ?? 'unknown'} />
                  <RowMain id={r.card_id} title={r.is_cycle_repeat ? `${r.title} · repeat` : r.title} sub={r.edge_label ? `${r.edge_label} · ${r.lane}` : r.lane} />
                </Row>
              ))}
            </Group>
          </div>
        </>
      )}

      <div className="desktop-only">
      <SectionCap aside={plural(isolated.length, 'card')}>Isolated</SectionCap>
      <Group>
        {isolated.length === 0 && <Empty>None</Empty>}
        {isolated.map(n => (
          <Row key={n.card_id} selected={selectedId === n.card_id} onClick={() => onSelect(selectedId === n.card_id ? null : n.card_id)}>
            <StatusDot status={data.node_status[n.card_id] ?? 'unknown'} />
            <RowMain id={n.card_id} title={n.title} sub={n.lane} />
            <RowAside value={<span style={{ fontWeight: 400, fontSize: 11, color: 'var(--label3)' }}>{n.kind}</span>} />
          </Row>
        ))}
      </Group>
      </div>
    </div>
  )
}

export function LineageInspector(props: InspectorProps) {
  return <HypothesesInspector {...props} />
}
