
Claude Code can drive a quant backtester via Vibe-Trading MCP - DEV Community
Skip to content
                Powered by Algolia
              Log in
            Create account
DEV Community
        Add reaction
      Like
      Unicorn
      Exploding Head
      Raised Hands
      Fire
      Jump to Comments
      Save
      Boost
Pick as gem
Copy link
Copied to Clipboard
              Share to X
              Share to LinkedIn
              Share to Facebook
              Share to Mastodon
Share Post via...
Report Abuse
Creeta
Posted on 
Aug 2
•
Originally published at 
news.creeta.com
                Claude Code can drive a quant backtester via Vibe-Trading MCP
#
vibetrading
#
quant
#
backtesting
#
opensource
Type one sentence — "Backtest a BTC-USDT 20/50 MA strategy for 2024" — and get back a full quantitative report, equity curve included. That is the pitch behind Vibe-Trading, and unlike most one-command demos, the plumbing underneath is real.
  What HKUDS built: a quant desk you can describe in plain English
Vibe-Trading is an MIT-licensed, self-hosted trading agent from HKUDS — the University of Hong Kong's Data Intelligence Lab, the same team behind LightRAG — that turns a plain-language instruction into runnable quant research: a backtest, ~15 metrics, an equity curve, validation artifacts, and an exportable report . Natural language is the interface, not a modeling claim: generated Python still runs locally, and data loaders keep their usual coverage limits. The project accumulated roughly 29,000 GitHub stars within months of release — fast-moving, so treat that figure as directional.
The scope is what stands out. Under the hood sit multi-agent "swarm" teams — a screener, factor researcher, backtester, and risk auditor chained as a DAG — drawing on about 88 bundled finance skills . Coverage spans multiple markets and data feeds, most needing no API key:
Dimension
What ships
Backtest engines
9 — US equities, China A-shares, Hong Kong, crypto, commodities, forex, options, India NSE/BSE, Korea KRX
Data sources
24 — yfinance, Tushare, AKShare, OKX, CCXT, Finnhub, Alpha Vantage and more, auto-selected per market
API keys
Most tools need zero; only the LLM swarm needs one provider key
Read it as an engineering consolidation of the agentic-quant wave — natural-language-first, MCP-native, broadly multi-market — rather than a new modeling approach . A Korean-language 
explainer video
 seeded the coverage, but the substance lives in the 
repository
.
  Dependency and bring-up checklist
Before you install anything, confirm four things: a Python runtime, one LLM provider key, an MCP-capable client, and — only if you plan to go past backtesting — broker credentials. Vibe-Trading requires 
Python 3.11+
, and the 0.1.x line moves fast, so pin the exact version you test against rather than tracking the tip.
LLM provider key (one):
 the swarm needs a single provider — OpenAI, Anthropic Claude, Google Gemini, DeepSeek, Kimi/Moonshot, Zhipu GLM, SiliconFlow, iFlytek Spark, or a local Ollama/vLLM endpoint via an OpenAI-compatible adapter. The majority of the ~88 bundled finance skills run with zero API keys; only the swarm requires the provider key.
MCP client:
 Claude Code, Codex CLI, or any MCP-compatible client to drive the stdio server. Docker Compose is optional but brings the full frontend up on 
localhost:8899
.
Broker credentials:
 none needed for backtest-only use. The Alpaca and IBKR integrations are off by default and require explicit opt-in.
  How to stand up Vibe-Trading in one shot
Standing up Vibe-Trading is a three-command install followed by a choice of driver: the standalone CLI for a quick smoke test, or an MCP subprocess so Claude Code calls every tool natively. Start with the package: 
pip install vibe-trading-ai
, then 
vibe-trading init
. The 
init
 step writes a default config and auto-discovers the tools available on your machine, so you only wire up what you actually have keys or data for . Python 3.11+ is required, and the 0.1.x line moves fast .
Step 1 — CLI test (no MCP client needed).
 Once initialized, run a full research-to-report loop from one prompt:
vibe-trading run 
-p
"Backtest a BTC-USDT 20/50 MA strategy for 2024"
This is the quickest path to confirm the install works end to end. It exercises the data loader, backtest engine, metrics and report export without a broker or an external client attached .
Step 2 — MCP path.
 To drive it from Claude Code, add Vibe-Trading as a stdio subprocess entry in your MCP config. Claude Code then calls the roughly 88 bundled finance skills as native tool-calls, streaming waiting / running / done / failed state into the chat timeline and rehydrating a finished run card after a UI disconnect . The illustrative Python below (not executed — the 
vibe-trading-mcp
 command ships with the package) shows the raw JSON-RPC handshake Claude Code performs under the hood:
#!/usr/bin/env python3
import
json
import
subprocess
import
sys
def
send
(
proc
,
msg
):
raw
=
json
.
dumps
(
msg
).
encode
()
proc
.
stdin
.
write
(
b
"
Content-Length: %d
\r\n\r\n
"
%
len
(
raw
)
+
raw
)
proc
.
stdin
.
flush
()
def
recv
(
proc
):
headers
=
{}
while
True
:
line
=
proc
.
stdout
.
readline
()
if
line
in
(
b
"
\r\n
"
,
b
"
\n
"
,
b
""
):
break
k
,
v
=
line
.
decode
().
split
(
"
:
"
,
1
)
headers
[
k
.
lower
()]
=
v
.
strip
()
body
=
proc
.
stdout
.
read
(
int
(
headers
[
"
content-length
"
]))
return
json
.
loads
(
body
)
run_dir
=
"
vt_mcp_demo_run
"
# Claude Code would create config/code here first.
print
(
"
Claude Code -> Vibe-Trading MCP -> backtest(run_dir=%r)
"
%
run_dir
)
try
:
p
=
subprocess
.
Popen
(
[
"
vibe-trading-mcp
"
],
stdin
=
subprocess
.
PIPE
,
stdout
=
subprocess
.
PIPE
,
stderr
=
subprocess
.
PIPE
,
)
except
FileNotFoundError
:
print
(
"
vibe-trading-mcp not found; install with: pip install vibe-trading-ai
"
)
sys
.
exit
(
1
)
send
(
p
,
{
"
jsonrpc
"
:
"
2.0
"
,
"
id
"
:
1
,
"
method
"
:
"
initialize
"
,
"
params
"
:
{
"
protocolVersion
"
:
"
2025-03-26
"
,
"
capabilities
"
:
{},
"
clientInfo
"
:
{
"
name
"
:
"
claude-code-demo
"
,
"
version
"
:
"
0
"
}}})
print
(
"
initialized:
"
,
recv
(
p
).
get
(
"
result
"
,
{}).
get
(
"
serverInfo
"
,
{}).
get
(
"
name
"
))
send
(
p
,
{
"
jsonrpc
"
:
"
2.0
"
,
"
method
"
:
"
notifications/initialized
"
,
"
params
"
:
{}})
send
(
p
,
{
"
jsonrpc
"
:
"
2.0
"
,
"
id
"
:
2
,
"
method
"
:
"
tools/call
"
,
"
params
"
:
{
"
name
"
:
"
backtest
"
,
"
arguments
"
:
{
"
run_dir
"
:
run_dir
}}})
print
(
json
.
dumps
(
recv
(
p
),
indent
=
2
)[:
1200
])
p
.
terminate
()
Docker Compose alternative.
 Prefer the web UI? 
docker compose up
 brings the backend and frontend online at 
localhost:8899
 with SSE streaming . From there, roughly 30 bundled swarm presets are ready to run — for example, 
quant_strategy_desk
 chains screener → factor researcher → backtester → risk auditor as a DAG, so one instruction fans out across a coordinated expert team rather than a single agent .
  Where Vibe-Trading can mislead you
Convenience hides three failure modes worth naming before you trust any output. First, natural language is the interface, not a correctness guarantee. The docs warn that 
a weak model may fabricate answers from training data instead of calling tools
  — so model capability decides whether the roughly 88 bundled finance tools are invoked at all . A confident paragraph that never ran the backtester looks identical to one that did.
Second, treat headline numbers as illustrative. Demo figures such as "12.3% annualized, Sharpe 1.4" are examples, not independently evaluated results , and no peer-reviewed head-to-head yet pits Vibe-Trading against 
TradingAgents
 or 
FinRL-Meta
. Open questions remain around survivorship bias, generated-code reliability, and whether any LLM-agent framework produces durable out-of-sample alpha after transaction costs .
Third, the safety story is credible but self-reported. Generated strategy code runs in an AST-hardened sandbox that blocks network access, subprocess calls, 
eval()
, and 
os.environ
 reads , yet prompt-injection resilience under real user data has not been checked by independent auditors. The team completed its own security audit on 2026-07-10, and the live-trading guardrails — mandate gates, a filesystem kill-switch, and a full audit ledger — carry only that internal review . As the maintainers put it, keys are withheld from generated code by default and consequential broker writes "require human approval," with reads auto-approved — Vibe-Trading team, HKUDS (source: 
GitHub
). One more operational note: a phishing Discord running a wallet "verification" scam impersonates the project and is not theirs  — flag it to your team.
  A few quant explorations to kick off
Once the desk is running, treat it as a research sandbox rather than a signal generator, and pick experiments that stress the parts the demo numbers ignore. Vibe-Trading ships walk-forward, Monte Carlo and bootstrap validation, 9 backtest engines across markets including US equities and Korean KRX, ~15 metrics, and an Alpha Zoo of pre-built factors  — enough to interrogate a strategy properly before any capital is involved.
Walk-forward a multi-factor screener
 across the US or KRX universe. Out-of-sample consistency is exactly what illustrative figures like the README's "12.3% annualized, Sharpe 1.4" never establish .
Monte Carlo a crypto momentum strategy
 using OKX or CCXT data at 1m–1D bar granularity, then read the outcome against the ~15 built-in metrics rather than a single return number .
Compare Alpha Zoo factor families
 — run Qlib, Kakushadze-101 and GTJA-191 signals over one backtest window to see which survive after transaction costs .
Try Shadow Account mode
: point it at a real trade history and let the agent extract mandate rules automatically — a low-risk way to audit your own behavioral patterns before wiring any live broker .
The takeaway: use the natural-language loop to run experiments you would otherwise skip, but validate every result yourself — no peer-reviewed benchmark yet confirms durable out-of-sample alpha from any LLM-agent quant framework .
  Frequently asked questions
  Does Vibe-Trading require a paid data subscription?
No. Most of the 24 bundled data sources — including yfinance, AKShare, CCXT, OKX and the Finnhub free tier — work with zero API keys, and Vibe-Trading auto-selects the best free source per market . Tushare needs a free registration token, and an optional premium QVeris gateway exists if you want higher-fidelity data, but neither is required to run backtests . Only the LLM swarm needs a provider key.
  Which LLM gives the most reliable results when calling the finance tools?
Frontier models are safest. Because Vibe-Trading ships roughly 88 finance skills and is tool-heavy, the docs warn that a weak model may fabricate answers from training data instead of calling the tools, so model capability directly affects reliability . Capable providers such as Anthropic Claude, OpenAI GPT-4o and Google Gemini are the most dependable choices. Local Ollama or vLLM runs through an OpenAI-compatible adapter, but reliability drops with smaller parameter counts .
  Is it safe to connect Vibe-Trading to a live broker?
Treat it cautiously and keep it read-only where possible. The IBKR path is read-only with no order-placement tool registered, and Alpaca's TAP mode is off by default, keeps raw broker keys out of the agent process, and requires human approval for consequential writes such as orders and cancels . Live trading is mandate-gated by symbol universe, position size, exposure, leverage and daily caps, with a filesystem kill-switch and audit ledger. The team reported a completed security audit on 2026-07-10, but framing remains research and simulation first.
  Can Vibe-Trading run without any MCP client — just the CLI?
Yes. Running 
vibe-trading run -p "your prompt"
 is a fully standalone path that needs no MCP client . The MCP server is only one of several interfaces: the project also exposes a CLI, a FastAPI web UI on localhost:8899, scheduled jobs, SSE streams and IM/channel adapters . MCP matters when you want an existing assistant like Claude Code or Codex CLI to drive it as a stdio subprocess.
  How does Vibe-Trading differ from FinGPT or FinRL?
They solve different problems. FinGPT (
arXiv:2306.06031
) fine-tunes financial LLMs with LoRA/QLoRA for classification and sentiment, and is weak at numerical reasoning, while FinRL-Meta (
arXiv:2304.13174
) builds gym-style RL environments for reinforcement-learning strategies. Vibe-Trading instead consumes frontier LLMs as interchangeable providers, exposes a tool-calling and MCP surface, and targets the "describe a strategy → get a backtested report" loop rather than model training or environment engineering . It is a deployment and orchestration consolidation, not a modeling breakthrough.
          Top comments 
(0)
Subscribe
Personal
Trusted User
        Create template
Templates let you quickly answer FAQs or store snippets for re-use.
Submit
Preview
Dismiss
        Are you sure you want to hide this comment? It will become hidden in your post, but will still be visible via the comment's 
permalink
.
Hide child comments as well
          Confirm
For further actions, you may consider blocking this person and/or 
reporting abuse
      Creeta
Follow
          Joined
Jun 17, 2026
            More from 
Creeta
              OpenMontage has 45k stars and no proprietary orchestrator
#
opensource
#
agenticvideo
#
claudecode
#
cursor
              Agent-Reach absorbed Bilibili's 412s — your agent kept working
#
agentreach
#
claudecode
#
opensource
#
developertools
              Strix solved 100 of 104 real-world exploits — at $3.37 each
#
strix
#
pentesting
#
appsec
#
opensource
          We're a place where coders share, stay up-to-date and grow their careers.
        Log in
        Create account

