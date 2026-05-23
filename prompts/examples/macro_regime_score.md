Return a strict JSON object with `score`, `confidence`, and `regime`.

Score the supplied point-in-time macro window for equity risk appetite:
- `score` must be between -1 and 1.
- `confidence` must be between 0 and 1.
- `regime` must be one of `risk_on`, `neutral`, or `risk_off`.

Do not use facts outside the supplied input payload.
