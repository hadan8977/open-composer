"""Original shared-feed branch with the isolated five-decimal serialization."""

from native_events import causal_activity
from native_events5 import native_month
from nautilus_trader.model.identifiers import ClientId


def feed(accounts, packets, scenario, factors, trigger_masks, *, afternoon):
    active = set()
    for _engine, strategy in accounts:
        active.update(causal_activity(strategy, packets[0], afternoon=afternoon))
    books, quotes, boundaries, next_factors = native_month(
        packets, scenario, factors, trigger_masks, active_symbols=active
    )
    # These data objects have no account state. Native engines independently
    # copy their L2 book state and maintain their own cache/matching/fees.
    for engine, strategy in accounts:
        strategy.runtime_active_symbols = active
        if books:
            engine.add_data(books)
        if quotes:
            engine.add_data(quotes)
        engine.add_data(boundaries, client_id=ClientId("MARTIN"))
        engine.run(streaming=True)
        engine.clear_data()
    return next_factors, dict(books=len(books), quotes=len(quotes), boundaries=len(boundaries))
