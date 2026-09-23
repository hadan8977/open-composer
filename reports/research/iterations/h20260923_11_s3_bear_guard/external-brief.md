# External brief: h20260923_11_s3_bear_guard

Giants first, on the new question. Gayed and Bilello (2016, SSRN 2741701, "Leverage for the
Long Run") establish that volatility is the enemy of leverage and that streaks in performance
favor margin use; they show that employing leverage while the broad U.S. equity market is above
its Moving Average and deleveraging to Treasury bills when it is below beats both a comparable
unleveraged buy-and-hold and a constant-leverage strategy, robust across leverage amounts,
Moving Average windows and multiple market cycles. That is the published mechanism BG01
(QQQ<SMA200) and BG02 (SMH<SMA200) instantiate directly, and BG04 (the unscaled S3 book's own
equity curve<SMA200) applies to the book itself rather than an external index. Faber
(2007/2013, SSRN 962461, "A Quantitative Approach to Tactical Asset Allocation") is the second,
independent giant behind the same mechanism class: a simple moving-average timing system,
applied across several unlevered asset classes, continued to deliver equity-like returns with
bond-like volatility and drawdowns in the 2008-2012 real-time update. Together these ground
moving-average regime gating as a broadly replicated mechanism, not a single-paper artifact.

Locally, the overlay this round reuses unchanged is the same S3 vt40+boost machine already
authorized in the live renewal (H-20260923-09 / commit 97c992c): 63-session absolute momentum
vs SHY, 21-session realized-volatility target 0.40 with a QQQ-oversold dip boost to 0.60, 1.0
leverage cap, monthly rebalance. Its own giants (Moreira and Muir 2017; Man Group 2017) and
negative evidence (Cederburg et al. 2020; Barroso and Detzel 2021; the 2025 international
replication; the 2026 closed-loop preprint) were verified in H-20260922-02 and are reused here,
because the overlay's own parameters are not being changed or re-tested -- only a bear-regime
gate is being added on top of it.

What is new here is the gate itself, and the evidence for reopening this family. The prior
drawdown-brake experiment (H-20260922-02) refuted an equity-curve drawdown brake because it lost
to its own calendar-shift placebo in 70% of seeds, and its own reopen_if condition was explicit:
"a drawdown signal validated with an exposure-matched control." This round implements exactly
that control (EM-k, a single bisected volatility-target scale factor matching each gate's mean
exposure) and, because the earlier calendar-shift placebo (a 1-20 session shift) is adequate
only for a fast, reactive signal and not for a slow 100/200-session trend gate that barely
changes state over 1-20 sessions, upgrades the placebo to a within-design-window circular shift
(CS-k, 20 offsets per gate) that preserves each gate's on/off duration and time-in-market while
breaking its alignment with actual market states. Gehrman's live, real-money r/LETFs track
record (Sep 2026 update, running since March 2024) is the independent post-publication record
required for this direction: it applies the identical Gayed-and-Bilello 200-day-SMA rule to a
2x S&P 500 ETF (SSO) today, confirming the rule is a real position someone holds, not only a
backtest curiosity -- though a single currently-on observation cannot show what the rule would
have done through the 2018 or 2022 drawdowns the design window exists to test.

What none of this literature answers is the only question this round is designed to settle: on
our own frozen S3 overlay machine, on the pre-select-window 2016-01-04..2023-09-15 design
window, at 10 and 20 bp, does moving all of S3's risk weight to SHY on any of four gate signals
(QQQ, SMH, a credit ratio, or the book's own equity curve, each below its own moving average)
cut the drawdown by more than an exposure-matched lower volatility target would, beat a
circular-shift placebo, and still clear the frozen anchor-window return bar -- without ever
claiming the already-spent 2026 holdout as new evidence. That is what BG01-BG04 measure, each
independently against BG00, with no ranking or selection among them.
