// Shared paper comparison workspace and the existing strategy inspector.
import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import type { InspectorProps, ScreenProps } from '../App'
import {
  fmtAgo, fmtInt, fmtMoney, fmtPct, useJson, useNow,
  type PaperComparisonPayload, type StrategyPayload,
} from '../api'
import {
  AuthChipBadge, Card, Details, Empty, ErrorNote, InspectorHead, KV,
  Loading, Stat, StatGrid, StateWord, Warnings,
} from '../components/Shared'

/** Long free text stays one line until opened. */
function Clamp({ text, limit = 140 }: { text: string; limit?: number }) {
  if (text.length <= limit) return <>{text}</>
  return (
    <details>
      <summary style={{ cursor: 'pointer', listStyle: 'none' }}>
        {text.slice(0, limit).trimEnd()}… <span style={{ color: 'var(--tint)' }}>more</span>
      </summary>
      <div style={{ marginTop: 4 }}>{text}</div>
    </details>
  )
}

interface PaperComparisonController {
  update(payload: PaperComparisonPayload): void
  setFilter(query: string): void
  destroy(): void
}
interface PaperComparisonModule {
  mountPaperComparison(element: HTMLElement, payload: PaperComparisonPayload): PaperComparisonController
}

const comparisonModuleUrl = `/static/js/paper-comparison.mjs?v=${__PAPER_COMPARISON_VERSION__}`
const comparisonStyleUrl = `/static/css/paper-comparison.css?v=${__PAPER_COMPARISON_VERSION__}`

export default function Paper({ search }: ScreenProps) {
  const { data, error } = useJson<PaperComparisonPayload>('/api/paper-comparison.json', 30_000)
  const host = useRef<HTMLDivElement>(null)
  const controller = useRef<PaperComparisonController | null>(null)
  const [comparisonModule, setComparisonModule] = useState<PaperComparisonModule | null>(null)
  const [moduleError, setModuleError] = useState(false)

  useEffect(() => {
    let active = true
    let style = document.querySelector<HTMLLinkElement>('link[data-paper-comparison]')
    if (!style) {
      style = document.createElement('link')
      style.rel = 'stylesheet'
      style.href = comparisonStyleUrl
      style.dataset.paperComparison = 'true'
      document.head.append(style)
    } else if (style.getAttribute('href') !== comparisonStyleUrl) {
      style.href = comparisonStyleUrl
    }
    const styleError = () => { if (active) setModuleError(true) }
    style.addEventListener('error', styleError)
    void import(/* @vite-ignore */ comparisonModuleUrl)
      .then((module: PaperComparisonModule) => {
        if (typeof module.mountPaperComparison !== 'function') throw new Error('Missing comparison renderer')
        if (active) setComparisonModule(module)
      })
      .catch(() => { if (active) setModuleError(true) })
    return () => {
      active = false
      style.removeEventListener('error', styleError)
    }
  }, [])

  useEffect(() => {
    if (!comparisonModule || !data || !host.current) return
    try {
      if (controller.current) controller.current.update(data)
      else controller.current = comparisonModule.mountPaperComparison(host.current, data)
      controller.current.setFilter(search)
    } catch {
      setModuleError(true)
    }
  }, [comparisonModule, data])

  useEffect(() => { controller.current?.setFilter(search) }, [search])
  useEffect(() => () => {
    controller.current?.destroy()
    controller.current = null
  }, [])

  return <div className="paper-page">
    <header className="paper-page-head">
      <h1>模拟盘</h1>
      <nav className="paper-nav" aria-label="模拟盘导航">
        <a href="/paper" aria-current="page">模拟盘</a>
        <a href="/paper/accounts">账户</a>
        <a href="/paper/history">历史</a>
      </nav>
    </header>
    {moduleError || error ? <p className="paper-load-error" role="alert">
      {data && !moduleError ? '更新失败' : '模拟盘加载失败'} · <a href="/paper">打开模拟盘</a>
    </p> : (!data || !comparisonModule) && <Loading label="加载中" />}
    <div ref={host} className="paper-comparison-host" />
  </div>
}

export function PaperInspector({ id }: InspectorProps) {
  const { data, error, loading } = useJson<StrategyPayload>(`/api/paper/${encodeURIComponent(id)}.json`, 60_000)
  const now = useNow()
  if (!data) return loading ? <Loading /> : error ? <ErrorNote error={error} /> : null
  const d = data.detail
  const a = d.authorization
  const label = data.auth_state_labels[a.state]
  const chart = data.chart
  const latest = d.equity_series.points[d.equity_series.points.length - 1]

  return (
    <div className="fade-in">
      <InspectorHead
        status={a.status}
        eyebrow={<AuthChipBadge auth={a.state} label={label} />}
        title={d.name}
        sub={`cycle ${d.cycle_status ?? 'unknown'} · ${d.generated_at ? fmtAgo(d.generated_at, now) : 'never'}`}
      />

      <StatGrid>
        <Stat value={d.equity_at_last_cycle === null ? '–' : fmtMoney(d.equity_at_last_cycle, 0)} label="equity at last cycle" />
        <Stat value={a.days_remaining === null ? (a.state === 'expired' ? 'expired' : '–') : `${a.days_remaining.toFixed(1)}d`} label="to expiry" tone={a.status} />
        <Stat value={d.positions.length} label="positions" />
        <Stat value={d.orders.length} label={`orders${d.orders_window_truncated ? ' (window)' : ''}`} />
      </StatGrid>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Authorization</div>
        <KV
          rows={[
            ['State', <>
              <StateWord status={a.status}>{label}</StateWord>
              {a.state === 'observation_only' && <span style={{ color: 'var(--label3)' }}> · never permitted to submit a paper order</span>}
              {a.state === 'expired' && <span style={{ color: 'var(--label3)' }}> · orders stopped</span>}
            </>],
            a.expires_at ? ['Expires', <span className="num" title={a.expires_at}>{a.expires_at.slice(0, 16).replace('T', ' ')}Z · {fmtAgo(a.expires_at, now)}</span>] : null,
            a.scope ? ['Scope', a.scope] : null,
            ...(a.limits ? Object.entries(a.limits).map(([k, v]) => [k.replace(/_/g, ' '), <span className="num">{String(v)}</span>] as [string, ReactNode]) : []),
            a.gate_status_note ? ['Gate', <Clamp text={a.gate_status_note} />] : null,
            d.session ? ['Session', d.session] : null,
            ['Positions', d.positions_agreement],
            ['Ledger', d.has_dedicated_ledger ? 'dedicated' : 'shared'],
          ]}
        />
      </section>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Positions <span className="num" style={{ color: 'var(--label3)', textTransform: 'none', letterSpacing: 0 }}>{d.positions.length}</span></div>
        {d.positions.length === 0 ? <Empty>None</Empty> : (
          <div className="tbl-wrap" style={{ margin: 0 }}>
            <table className="tbl">
              <thead><tr><th>Symbol</th><th className="r">Target w</th><th className="r">Ledger</th><th className="r">Broker</th><th className="r">Value</th><th className="r">Unreal.</th></tr></thead>
              <tbody>
                {d.positions.map(p => (
                  <tr key={p.symbol}>
                    <td className="mono">{p.symbol}</td>
                    <td className="r">{p.target_weight === null ? '–' : p.target_weight.toFixed(3)}</td>
                    <td className="r">{p.ledger_qty ?? '–'}</td>
                    <td className="r">{p.broker_qty ?? '–'}</td>
                    <td className="r">{fmtMoney(p.market_value, 0)}</td>
                    <td className="r" style={{ color: p.unrealized_pl === null ? undefined : p.unrealized_pl >= 0 ? 'var(--ok)' : 'var(--stale)' }}>{fmtMoney(p.unrealized_pl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Orders <span className="num" style={{ color: 'var(--label3)', textTransform: 'none', letterSpacing: 0 }}>{d.orders.length}{d.orders_window_truncated ? ' · window truncated' : ''}</span></div>
        {d.orders.length === 0 ? <Empty>None</Empty> : (
          <div className="tbl-wrap" style={{ margin: 0, maxHeight: 320 }}>
            <table className="tbl">
              <thead><tr><th>Symbol</th><th>Side</th><th className="r">Qty</th><th className="r">Notional</th><th>Status</th><th className="r">Recorded</th></tr></thead>
              <tbody>
                {d.orders.map((o, i) => (
                  <tr key={`${o.broker_order_id ?? i}`}>
                    <td className="mono">{o.symbol}</td>
                    <td style={{ color: o.side === 'buy' ? 'var(--ok)' : o.side === 'sell' ? 'var(--stale)' : undefined }}>{o.side ?? '–'}</td>
                    <td className="r">{o.qty ?? '–'}</td>
                    <td className="r">{fmtMoney(o.notional, 0)}</td>
                    <td>{o.broker_status ?? '–'}{o.order_style ? <span style={{ color: 'var(--label3)' }}> · {o.order_style}</span> : null}</td>
                    <td className="r dim" title={o.recorded_at ?? undefined}>{o.recorded_at ? fmtAgo(o.recorded_at, now) : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Fills</div>
        {!d.fills.available ? <Empty>No data yet</Empty> : d.fills.sessions.length === 0 ? <Empty>None</Empty> : (
          <div className="tbl-wrap" style={{ margin: 0 }}>
            <table className="tbl">
              <thead><tr><th>Session</th><th className="r">Orders</th><th className="r">Full</th><th className="r">Partial</th><th className="r">Fill</th><th className="r">Slip vs open bps</th></tr></thead>
              <tbody>
                {d.fills.sessions.map(f => (
                  <tr key={f.session}>
                    <td>{f.session}</td>
                    <td className="r">{f.orders ?? '–'}</td>
                    <td className="r">{f.filled_full ?? '–'}</td>
                    <td className="r">{f.filled_partial ?? '–'}</td>
                    <td className="r">{f.fill_rate_by_notional === null ? '–' : fmtPct(f.fill_rate_by_notional * 100)}</td>
                    <td className="r">{f.median_slippage_vs_open_bps == null ? '–' : f.median_slippage_vs_open_bps.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ padding: '12px 16px 4px' }}>
        <div className="section-cap" style={{ marginBottom: 8 }}>Equity</div>
        {chart && chart.bars.length > 0 ? (
          <Card pad={12}>
            <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label="equity history" style={{ width: '100%', height: 'auto', display: 'block' }}>
              {chart.bars.map((b, i) => (
                <rect key={i} x={b.x} y={b.y} width={b.width} height={b.height} rx={1.5} fill="var(--tint)" opacity={0.85}>
                  <title>{b.title}</title>
                </rect>
              ))}
            </svg>
            <div className="num" style={{ fontSize: 11, color: 'var(--label3)', marginTop: 6 }}>
              {latest ? <>latest {fmtMoney(latest.equity, 0)} · {fmtAgo(latest.at, now)}</> : null}
              {d.equity_series.note ? ` · ${d.equity_series.note}` : ''}
              {' · '}{fmtInt(d.equity_series.points.length)} points
            </div>
          </Card>
        ) : (
          <Empty>No history yet{d.equity_series.note ? ` · ${d.equity_series.note}` : ''}</Empty>
        )}
      </section>

      {Object.keys(d.decision_counts).length > 0 && (
        <Details summary="Decision counts">
          <KV rows={Object.entries(d.decision_counts).map(([k, v]) => [k, <span className="num">{v}</span>])} />
        </Details>
      )}
      <Warnings items={[...d.warnings, ...a.warnings, ...d.fills.warnings, ...d.equity_series.warnings]} />
    </div>
  )
}
