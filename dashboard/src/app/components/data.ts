export type RiskLevel = "stable" | "moderate" | "high";
export type ModelClass =
  | "pure-quant"
  | "quant-review"
  | "quant-scan"
  | "quant-orchestrator";

export interface Strategy {
  id: string;
  name: string;
  symbol: string;
  version: string;
  status: "active" | "approved" | "draft" | "retired";
  modelClass: ModelClass;
  risk: RiskLevel;
  group: string;
  pine: boolean;
  python: boolean;
  alpaca: boolean;
  lastReturn: number;
  sharpe: number;
  trades: number;
  series: number[];
}

const series = (n = 24, start = 100, vol = 4) => {
  const out: number[] = [];
  let v = start;
  for (let i = 0; i < n; i++) {
    v += (Math.random() - 0.45) * vol;
    out.push(v);
  }
  return out;
};

export const strategies: Strategy[] = [
  {
    id: "s-001",
    name: "Mean Reversion · QQQ",
    symbol: "QQQ",
    version: "v12",
    status: "active",
    modelClass: "pure-quant",
    risk: "stable",
    group: "Core Satellite",
    pine: true,
    python: true,
    alpaca: true,
    lastReturn: 8.4,
    sharpe: 1.42,
    trades: 36,
    series: series(28, 100, 3),
  },
  {
    id: "s-002",
    name: "Earnings Drift · S&P 100",
    symbol: "SPX",
    version: "v07",
    status: "active",
    modelClass: "quant-review",
    risk: "moderate",
    group: "Event-driven",
    pine: false,
    python: true,
    alpaca: true,
    lastReturn: 14.1,
    sharpe: 1.81,
    trades: 92,
    series: series(28, 100, 5),
  },
  {
    id: "s-003",
    name: "Macro Regime Switch",
    symbol: "TLT/SPY",
    version: "v04",
    status: "approved",
    modelClass: "quant-orchestrator",
    risk: "high",
    group: "Regime",
    pine: false,
    python: true,
    alpaca: false,
    lastReturn: -2.3,
    sharpe: 0.42,
    trades: 12,
    series: series(28, 100, 6),
  },
  {
    id: "s-004",
    name: "News Sentiment Scanner",
    symbol: "NDX",
    version: "v02",
    status: "draft",
    modelClass: "quant-scan",
    risk: "high",
    group: "LLM Scan",
    pine: false,
    python: true,
    alpaca: false,
    lastReturn: 5.7,
    sharpe: 0.94,
    trades: 18,
    series: series(28, 100, 4.5),
  },
  {
    id: "s-005",
    name: "Pairs · KO / PEP",
    symbol: "KO-PEP",
    version: "v18",
    status: "active",
    modelClass: "pure-quant",
    risk: "stable",
    group: "Stat-Arb",
    pine: true,
    python: true,
    alpaca: true,
    lastReturn: 3.6,
    sharpe: 1.12,
    trades: 54,
    series: series(28, 100, 2.5),
  },
  {
    id: "s-006",
    name: "Vol Carry · VIX Term",
    symbol: "VIX",
    version: "v09",
    status: "active",
    modelClass: "quant-review",
    risk: "high",
    group: "Vol",
    pine: false,
    python: true,
    alpaca: true,
    lastReturn: 22.8,
    sharpe: 1.95,
    trades: 41,
    series: series(28, 100, 7),
  },
  {
    id: "s-007",
    name: "Sector Rotation",
    symbol: "XL*",
    version: "v05",
    status: "approved",
    modelClass: "quant-orchestrator",
    risk: "moderate",
    group: "Rotation",
    pine: false,
    python: true,
    alpaca: false,
    lastReturn: 6.9,
    sharpe: 1.05,
    trades: 22,
    series: series(28, 100, 3.5),
  },
];

export const recentSignals = [
  { t: "09:31:02", strat: "Mean Reversion · QQQ", side: "BUY", px: 442.18, sz: 50, tag: "entry" },
  { t: "09:35:14", strat: "Pairs · KO / PEP", side: "SELL", px: 61.04, sz: 200, tag: "exit" },
  { t: "09:42:55", strat: "Vol Carry · VIX Term", side: "BUY", px: 18.42, sz: 30, tag: "entry" },
  { t: "10:01:10", strat: "Earnings Drift · S&P 100", side: "BUY", px: 211.7, sz: 25, tag: "entry" },
  { t: "10:15:33", strat: "Mean Reversion · QQQ", side: "SELL", px: 443.91, sz: 50, tag: "exit" },
  { t: "10:48:22", strat: "Sector Rotation", side: "BUY", px: 88.4, sz: 80, tag: "entry" },
];

export const events = [
  { t: "08:15", kind: "Earnings", title: "NVDA beats revenue estimates by 9%", impact: "high" },
  { t: "09:00", kind: "Macro", title: "ISM Manufacturing PMI 48.7 (vs 49.1 exp)", impact: "med" },
  { t: "09:48", kind: "News", title: "Fed officials signal patience on rate cuts", impact: "high" },
  { t: "10:22", kind: "Filing", title: "AAPL files 10-Q with FX guidance revised", impact: "low" },
  { t: "11:05", kind: "News", title: "OPEC+ extends voluntary cuts through Q3", impact: "med" },
];

export const llmReviews = [
  {
    id: "r-91",
    strat: "Macro Regime Switch v04",
    verdict: "needs-changes",
    summary: "Drawdown profile inconsistent with declared moderate-risk tier.",
    color: "pink" as const,
  },
  {
    id: "r-92",
    strat: "News Sentiment Scanner v02",
    verdict: "approve-with-caveats",
    summary: "Feature pipeline reproducible; suggest cap on intraday turnover.",
    color: "orange" as const,
  },
  {
    id: "r-93",
    strat: "Vol Carry · VIX Term v09",
    verdict: "approved",
    summary: "Live behavior matches backtest within tolerance bands.",
    color: "green" as const,
  },
];

export const auditLog = [
  { t: "2026-05-09 10:48", who: "user", action: "Activated paper_auto", target: "Sector Rotation v05" },
  { t: "2026-05-09 09:12", who: "codex", action: "Created version", target: "News Sentiment Scanner v02" },
  { t: "2026-05-08 16:30", who: "user", action: "Approved", target: "Vol Carry · VIX Term v09" },
  { t: "2026-05-08 14:11", who: "system", action: "Risk rule blocked", target: "Macro Regime Switch v04" },
  { t: "2026-05-08 09:00", who: "llm", action: "Review submitted", target: "Earnings Drift · S&P 100 v07" },
];
