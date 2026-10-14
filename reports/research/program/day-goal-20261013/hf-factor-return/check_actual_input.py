"""Non-economic source schema, clock and missing-value QA of one retained month."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

P = Path(__file__).parent


def main():
    path = P / "inputs/199601.parquet"
    a = pd.read_parquet(path)
    ix = a.index
    counts = pd.Series(1, index=ix).groupby(ix.normalize()).sum()
    missing = a.isna().sum()
    names = list(a.columns)
    first_day = ix[ix.normalize() == ix[0].normalize()]
    out = {
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "scope": "One complete author month for input QA only; no economic smoke result",
        "input_path": str(path),
        "SHA256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "rows": len(a),
        "columns": len(a.columns),
        "column_types": {str(k): v for k, v in a.dtypes.astype(str).items()},
        "duplicate_timestamps": int(ix.duplicated().sum()),
        "monotonic_increasing": bool(ix.is_monotonic_increasing),
        "timezone": str(ix.tz),
        "first_timestamp": str(ix[0]),
        "last_timestamp": str(ix[-1]),
        "dates": len(counts),
        "rows_by_date": {str(k.date()): int(v) for k, v in counts.items()},
        "time_labels_first_day": [str(t.time()) for t in first_day[:20]],
        "time_labels_last_first_day": [str(t.time()) for t in first_day[-8:]],
        "factor_groups": {
            "CZ": sum(x.startswith("cz__") for x in names),
            "JKP": sum(x.startswith("jkp__") for x in names),
            "FF": sum(x.startswith("ff__") for x in names),
            "industry48": sum(x.startswith("ind48__") for x in names),
        },
        "NaN_values": int(a.isna().sum().sum()),
        "infinite_values": int(np.isinf(a.to_numpy()).sum()),
        "columns_with_missing": {str(k): int(v) for k, v in missing[missing > 0].items()},
        "source_paper_key_factors_present": {
            s: s in names for s in ["cz__betatailrisk", "jkp__ivol_capm_252d",
                                   "jkp__turnover_126d", "jkp__zero_trades_21d",
                                   "jkp__zero_trades_252d", "ff__mkt"]
        },
        "units_declared_by_author_page": "Minute percentage returns; adjusted overnight included",
        "unit_and_clock_conversion_accepted_for_economics": False,
        "actual_full_sample_ready": False,
        "ETF_prices_quoted_spreads_RF_full_sample_ready": False,
        "historical_PIT_or_thenvisible_weight_certified": False,
        "economic_runs": 0,
        "model_fits": 0,
        "signal_values_or_strategy_returns_evaluated": False,
        "next_action": "Complete plan and input/resource decision; no short-window fit or price proxy",
    }
    (P / "actual-one-month-input-QA.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ["rows", "columns", "timezone", "first_timestamp",
                                        "last_timestamp", "dates", "rows_by_date",
                                        "time_labels_first_day", "time_labels_last_first_day",
                                        "factor_groups", "NaN_values", "infinite_values",
                                        "columns_with_missing"]}, indent=2))


if __name__ == "__main__":
    main()
