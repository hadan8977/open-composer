import { useState } from "react";
import {
  GitBranch, Play, Pause, FlaskConical, Eye, ShieldCheck, Sparkles,
  TrendingUp, ArrowRight, Plus,
} from "lucide-react";
import { Card, Tag, Pill, KPI, SectionTitle } from "./blocks";
import { Sparkline } from "./sparkline";
import { strategies } from "./data";

type Tab = "spec" | "backtest" | "signals" | "versions" | "llm" | "audit";

const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: "spec",     label: "Spec",     icon: FlaskConical },
  { key: "backtest", label: "Backtest", icon: TrendingUp },
  { key: "signals",  label: "Signals",  icon: Eye },
  { key: "versions", label: "Versions", icon: GitBranch },
  { key: "llm",      label: "LLM",      icon: Sparkles },
  { key: "audit",    label: "Audit",    icon: ShieldCheck },
];

export function StrategyDetail({ id }: { id: string }) {
  const s = strategies.find((x) => x.id === id) ?? strategies[0];
  const [tab, setTab] = useState<Tab>("spec");
  const positive = s.lastReturn >= 0;
  const accent = positive ? "#16C268" : "#FF2D7A";

  return (
    <div className="px-6 pb-8 space-y-3">
      {/* Detail header — strategy hero */}
      <div
        className="dscard relative overflow-hidden"
        style={{ borderRadius: "var(--r-2xl)", padding: "22px 26px" }}
      >
        {/* composer-style multi-tile color signature in corner */}
        <div
          aria-hidden
          className="absolute blend-multiply tile-halftone"
          style={{ top: 0, right: 0, width: 240, height: 56, background: accent }}
        />
        <div
          aria-hidden
          className="absolute blend-multiply"
          style={{ top: 56, right: 96, width: 56, height: 32, background: "#0A0A0A" }}
        />
        <div
          aria-hidden
          className="absolute blend-multiply"
          style={{ top: 56, right: 152, width: 32, height: 16, background: accent, opacity: 0.55 }}
        />
        <div className="relative flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2 t-caption ink-subtle">
              <span>STRATEGY</span>
              <span>·</span>
              <span className="t-mono">{s.symbol}</span>
              <span>·</span>
              <span className="t-mono">{s.version}</span>
            </div>
            <h1 className="t-display-lg mt-2 grad-ink-green">{s.name}</h1>
            <div className="flex items-center gap-2 mt-3">
              <Tag color={s.status === "active" ? "green" : "paper"}>{s.status}</Tag>
              <Tag color="cyan">{s.modelClass.replace("-", " ")}</Tag>
              <Tag color={s.risk === "stable" ? "green" : s.risk === "moderate" ? "orange" : "pink"}>{s.risk}</Tag>
              <span className="t-body-sm ink-subtle ml-1">in {s.group}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Pill variant="secondary"><Pause size={12} /> Pause</Pill>
            <Pill variant="primary"><Play size={12} fill="white" /> Run backtest</Pill>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-1">
        {TABS.map(({ key, label, icon: Icon }) => {
          const isActive = key === tab;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`pill ${isActive ? "pill-primary" : "pill-ghost"}`}
            >
              <Icon size={13} /> {label}
            </button>
          );
        })}
      </div>

      {tab === "spec" && <SpecCanvas s={s} accent={accent} />}
      {tab === "backtest" && <BacktestPanel s={s} accent={accent} />}
      {tab === "signals" && <SignalsPanel />}
      {tab === "versions" && <VersionsMini />}
      {tab === "llm" && <LLMPanel />}
      {tab === "audit" && <AuditMini />}
    </div>
  );
}

/* ---------------- Spec — halftone workspace canvas ---------------- */

function SpecCanvas({ s, accent }: { s: any; accent: string }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      {/* The canvas itself — halftone background, the "engineering file" */}
      <div className="col-span-8">
        <Card pad={false}>
          <div className="px-5 py-3 hairline-b flex items-center justify-between">
            <SectionTitle hint="StrategySpec · YAML-backed workspace">Editor canvas</SectionTitle>
            <div className="flex items-center gap-1.5">
              <Pill variant="ghost">YAML</Pill>
              <Pill variant="ghost">Visual</Pill>
            </div>
          </div>
          <div
            className="relative halftone bg-paper-3 overflow-hidden"
            style={{ height: 460 }}
          >
            {/* subtle grid hint */}
            <div
              aria-hidden
              className="absolute inset-0 pointer-events-none"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(0,0,0,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,.04) 1px, transparent 1px)",
                backgroundSize: "48px 48px",
                backgroundPosition: "-1px -1px",
              }}
            />

            {/* Node: Universe */}
            <SpecNode
              x={48} y={48} w={220}
              kind="UNIVERSE" title={s.symbol} subtitle="Daily · 1m bars" tone="ink"
            />
            {/* Connector */}
            <Connector x1={158} y1={104} x2={158} y2={150} />

            {/* Node: Filter */}
            <SpecNode
              x={48} y={150} w={220}
              kind="FILTER" title="ATR(14) > 1.0" subtitle="Volatility floor" tone="cyan"
            />
            <Connector x1={158} y1={206} x2={158} y2={252} />

            {/* Node: Entry */}
            <SpecNode
              x={48} y={252} w={220}
              kind="ENTRY" title="RSI(2) < 10 AND close > SMA(200)" subtitle="Mean reversion" tone="green"
            />
            <Connector x1={268} y1={290} x2={420} y2={290} />

            {/* Node: Sizing */}
            <SpecNode
              x={420} y={252} w={220}
              kind="SIZING" title="Risk parity 1.5%" subtitle="Per-trade vol target" tone="orange"
            />
            <Connector x1={530} y1={308} x2={530} y2={360} />

            {/* Node: Exit */}
            <SpecNode
              x={420} y={360} w={220}
              kind="EXIT" title="RSI(2) > 70 OR -1.5% stop" subtitle="3 conditions" tone="pink"
            />

            {/* Drifting "+" placeholder */}
            <button
              className="absolute flex items-center gap-1 px-3 h-8 rounded-full t-body-sm ink-muted bg-white/70 hover:bg-white"
              style={{ left: 700, top: 380, boxShadow: "var(--e1)", border: "1px dashed rgba(10,10,10,.18)" }}
            >
              <Plus size={12} /> add node
            </button>
          </div>
        </Card>
      </div>

      {/* Side panel — stats + spec metadata */}
      <div className="col-span-4 space-y-3">
        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Live metrics</SectionTitle>
          </div>
          <div className="p-3 grid grid-cols-2 gap-2">
            <KPI label="Sharpe" value={String(s.sharpe)} accent="black" />
            <KPI label="30d return" value={`${s.lastReturn > 0 ? "+" : ""}${s.lastReturn}%`} accent={s.lastReturn >= 0 ? "green" : "pink"} />
          </div>
          <div className="px-5 pb-4 pt-1">
            <Sparkline data={s.series} color={accent} width={340} height={64} />
          </div>
        </Card>

        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Compatibility</SectionTitle>
          </div>
          <div className="p-3 space-y-1.5">
            <CompatRow label="Pine export" ok={s.pine} note="full subset" />
            <CompatRow label="Python engine" ok={s.python} note="primary runtime" />
            <CompatRow label="Alpaca paper" ok={s.alpaca} note="paper_auto eligible" />
          </div>
        </Card>

        <Card pad={false}>
          <div className="px-5 py-3 hairline-b">
            <SectionTitle>Provenance</SectionTitle>
          </div>
          <div className="p-4 t-body-sm space-y-1.5">
            <ProvRow k="Created" v="2026-04-12" />
            <ProvRow k="Author" v="user · cellinz" />
            <ProvRow k="Hash" v="a8c1…f9" mono />
            <ProvRow k="Parent" v="v11" mono />
            <ProvRow k="Last run" v="2 min ago" />
          </div>
        </Card>
      </div>
    </div>
  );
}

function SpecNode({
  x, y, w, kind, title, subtitle, tone,
}: {
  x: number; y: number; w: number; kind: string; title: string; subtitle: string;
  tone: "ink" | "green" | "pink" | "cyan" | "orange";
}) {
  const tones: Record<string, { bg: string; bar: string; ink: string }> = {
    ink:    { bg: "#FFFFFF", bar: "#0A0A0A", ink: "#0A0A0A" },
    green:  { bg: "#FFFFFF", bar: "#16C268", ink: "#0A0A0A" },
    pink:   { bg: "#FFFFFF", bar: "#FF2D7A", ink: "#0A0A0A" },
    cyan:   { bg: "#FFFFFF", bar: "#21CFEF", ink: "#0A0A0A" },
    orange: { bg: "#FFFFFF", bar: "#F8A93B", ink: "#0A0A0A" },
  };
  const t = tones[tone];
  return (
    <div
      className="absolute"
      style={{
        left: x, top: y, width: w,
        background: t.bg,
        borderRadius: "var(--r-md)",
        boxShadow: "var(--e2)",
        border: "1px solid rgba(10,10,10,.06)",
        overflow: "hidden",
      }}
    >
      <div className="flex items-center gap-2 px-3 py-1.5" style={{ borderBottom: "1px solid rgba(10,10,10,.06)" }}>
        <span style={{ width: 6, height: 6, background: t.bar, borderRadius: 2, display: "inline-block" }} />
        <span className="t-caption" style={{ color: "#6B6B68" }}>{kind}</span>
      </div>
      <div className="px-3 py-2.5">
        <div className="t-title-sm" style={{ color: t.ink }}>{title}</div>
        <div className="t-body-sm ink-subtle mt-0.5">{subtitle}</div>
      </div>
    </div>
  );
}

function Connector({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const isHorizontal = y1 === y2;
  const left = Math.min(x1, x2) - 4;
  const top = Math.min(y1, y2) - 4;
  const width = isHorizontal ? Math.abs(x2 - x1) + 8 : 8;
  const height = isHorizontal ? 8 : Math.abs(y2 - y1) + 8;
  return (
    <svg
      className="absolute pointer-events-none"
      style={{ left, top, width, height }}
      viewBox={`0 0 ${width} ${height}`}
    >
      {isHorizontal ? (
        <line x1={4} y1={4} x2={width - 4} y2={4} stroke="#0A0A0A" strokeWidth="1.5" strokeDasharray="3 3" />
      ) : (
        <line x1={4} y1={4} x2={4} y2={height - 4} stroke="#0A0A0A" strokeWidth="1.5" strokeDasharray="3 3" />
      )}
      <circle cx={isHorizontal ? width - 4 : 4} cy={isHorizontal ? 4 : height - 4} r="2" fill="#0A0A0A" />
    </svg>
  );
}

function CompatRow({ label, ok, note }: { label: string; ok: boolean; note: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: ok ? "var(--paper-3)" : "transparent" }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: ok ? "#16C268" : "rgba(10,10,10,.18)" }} />
      <span className="t-body-md flex-1">{label}</span>
      <span className="t-body-sm ink-subtle">{note}</span>
    </div>
  );
}

function ProvRow({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="ink-subtle">{k}</span>
      <span className={mono ? "t-mono" : "ink"}>{v}</span>
    </div>
  );
}

/* ---------------- Other tabs (light placeholders) ---------------- */

function BacktestPanel({ s, accent }: { s: any; accent: string }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <Card variant="dark" pad={false} className="col-span-8">
        <div className="px-5 pt-4 pb-3 flex items-end justify-between gap-4">
          <div>
            <div className="t-caption" style={{ color: "rgba(242,242,240,.55)" }}>Equity curve · 5y</div>
            <div className="t-display-xl mt-1.5 t-num">+184.2%</div>
          </div>
          <div className="flex items-center gap-0.5 p-1 rounded-full bg-white/5">
            {["1M", "3M", "1Y", "3Y", "5Y", "All"].map((p, i) => (
              <button
                key={p}
                className={`px-2.5 h-7 inline-flex items-center t-body-sm rounded-full transition-colors ${
                  i === 4 ? "bg-white text-[#0A0A0A]" : "text-white/65 hover:text-white"
                }`}
                style={{ fontWeight: 600 }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="px-5 pb-5">
          <Sparkline
            data={s.series.concat(s.series)}
            color={accent}
            width={760}
            height={240}
            area
            strokeWidth={1.8}
          />
        </div>
        {/* benchmark legend */}
        <div className="px-5 pb-5 flex items-center gap-4 t-body-sm" style={{ color: "rgba(242,242,240,.7)" }}>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: accent, borderRadius: 1 }} /> Strategy
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: "rgba(242,242,240,.45)", borderRadius: 1 }} /> SPY benchmark
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: "#1AC8E8", borderRadius: 1 }} /> Risk-free
          </span>
        </div>
      </Card>
      <Card pad={false} className="col-span-4">
        <div className="px-5 py-3 hairline-b">
          <SectionTitle tick="green">Performance</SectionTitle>
        </div>
        <div className="p-3 grid grid-cols-2 gap-1.5">
          {[
            ["Cumulative", "+184.2%", "green"],
            ["Annualized", "+22.6%",  "green"],
            ["Sharpe",     String(s.sharpe), null],
            ["Max DD",     "−7.4%",   "pink"],
            ["Win rate",   "58.4%",   null],
            ["Trades",     String(s.trades), null],
          ].map(([k, v, accent]) => (
            <div
              key={k as string}
              className="px-3.5 py-2.5"
              style={{ background: "var(--paper-3)", borderRadius: "var(--r-sm)" }}
            >
              <div className="t-caption ink-subtle">{k}</div>
              <div
                className="t-title-md t-num mt-1"
                style={{
                  color: accent === "green" ? "#0A6E3B" : accent === "pink" ? "#C81E5C" : "var(--ink)",
                  fontWeight: 700,
                }}
              >{v}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SignalsPanel() {
  return <Card><div className="t-body-md ink-muted">Signal log table — render last 200 entry/exit events with backtest replay.</div></Card>;
}
function VersionsMini() {
  return <Card><div className="t-body-md ink-muted">Version lineage tree for this strategy — diff & rollback.</div></Card>;
}
function LLMPanel() {
  return <Card><div className="t-body-md ink-muted">Review cards, scan outputs and orchestrator decisions tied to this strategy.</div></Card>;
}
function AuditMini() {
  return <Card><div className="t-body-md ink-muted">Audit events scoped to this strategy — approvals, blocks, paper toggles.</div></Card>;
}
