import { useState } from 'react'
import { fmtMoney, fmtPct, type PaperDashboardReading, type PaperDashboardRow, type PaperOverviewReading } from '../api'
import { Card, Empty, matches } from '../components/Shared'

const money = (value: number | null) => value === null ? '—' : fmtMoney(value)
const tone = (value: number | null) => value === null || value === 0 ? '' : value > 0 ? 'po-positive' : 'po-negative'

export default function PaperOverview({ reading, dashboard, search = '', inspectorIds = [] }: {
  reading?: PaperOverviewReading
  dashboard?: PaperDashboardReading
  search?: string
  inspectorIds?: string[]
}) {
  const [mode, setMode] = useState<'pnl_usd' | 'return_pct'>('pnl_usd')
  const s = reading?.available ? reading.snapshot : undefined
  const percent = mode === 'return_pct'
  const chart = reading?.available ? reading.charts[mode] : undefined
  const first = reading?.daily?.[0]
  const last = reading?.daily?.[reading.daily.length - 1]
  const strategyRows: PaperDashboardRow[] = dashboard?.rows ?? (s?.rows ?? []).map(row => ({
    ...row,
    status_label: row.status === '已退出' ? '已退出' : row.pnl_usd === null ? '等待估值' : '已估值',
    status_tone: 'unknown',
    href: `/paper/ledger/${encodeURIComponent(row.id)}`,
    observed_at: s?.at_end ?? null,
  }))
  const rows = strategyRows.filter(row => matches(search, row.label, row.id, row.status_label))
  const snapshotAt = s?.at_end ?? dashboard?.snapshot_at
  const snapshotLabel = snapshotAt && Number.isFinite(Date.parse(snapshotAt))
    ? `${new Date(snapshotAt).toISOString().slice(0, 16).replace('T', ' ')} UTC`
    : null
  if (!s && strategyRows.length === 0) return <Card><Empty>暂无模拟盘数据</Empty></Card>
  const format = (value: number) => percent ? fmtPct(value, 2) : fmtMoney(value, 0)

  return <>
    {s && chart ? <section className="po-panel po-hero" aria-label="模拟盘收益">
      {snapshotLabel && <div className="po-snapshot num"><time dateTime={snapshotAt ?? undefined}>{snapshotLabel}</time>{dashboard?.stale && <span>待更新</span>}</div>}
      <div className="po-metrics num">
        <div className="po-primary-metric">
          <span className="po-label">总盈亏</span>
          <strong className={tone(s.pnl_usd)}>{money(s.pnl_usd)}</strong>
        </div>
        <div>
          <span className="po-label">收益率</span>
          <strong className={tone(s.return_pct)}>{s.return_pct === null ? '—' : fmtPct(s.return_pct, 2)}</strong>
        </div>
        <div>
          <span className="po-label">投入本金</span>
          <strong>{fmtMoney(s.capital_usd, 0)}</strong>
        </div>
      </div>
      <div className="po-chart-head">
        <h2>累计收益</h2>
        <div className="po-segment" role="group" aria-label="图表单位">
          <button type="button" aria-pressed={!percent} onClick={() => setMode('pnl_usd')}>盈亏 $</button>
          <button type="button" aria-pressed={percent} onClick={() => setMode('return_pct')}>收益率 %</button>
        </div>
      </div>
      <div className="po-chart">
        {chart.bars.length === 0 ? <Empty>暂无收益记录</Empty> : <svg viewBox="0 0 850 170" role="img" aria-label={`累计${percent ? '收益率' : '盈亏'}`}>
          <line x1={0} x2={780} y1={chart.baseline} y2={chart.baseline} stroke="var(--label3)" opacity={0.3} />
          {chart.bars.map(bar => bar.value === null
            ? <line key={bar.day} x1={bar.x} x2={bar.x + bar.width} y1={160} y2={160} stroke="var(--warn)" strokeWidth={2}><title>{bar.day} · 暂无估值</title></line>
            : <rect key={bar.day} x={bar.x} y={bar.y!} width={bar.width} height={bar.height!} rx={2} fill={bar.value >= 0 ? 'var(--ok)' : 'var(--stale)'}><title>{bar.day} · {format(bar.value)}</title></rect>)}
          <text x={792} y={18} fill="var(--label2)" fontSize={10}>{percent ? `${chart.high.toFixed(2)}%` : `${(chart.high / 1000).toFixed(1)}k`}</text>
          <text x={792} y={151} fill="var(--label2)" fontSize={10}>{percent ? `${chart.low.toFixed(2)}%` : `${(chart.low / 1000).toFixed(1)}k`}</text>
        </svg>}
        {first && last && <div className="po-chart-dates num"><span>{first.day}</span><span>{last.day}</span></div>}
      </div>
    </section> : <Card><Empty>暂无估值</Empty></Card>}

    <section className="po-panel po-strategies" aria-label="策略收益">
      <div className="po-table-head"><h2>策略 <span>{rows.length}</span></h2></div>
      <div className="po-table-scroll">
        <table className="po-rows num">
          <thead><tr><th>策略</th><th>投入本金</th><th>盈亏</th><th>收益率</th></tr></thead>
          <tbody>
            {rows.map(row => {
              const href = row.href || `/paper/ledger/${encodeURIComponent(row.id)}`
              const inspectorId = row.id.startsWith('legacy/') ? row.id.slice('legacy/'.length) : null
              return <tr key={row.id} data-strategy={row.id}>
                <td><div className="po-strategy-name"><a href={href}>{row.label}<span className="po-row-status" data-tone={row.status_tone}>{row.status_label}</span></a>{inspectorId && inspectorIds.includes(inspectorId) && <a className="po-inspector-link" href={`#/paper/${encodeURIComponent(inspectorId)}`}>运行</a>}</div></td>
                <td><a href={href}>{row.capital_usd === null ? '—' : fmtMoney(row.capital_usd, 0)}</a></td>
                <td className={tone(row.pnl_usd)}><a href={href}>{money(row.pnl_usd)}</a></td>
                <td className={tone(row.return_pct)}><a href={href}>{row.return_pct === null ? '—' : fmtPct(row.return_pct, 2)}</a></td>
              </tr>
            })}
            {rows.length === 0 && <tr><td colSpan={4} className="po-no-results">无匹配策略</td></tr>}
            {!search && s && <>
              <tr className="po-adjustment"><td><a href="/paper/accounts">其他收支</a></td><td>—</td><td className={tone(s.adjustment_usd)}>{money(s.adjustment_usd)}</td><td>—</td></tr>
              {s.unassigned_capital_usd !== 0 && <tr className="po-adjustment"><td><a href="/paper/accounts">未分配本金</a></td><td>{fmtMoney(s.unassigned_capital_usd, 0)}</td><td>—</td><td>—</td></tr>}
            </>}
          </tbody>
        </table>
      </div>
    </section>
  </>
}
