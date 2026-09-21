// Hypotheses: the main screen. Cards grouped by lane, one row each; the
// inspector shows the card's fields, criteria vs result, lineage neighbours
// and the rendered body. Reads /api/hypotheses.json and /api/hypotheses/<id>.json.
import type { ReactNode } from 'react'
import { useMemo } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import { fmtAgo, useJson, useNow, type CardPayload, type HypothesesPayload, type Status } from '../api'
import {
  Card,
  Details,
  Empty,
  ErrorNote,
  Group,
  InspectorHead,
  KV,
  Loading,
  MetricCard,
  Metrics,
  Row,
  RowAside,
  RowMain,
  SectionCap,
  StateWord,
  StatusDot,
  Warnings,
  matches,
  plural,
} from '../components/Shared'

// Mirrors `_LANE_STATUS` in open_composer/cockpit/data/hypotheses.py.
export const LANE_STATUS: Record<string, Status> = {
  shipped: 'ok',
  refuted: 'stale',
  running: 'warn',
  'on hold': 'warn',
  preregistered: 'unknown',
  proposed: 'unknown',
  approved: 'unknown',
  'data card': 'unknown',
  unclassified: 'unknown',
}
export function laneStatus(lane: string): Status {
  return LANE_STATUS[lane] ?? 'unknown'
}

export function edgeLabel(kind: string): string {
  return kind === 'explicit_previous' ? 'declared' : 'mentioned'
}

export default function Hypotheses({ selectedId, onSelect, search, navigate }: ScreenProps) {
  const { data, error, loading } = useJson<HypothesesPayload>('/api/hypotheses.json', 60_000)
  const lanes = useMemo(
    () =>
      data
        ? data.lanes
            .map(l => ({
              ...l,
              cards: l.cards.filter(c => matches(search, c.id, c.title, c.layer, c.data_layer, l.lane, c.status_text)),
            }))
            .filter(l => l.cards.length > 0)
        : [],
    [data, search],
  )
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null

  const count = (lane: string) => data.lanes.find(l => l.lane === lane)?.cards.length ?? 0
  const total = data.lanes.reduce((n, l) => n + l.cards.length, 0)
  const jump = (lane: string) => () => {
    document.getElementById(`lane-${lane.replace(/\s+/g, '-')}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  return (
    <div>
      <Metrics>
        <MetricCard label="Running" value={count('running')} status={count('running') ? 'warn' : 'unknown'} sub={`${count('preregistered')} preregistered`} onClick={jump('running')} />
        <MetricCard label="Shipped" value={count('shipped')} status={count('shipped') ? 'ok' : 'unknown'} sub={`${count('approved')} approved`} onClick={jump('shipped')} />
        <MetricCard label="Refuted" value={count('refuted')} status={count('refuted') ? 'stale' : 'unknown'} sub={`${count('on hold')} on hold`} onClick={jump('refuted')} />
        <MetricCard label="Unclassified" value={count('unclassified')} status={count('unclassified') ? 'warn' : 'unknown'} sub={`${count('data card')} data cards · ${total} total`} onClick={jump('unclassified')} />
      </Metrics>

      {lanes.length === 0 && (
        <Group>
          <Empty>None</Empty>
        </Group>
      )}
      {lanes.map(l => (
        <div key={l.lane} id={`lane-${l.lane.replace(/\s+/g, '-')}`} style={{ scrollMarginTop: 8 }}>
          <SectionCap aside={String(l.cards.length)}>
            <StateWord status={l.status}>{l.lane}</StateWord>
          </SectionCap>
          <Group>
            {l.cards.map(c => {
              const runs = c.headlines.length
              const base = l.lane === 'unclassified' ? c.status_text || 'no status line' : [c.layer ?? '–', c.data_layer].filter(Boolean).join(' · ')
              return (
                <Row key={c.id} selected={selectedId === c.id} onClick={() => onSelect(selectedId === c.id ? null : c.id)}>
                  <StatusDot status={l.status} />
                  <RowMain id={c.id} title={c.title} sub={runs ? `${base} · ${c.headlines[0]}` : base} />
                  <RowAside value={runs || '–'} sub={runs ? (runs === 1 ? 'run' : 'runs') : 'No results'} />
                </Row>
              )
            })}
          </Group>
        </div>
      ))}

      <div style={{ padding: '0 16px 12px', fontSize: 11, color: 'var(--label3)' }}>
        <button type="button" onClick={() => navigate('lineage')} style={{ border: 0, background: 'none', padding: 0, color: 'var(--tint)', cursor: 'pointer', fontSize: 11 }}>
          Lineage →
        </button>
      </div>
      {data.warnings.length > 0 && (
        <Details summary={`${plural(data.warnings.length, 'result file')} not joined`}>
          <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--label3)', fontSize: 11, lineHeight: 1.5 }}>
            {data.warnings.map((w, i) => (
              <li key={i} style={{ overflowWrap: 'anywhere' }}>{w}</li>
            ))}
          </ul>
        </Details>
      )}
    </div>
  )
}

function LinkId({ id, onSelect }: { id: string; onSelect: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onSelect(id)} className="mono" style={{ border: 0, background: 'none', padding: 0, color: 'var(--tint)', cursor: 'pointer' }}>
      {id}
    </button>
  )
}

export function HypothesesInspector({ id, onSelect }: InspectorProps) {
  const { data, error, loading } = useJson<CardPayload>(`/api/hypotheses/${encodeURIComponent(id)}.json`, 0)
  const now = useNow()
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null
  const c = data.card
  const fm = c.front_matter
  const hasCriteria = data.criteria.length > 0 || data.results.length > 0

  return (
    <div className="fade-in">
      <InspectorHead
        status={laneStatus(c.lane)}
        eyebrow={
          <>
            <span>{c.lane}</span>
            {c.lane === 'unclassified' && c.lane_reason ? <span style={{ color: 'var(--label3)' }}>· {c.lane_reason}</span> : null}
            <span style={{ color: 'var(--label3)' }}>·</span>
            <span className="mono">{c.id}</span>
          </>
        }
        title={c.title}
        sub={c.status_text || undefined}
      />

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Fields</div>
        <KV
          rows={[
            c.layer ? ['Layer', c.layer] : null,
            c.data_layer ? ['Data', c.data_layer] : null,
            c.script ? ['Script', <span className="mono">{c.script}</span>] : null,
            c.output_dir ? ['Output', <span className="mono">{c.output_dir}</span>] : null,
            c.lesson_ref ? ['Lesson', c.lesson_ref] : null,
            ['Previous', c.previous ? <LinkId id={c.previous} onSelect={onSelect} /> : <span style={{ color: 'var(--label3)' }}>None</span>],
            ['File', <span className="mono" style={{ color: 'var(--label3)' }}>{c.path}</span>],
          ]}
        />
      </section>

      {fm && fm.criteria.length > 0 && (
        <section style={{ padding: '12px 16px 4px' }}>
          <div className="section-cap" style={{ marginBottom: 8 }}>Criteria <span style={{ color: 'var(--label3)', textTransform: 'none', letterSpacing: 0 }}>front matter</span></div>
          <div className="tbl-wrap" style={{ margin: 0 }}>
            <table className="tbl">
              <thead><tr><th>Name</th><th className="r">Threshold</th><th>Direction</th></tr></thead>
              <tbody>
                {fm.criteria.map((k, i) => (
                  <tr key={i}>
                    <td>{k.name}</td>
                    <td className="r">{String(k.threshold ?? '–')}</td>
                    <td>{k.direction ?? '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>
          Criteria vs result {hasCriteria ? <span className="chip" style={{ marginLeft: 6, textTransform: 'none', letterSpacing: 0 }}>unstructured</span> : null}
        </div>
        {!hasCriteria ? (
          <Empty>No data yet</Empty>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <Card pad={12}>
              <div style={{ fontSize: 10.5, color: 'var(--label2)', marginBottom: 6, fontWeight: 600 }}>As written</div>
              {data.criteria.length === 0 ? (
                <span style={{ fontSize: 12, color: 'var(--label3)' }}>None</span>
              ) : (
                data.criteria.map((s, i) => <div key={i} className="md" dangerouslySetInnerHTML={{ __html: s.html }} />)
              )}
            </Card>
            <Card pad={12}>
              <div style={{ fontSize: 10.5, color: 'var(--label2)', marginBottom: 6, fontWeight: 600 }}>Result</div>
              {data.results.length === 0 ? (
                <span style={{ fontSize: 12, color: 'var(--label3)' }}>None</span>
              ) : (
                data.results.map((f, i) => (
                  <div key={f.iteration_id + i} style={{ marginTop: i ? 12 : 0 }}>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--label2)', marginBottom: 6 }}>
                      {f.iteration_id}
                      {f.generated_at ? <span style={{ color: 'var(--label3)' }}> · {fmtAgo(f.generated_at, now)}</span> : null}
                    </div>
                    <KV
                      rows={[
                        f.cell_count !== null ? ['Cells', <span className="num">{f.cell_count}</span>] : null,
                        ...(f.incumbent_to_beat ? Object.entries(f.incumbent_to_beat).map(([k, v]) => [k, <span className="num">{String(v)}</span>] as [string, ReactNode]) : []),
                        f.family_picks !== null ? ['Family picks', <span className="num">{f.family_picks.length}</span>] : null,
                        f.benchmarks !== null ? ['Benchmarks', <span className="num">{f.benchmarks.length}</span>] : null,
                        f.windows ? ['Windows', <span className="mono" style={{ fontSize: 11 }}>{JSON.stringify(f.windows)}</span>] : null,
                      ]}
                    />
                  </div>
                ))
              )}
            </Card>
          </div>
        )}
      </section>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Lineage <span className="num" style={{ color: 'var(--label3)' }}>{data.neighbours.length}</span></div>
        {data.neighbours.length === 0 ? (
          <Empty>None</Empty>
        ) : (
          <div className="group" style={{ margin: 0 }}>
            {data.neighbours.map((e, i) => {
              const other = e.target === c.id ? e.source : e.target
              const card = data.neighbour_cards[other]
              return (
                <Row key={i} onClick={() => onSelect(other)}>
                  {card ? <StatusDot status={card.status} /> : <StatusDot status="unknown" />}
                  <RowMain id={other} title={card?.title ?? ''} />
                  <RowAside value={<span style={{ fontWeight: 400, fontSize: 11, color: 'var(--label2)' }}>{e.target === c.id ? 'from' : 'to'} · {edgeLabel(e.kind)}</span>} />
                </Row>
              )
            })}
          </div>
        )}
      </section>

      <div style={{ height: 8 }} />
      <Details summary="Card body">
        <div className="md" style={{ padding: 12, background: 'var(--bg3)', borderRadius: 'var(--r-m)' }} dangerouslySetInnerHTML={{ __html: data.body_html }} />
      </Details>
      <Warnings items={c.parse_warnings} />
    </div>
  )
}
