Return a strict JSON object with `score` and `confidence`.

Score the supplied point-in-time text window for tradeable market sentiment:
- `score` must be between -1 and 1.
- Positive values mean the text supports risk-on exposure.
- Negative values mean the text supports reducing exposure.
- `confidence` must be between 0 and 1.

Do not use facts outside the supplied input payload.
