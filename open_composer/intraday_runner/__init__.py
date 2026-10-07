"""Multi-strategy intraday paper runner for one Alpaca Paper account (quant2).

Plugins (one per strategy) emit target positions from point-in-time bars; the engine keeps a
virtual sub-account per strategy, nets orders across strategies into account-level market
orders, allocates fills back, enforces risk caps, flattens before the close and recovers from
its append-only event log.  Reuses ``open_composer.paper_intraday`` (authorization record,
``_client_order_id``, market-order builder, session gate) and ``open_composer.execution.bar_source``
/ ``research.bars.hourly`` (bar aggregation).  See ``docs/runbook-intraday-runner.zh.md``.
"""
