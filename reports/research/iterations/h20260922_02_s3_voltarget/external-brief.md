# External brief: h20260922_02_s3_voltarget

Giants first. Moreira and Muir (NBER w22208, Journal of Finance 2017) showed that scaling
exposure down when trailing realized volatility is high raises Sharpe ratios across equity
factors and carry, because volatility moves without a matching move in expected return. Man
Group's cross-asset study reaches the same conclusion for risk assets with daily data from
1926. Quantpedia has published the closest analogue on our exact instrument class: a
volatility filter that cuts leveraged-ETF exposure in high-volatility periods to keep the
leverage while mitigating the worst drawdowns.

The negative evidence is just as strong and is the reason this round is gated. Cederburg,
O'Doherty, Wang and Yan (JFE 2020) find that across 103 equity strategies volatility-managed
portfolios do not systematically beat their unmanaged counterparts for a real-time investor.
Barroso and Detzel (JFE 2021) find the overlay dies after transaction costs for every factor
except the market. A 2025 Journal of Empirical Finance study covering 45 markets agrees. A
March 2026 arXiv preprint documents the mechanical failure mode of open-loop inverse-variance
scaling: turnover explosion and leverage spikes.

What that literature does not answer is the only question we care about: on our own frozen
sleeve (A4 levered ETF menu, 63-day or blended momentum, top two, month end, absolute momentum
against SHY), on our recent windows, with 10 and 20 bp per side and next-open fills, can a
capped, down-only overlay cut the -56.4% anchor drawdown to -35% or better without dropping
annualized return below 50%. That is what the twelve preregistered cells measure.

Design consequences taken directly from the sources: leverage is capped at 1.0 so the overlay
can only move money into SHY, the overlay updates monthly rather than daily to keep turnover
inside the cost gate, the 20 bp per side view is a pass/fail gate, and the 2026 holdout is
never used for ranking.
