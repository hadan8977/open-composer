# Search Space: mom_stock_intraday_codesign_q1

The round is capped at 48 counted candidates across deterministic daily, ML-native daily, independent intraday, and event/LLM paths. Every skipped dependency still consumes its preregistered slot. Candidate generation cannot use historical challenge or forward-observation outcomes.

The first stage compares economically different method families rather than many nearby parameter values. The second stage uses grouped chronological folds with complete label intervals and purge/embargo. The same portfolio constraints, benchmark family, and base/two/four-times cost assumptions apply to all candidates. No candidate can add a model, factor, symbol subset, prompt, or threshold after seeing an outer-fold result.

Daily stock history selected from the current universe remains exploratory before the frozen membership date. Intraday IEX candidates remain research-only until session completeness and SIP comparison pass. Event candidates are counted and skipped when rights or immutable PIT versions are unavailable.
