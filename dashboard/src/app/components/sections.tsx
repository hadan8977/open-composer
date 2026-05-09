import { GitCommit, Pause, Layers, ArrowUpRight, Square } from "lucide-react";
import { Card, SectionTitle, Tag, KPI, Pill, ColorBlock } from "./blocks";
import { Hero } from "./hero";
import { Sparkline } from "./sparkline";
import { strategies, events, llmReviews, auditLog } from "./data";

/* ---------------- Versions ---------------- */

const versions = [
  { id: "v12", strat: "Mean Reversion · QQQ", parent: "v11", by: "user", at: "2026-05-08 16:30", status: "active", diff: "+24 / -8", hash: "a8c1…f9" },
  { id: "v11", strat: "Mean Reversion · QQQ", parent: "v10", by: "codex", at: "2026-05-04 11:02", status: "retired", diff: "+5 / -2", hash: "b3d2…11" },
  { id: "v07", strat: "Earnings Drift · S&P 100", parent: "v06", by: "user", at: "2026-05-07 09:55", status: "active", diff: "+91 / -34", hash: "c4e8…aa" },
  { id: "v04", strat: "Macro Regime Switch", parent: "v03", by: "llm", at: "2026-05-09 09:12", status: "approved", diff: "+12 / -1", hash: "d7f0…42" },
  { id: "v02", strat: "News Sentiment Scanner", parent: "v01", by: "llm", at: "2026-05-09 08:00", status: "draft", diff: "+204 / -12", hash: "e1a3…7b" },
];

export function Versions() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="cyan"
        greeting="Version control · immutable"
        headline="Lineage"
        meta="Every edit lives as its own version with parent, hash and replay."
        stat={{ label: "Versions tracked", value: "118", delta: "4 created today" }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Versions tracked" value="118" accent="black" /></div>
        <div className="col-span-3"><KPI label="Active pointers" value="12" accent="green" /></div>
        <div className="col-span-3"><KPI label="Created today" value="4" accent="pink" /></div>
        <div className="col-span-3"><KPI label="LLM-authored" value="38%" accent="orange" /></div>
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="cyan" action={<Pill variant="ghost">Compare two →</Pill>}>
            Recent versions
          </SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Version</th>
              <th className="text-left t-caption ink-subtle">Strategy</th>
              <th className="text-left t-caption ink-subtle">Parent</th>
              <th className="text-left t-caption ink-subtle">Author</th>
              <th className="text-left t-caption ink-subtle">Created</th>
              <th className="text-left t-caption ink-subtle">Diff</th>
              <th className="text-left t-caption ink-subtle">Hash</th>
              <th className="text-left t-caption ink-subtle">Status</th>
              <th className="px-5"></th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id + v.strat} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 flex items-center gap-2">
                  <GitCommit size={14} className="ink-subtle" />
                  <span className="t-mono">{v.id}</span>
                </td>
                <td className="t-title-sm">{v.strat}</td>
                <td className="ink-muted t-mono">{v.parent}</td>
                <td><Tag color={v.by === "llm" ? "purple" : v.by === "codex" ? "cyan" : "paper"}>{v.by}</Tag></td>
                <td className="ink-muted t-num">{v.at}</td>
                <td className="t-mono">{v.diff}</td>
                <td className="t-mono ink-subtle">{v.hash}</td>
                <td><Tag color={v.status === "active" ? "green" : v.status === "approved" ? "cyan" : "paper"}>{v.status}</Tag></td>
                <td className="px-5 text-right whitespace-nowrap">
                  <button className="t-body-sm ink-muted hover:ink mr-3">diff</button>
                  <button className="t-body-sm ink-muted hover:ink">rollback</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ---------------- Paper monitor ---------------- */

const positions = [
  { sym: "QQQ",  qty: 50,  avg: 441.20, mkt: 442.81, upnl: +80.5,  strat: "Mean Reversion · QQQ" },
  { sym: "SPY",  qty: 25,  avg: 522.10, mkt: 523.95, upnl: +46.25, strat: "Earnings Drift · S&P 100" },
  { sym: "VXX",  qty: 30,  avg: 18.41,  mkt: 18.10,  upnl: -9.30,  strat: "Vol Carry · VIX Term" },
  { sym: "KO",   qty:200,  avg: 60.82,  mkt: 61.04,  upnl: +44.0,  strat: "Pairs · KO / PEP" },
  { sym: "PEP",  qty:-180, avg:171.00,  mkt:170.55,  upnl: +81.0,  strat: "Pairs · KO / PEP" },
  { sym: "XLE",  qty: 80,  avg: 88.10,  mkt: 88.40,  upnl: +24.0,  strat: "Sector Rotation" },
];

export function Paper() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting="Paper monitor · 6 running"
        headline="Live"
        meta="Paper_auto strategies, open positions, exposure and slippage in real time."
        stat={{ label: "Day P&L", value: "+$1,562", delta: "Unrealized +$266" }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Auto strategies" value="6" accent="green" /></div>
        <div className="col-span-3"><KPI label="Open positions" value="14" accent="black" /></div>
        <div className="col-span-2"><KPI label="Day P&L" value="+$1,562" accent="cyan" /></div>
        <div className="col-span-2"><KPI label="Unrealized" value="+$266" accent="pink" /></div>
        <div className="col-span-2"><KPI label="Slippage" value="2.1bp" accent="orange" /></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-7" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="green">Running strategies</SectionTitle>
          </div>
          <div className="divider-soft">
            {strategies.filter((s) => s.status === "active").map((s) => (
              <div key={s.id} className="px-5 py-3.5 flex items-center gap-4">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[#16C268] opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#16C268]" />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="t-title-sm truncate">{s.name}</div>
                  <div className="t-body-sm ink-subtle mt-0.5">{s.symbol} · {s.version} · {s.group}</div>
                </div>
                <Sparkline data={s.series} color={s.lastReturn >= 0 ? "#16C268" : "#FF2D7A"} width={140} height={28} />
                <div className="text-right t-num">
                  <div className="t-title-sm" style={{ color: s.lastReturn >= 0 ? "#0A6E3B" : "#C81E5C" }}>
                    {s.lastReturn >= 0 ? "+" : ""}{s.lastReturn}%
                  </div>
                  <div className="t-body-sm ink-subtle">{s.trades} trades</div>
                </div>
                <div className="flex items-center gap-1">
                  <button className="p-2 hover:bg-[var(--paper-3)] transition-colors" style={{ borderRadius: "var(--r-sm)" }}><Pause size={14} /></button>
                  <button className="p-2 hover:bg-[var(--paper-3)] transition-colors" style={{ borderRadius: "var(--r-sm)" }}><Square size={12} /></button>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-5" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="ink">Open positions</SectionTitle>
          </div>
          <table className="w-full t-body-sm">
            <thead>
              <tr className="hairline-b">
                <th className="text-left px-5 py-2.5 t-caption ink-subtle">Sym</th>
                <th className="text-right t-caption ink-subtle">Qty</th>
                <th className="text-right t-caption ink-subtle">Avg</th>
                <th className="text-right t-caption ink-subtle">Mkt</th>
                <th className="text-right pr-5 t-caption ink-subtle">uPnL</th>
              </tr>
            </thead>
            <tbody className="t-num">
              {positions.map((p) => (
                <tr key={p.sym} className="hairline-b last:border-b-0">
                  <td className="px-5 py-3 t-title-sm">{p.sym}</td>
                  <td className="text-right">{p.qty}</td>
                  <td className="text-right">{p.avg.toFixed(2)}</td>
                  <td className="text-right">{p.mkt.toFixed(2)}</td>
                  <td className="text-right pr-5" style={{ color: p.upnl >= 0 ? "#0A6E3B" : "#C81E5C" }}>
                    {p.upnl >= 0 ? "+" : ""}{p.upnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

/* ---------------- Events / News / Macro ---------------- */

export function Events() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="orange"
        greeting="Events · macro · news"
        headline="Signal"
        meta="Raw event stream, derived factors and which strategies they touch."
        stat={{ label: "Events today", value: "48", delta: "5 high-impact" }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-4"><KPI label="Events today" value="48" accent="cyan" /></div>
        <div className="col-span-4"><KPI label="Linked to strategies" value="12" accent="green" /></div>
        <div className="col-span-4"><KPI label="High-impact" value="5" accent="pink" /></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-8" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="orange">Event stream</SectionTitle>
          </div>
          <ul className="divider-soft">
            {[...events, ...events].map((e, i) => (
              <li key={i} className="px-5 py-3 flex items-start gap-3">
                <span className="t-body-sm ink-subtle t-num w-12">{e.t}</span>
                <Tag color={e.kind === "Earnings" ? "pink" : e.kind === "Macro" ? "orange" : e.kind === "News" ? "cyan" : "paper"}>{e.kind}</Tag>
                <span className="t-body-sm flex-1">{e.title}</span>
                <span className="t-caption" style={{
                  color: e.impact === "high" ? "#C81E5C" : e.impact === "med" ? "#B8761B" : "#A09E97",
                }}>{e.impact}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="col-span-4" pad={false}>
          <div className="px-5 py-4 hairline-b">
            <SectionTitle tick="cyan">Factors derived</SectionTitle>
          </div>
          <div className="p-3 space-y-2">
            {[
              ["earnings_surprise_z", "+2.1σ", "green"],
              ["macro_regime", "risk-off", "pink"],
              ["news_sentiment_24h", "+0.18", "cyan"],
              ["vol_term_slope", "contango", "orange"],
              ["sector_breadth", "0.62", "paper"],
            ].map(([k, v, c]) => (
              <div key={k as string} className="flex items-center justify-between px-3.5 py-2.5"
                style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                <span className="t-mono">{k}</span>
                <Tag pill color={c as any}>{v}</Tag>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ---------------- LLM center ---------------- */

export function LLM() {
  const cols = [
    { title: "Review", subtitle: "LLM acts as final reviewer", color: "green" as const, items: llmReviews.slice(0, 2) },
    { title: "Scan", subtitle: "Events → structured features", color: "cyan" as const, items: llmReviews.slice(0, 3) },
    { title: "Orchestrator", subtitle: "Selects which group runs", color: "purple" as const, items: llmReviews.slice(1, 3) },
  ];
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="purple"
        greeting="LLM workspace · 3 lanes"
        headline="Reasoning"
        meta="Review, scan and orchestrator outputs — every card is structured & replayable."
        stat={{ label: "Pending review", value: "3", delta: "22 submissions / 7d" }}
      />
      <div className="grid grid-cols-3 gap-3">
        {cols.map((c) => (
          <Card key={c.title} pad={false}>
            <ColorBlock color={c.color} rounded="sm" halftone className="m-3 px-5 py-4 relative overflow-hidden">
              <div className="t-display-md" style={{ position: "relative", zIndex: 1 }}>{c.title}</div>
              <div className="t-body-sm mt-0.5" style={{ opacity: 0.85, position: "relative", zIndex: 1 }}>{c.subtitle}</div>
            </ColorBlock>
            <div className="px-3 pb-3 space-y-2">
              {c.items.map((r) => (
                <div key={r.id} className="p-3.5" style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                  <div className="flex items-center justify-between mb-1">
                    <Tag pill color={r.color}>{r.verdict}</Tag>
                    <span className="t-mono ink-subtle">{r.id}</span>
                  </div>
                  <div className="t-title-sm">{r.strat}</div>
                  <div className="t-body-sm ink-muted mt-1 leading-snug">{r.summary}</div>
                  <div className="flex items-center gap-2 mt-3">
                    <Pill variant="primary">Open card</Pill>
                    <Pill variant="secondary">Replay</Pill>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="purple">Prompt / model lineage</SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Session</th>
              <th className="text-left t-caption ink-subtle">Model</th>
              <th className="text-left t-caption ink-subtle">Template</th>
              <th className="text-left t-caption ink-subtle">Strategy version</th>
              <th className="text-left t-caption ink-subtle">Output</th>
              <th className="text-right pr-5 t-caption ink-subtle">Tokens</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["sess-7afb", "claude-opus-4-7", "review.v3", "Vol Carry · VIX Term v09", "approved", 4120],
              ["sess-7af2", "claude-sonnet-4-6", "scan.v2", "News Sentiment Scanner v02", "features.json", 8810],
              ["sess-7adb", "claude-opus-4-7", "orchestrator.v1", "Macro Regime Switch v04", "needs-changes", 6204],
              ["sess-7ac9", "claude-sonnet-4-6", "review.v3", "Earnings Drift · S&P 100 v07", "approved-w-caveats", 3620],
            ].map((row) => (
              <tr key={row[0] as string} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 t-mono">{row[0]}</td>
                <td className="t-mono">{row[1]}</td>
                <td className="t-mono">{row[2]}</td>
                <td className="t-title-sm">{row[3]}</td>
                <td><Tag color="paper">{row[4]}</Tag></td>
                <td className="text-right t-num pr-5">{(row[5] as number).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ---------------- Strategy Groups ---------------- */

export function Groups() {
  const groups = [
    { name: "Core Satellite", weight: 32, color: "green"  as const, risk: "stable",   children: ["Mean Reversion · QQQ", "Pairs · KO / PEP"] },
    { name: "Event-driven",   weight: 22, color: "pink"   as const, risk: "moderate", children: ["Earnings Drift · S&P 100"] },
    { name: "Vol",            weight: 16, color: "cyan"   as const, risk: "high",     children: ["Vol Carry · VIX Term"] },
    { name: "Rotation",       weight: 10, color: "black"  as const, risk: "moderate", children: ["Sector Rotation"] },
    { name: "Regime",         weight:  5, color: "purple" as const, risk: "high",     children: ["Macro Regime Switch"] },
    { name: "LLM Scan",       weight:  3, color: "orange" as const, risk: "high",     children: ["News Sentiment Scanner"] },
  ];
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="pink"
        greeting="Strategy groups · 6 active"
        headline="Compose"
        meta="First-class orchestrator objects — capital, frequency and regime are all here."
        stat={{ label: "Capital allocated", value: "97%", delta: "3% cash" }}
      />
      <div className="grid grid-cols-3 gap-3">
      {groups.map((g) => (
        <Card key={g.name} pad={false}>
          <ColorBlock color={g.color} rounded="sm" halftone className="m-3 px-5 py-5 relative overflow-hidden">
            <div className="t-caption" style={{ opacity: 0.78, position: "relative", zIndex: 1 }}>Strategy group</div>
            <div className="t-display-md mt-1" style={{ position: "relative", zIndex: 1 }}>{g.name}</div>
            <div className="mt-5 flex items-baseline gap-3" style={{ position: "relative", zIndex: 1 }}>
              <div className="t-display-xl t-num">{g.weight}%</div>
              <div className="t-body-sm" style={{ opacity: 0.82 }}>capital allocation</div>
            </div>
          </ColorBlock>
          <div className="px-4 pb-4 space-y-2">
            <div className="flex items-center justify-between t-body-sm ink-muted">
              <span>Children · <span className="ink t-num">{g.children.length}</span></span>
              <Tag pill color={g.risk === "stable" ? "green" : g.risk === "moderate" ? "orange" : "pink"}>{g.risk}</Tag>
            </div>
            {g.children.map((c) => (
              <div key={c} className="flex items-center gap-2 px-3.5 py-2.5"
                style={{ background: "var(--paper-3)", borderRadius: "var(--r-md)" }}>
                <Layers size={13} className="ink-subtle" />
                <span className="t-body-md flex-1 truncate">{c}</span>
                <ArrowUpRight size={13} className="ink-subtle" />
              </div>
            ))}
            <button
              className="w-full mt-1 t-body-sm ink-muted py-2.5 hover:bg-[var(--paper-3)]"
              style={{ borderRadius: "var(--r-md)", border: "1px dashed rgba(10,10,10,.18)" }}
            >
              + add child strategy
            </button>
          </div>
        </Card>
      ))}
      </div>
    </div>
  );
}

/* ---------------- Audit ---------------- */

export function Audit() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="ink"
        greeting="Activity ledger · last 7 days"
        headline="Audit"
        meta="Every write goes through CLI safety gates — full replayable trail."
        stat={{ label: "Events 7d", value: "284", delta: "3 blocked by rules" }}
      />
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3"><KPI label="Audit events 7d" value="284" accent="black" /></div>
        <div className="col-span-3"><KPI label="Approvals" value="14" accent="green" /></div>
        <div className="col-span-3"><KPI label="Blocked by rules" value="3" accent="pink" /></div>
        <div className="col-span-3"><KPI label="LLM submissions" value="22" accent="cyan" /></div>
      </div>
      <Card pad={false}>
        <div className="px-5 py-4 hairline-b">
          <SectionTitle tick="ink">Activity log</SectionTitle>
        </div>
        <table className="w-full t-body-sm">
          <thead>
            <tr className="hairline-b" style={{ background: "var(--paper-4)" }}>
              <th className="text-left px-5 py-3 t-caption ink-subtle">Time</th>
              <th className="text-left t-caption ink-subtle">Actor</th>
              <th className="text-left t-caption ink-subtle">Action</th>
              <th className="text-left t-caption ink-subtle">Target</th>
              <th className="text-right pr-5 t-caption ink-subtle">Replay</th>
            </tr>
          </thead>
          <tbody>
            {[...auditLog, ...auditLog].map((a, i) => (
              <tr key={i} className="hairline-b last:border-b-0">
                <td className="px-5 py-3 t-num ink-muted">{a.t}</td>
                <td><Tag color={a.who === "user" ? "paper" : a.who === "codex" ? "cyan" : a.who === "llm" ? "purple" : "orange"}>{a.who}</Tag></td>
                <td>{a.action}</td>
                <td className="t-title-sm">{a.target}</td>
                <td className="pr-5 text-right">
                  <button className="t-body-sm ink-muted hover:ink">view →</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
