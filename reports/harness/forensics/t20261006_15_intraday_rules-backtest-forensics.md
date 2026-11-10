# Backtest Forensics: T-20261006-15 C

The causal feature rebuild uses only prior sessions, resets at a visible price break, filters cross-month duplicate rows, and preserves cash for unused slots. The full-window sanitizer is retained as an audit and does not decide earlier eligibility. The implementation therefore passes the lookahead and future-leak checks.

The registered family contains 162 variants, with 18 main-grid points and selection by a frozen second-of-top-three rule. Multiple-testing risk is high. The selected points have DSR 0 and fail the frozen P1 gate. The recent window has 689 sessions, so the sample is not short, but the result is strongly negative after costs. Stop detection is based on 5-minute OHLC bars; historical NBBO and complete corporate-action reconciliation remain limitations.

The current conclusion is blocked for promotion: gross edge is smaller than modeled entry/exit spread plus fees, recent Alpha versus SPY is negative, and the direction IC decays toward zero as the pool expands. The appropriate next action is to close this branch and preserve the evidence, not tune parameters after seeing the result.
