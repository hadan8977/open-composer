# External Brief: h20260928_41_country_etf_rotation

See `direction-review.json` and `external-brief.json` for the full source
list, applicability notes and reflections. Summary: this batch reuses the
Quantpedia "Momentum Factor Effect in Country Equity Indexes" mechanism
(cross-sectional momentum across country equities) applied to 9 US-listed
single-country equity ETFs, and reuses the sibling h20260928_40_equity_etf_
menus batch's own `make_rotation_fn` implementation unedited. No new
momentum formula, absolute-momentum rule or weighting scheme is
introduced; only the menu (ticker list) and grid change.
