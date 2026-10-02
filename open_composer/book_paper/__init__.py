"""Short-capable portfolio order engine for the equity book (Alpaca Paper, T-20261001-16).

Dry-run first: ``plan`` reads the account read-only and writes an order plan; ``submit`` is the
only path that sends orders and needs an explicit ``--submit``.  Credentials for the two book
accounts (``quant1`` and ``quant2``) are read by variable name from a file outside the repo and
never printed, logged or written.
"""
