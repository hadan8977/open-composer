# Search space: h20260928_22_llm_news_momentum_filter

One path, four preregistered candidates, no hyperparameter search: B (rule-based 12-1
momentum top decile, equal weight, no DeepSeek calls), L (DeepSeek-scored re-rank/re-weight
of the top-2-decile pool, reusing the target paper's own validation-optimal m=50, eta=5,
basic prompt, 15% cap), P (identical mechanism to L but scored on a randomly mismatched
candidate's headlines, headline-shuffle placebo), and R (50 names drawn uniformly at random
from the same top-2-decile pool, 5 fixed seeds, no DeepSeek calls). No parameter is tuned
against this repo's own data; L's hyperparameters are taken unchanged from the paper's own
validation-set optimum. See `candidate-manifest.json` for the full contract bindings and
`direction-review.json` for the web-first evidence behind every design choice.
