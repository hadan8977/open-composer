# R5 Execution Reality

## Verdict

Execution and paper simulation are blocked. The best candidate's average gross return is 3.21 bps per traded day, below the lowest 10 bps modeled round trip. Raising one-way costs from 5 to 10 and 20 bps worsens D07 from -10.94% to -23.97% and -44.62% total return.

## Fill Boundary

The first-hour signal completes at 10:30 ET and the historical fill is the 10:30 next-bar open. A live process receives, computes, and routes after that boundary, so it cannot assume the exact historical opening print. Before any paper order, replay the first tradable quote after signal delivery and compare immediate marketable limits, an 11:00 delayed limit, and a five-minute TWAP.

## TCA

Record decision, submission, acceptance, first fill, all fills, arrival bid/ask, participation, 15:30 reference, and official close. Review fill rate, implementation shortfall, effective and realized spread, adverse movement, and signal decay weekly. Alpaca paper results can validate lifecycle plumbing only, not live execution quality.
