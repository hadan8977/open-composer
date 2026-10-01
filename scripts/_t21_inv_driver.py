"""Throwaway driver for T-20261001-21: run compare() and merge into invariance.json."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cfi", Path(__file__).parent / "check_feature_invariance.py"
)
m = importlib.util.module_from_spec(spec)
sys.modules["cfi"] = m
spec.loader.exec_module(m)
OUT = Path("reports/research/program/data-refresh-2026-10-01/invariance.json")


def main():
    table, new, old, date_col, cut, keys, bn = sys.argv[1:8]
    extra = {}
    if len(sys.argv) > 8:
        extra = json.loads(sys.argv[8])
    pairs = extra.get("pairs") or [[new, old, table]]
    store = json.loads(OUT.read_text()) if OUT.exists() else {}
    entry = {"parts": {}}
    for n, o, label in pairs:
        r = m.compare(
            Path(n),
            Path(o),
            date_col=date_col,
            cut=date.fromisoformat(cut),
            keys=keys.split(","),
            baseline_n=int(bn),
        )
        entry["parts"][label] = r
        print(
            label,
            {
                k: r[k]
                for k in (
                    "keys_equal",
                    "max_changed_share",
                    "n_new_dates",
                    "last_date",
                    "coverage_ratio",
                    "pass",
                    "n_keys_only_new",
                    "n_keys_only_old",
                )
            },
            flush=True,
        )
    entry["pass"] = all(p["pass"] for p in entry["parts"].values())
    entry["keys_equal"] = all(p["keys_equal"] for p in entry["parts"].values())
    entry["max_changed_share"] = max(p["max_changed_share"] for p in entry["parts"].values())
    store[table] = entry
    OUT.write_text(json.dumps(store, indent=1, default=str) + "\n")


main()
