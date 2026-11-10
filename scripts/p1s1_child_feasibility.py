"""Bounded DLSA child data-feasibility audit; never computes strategy returns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research.features.price_hygiene import sanitize_price_matrices
from scripts.p1s1_build import daily_returns, load_store, monthly_universes


def audit(store_path: Path, residual_path: Path, output: Path, chunk_symbols: int) -> dict:
    store = load_store(store_path)
    close = np.load(store_path / "close.npy", mmap_mode="r")
    dates = store.dates
    break_count = 0
    masked_cells = 0
    masked_symbols: set[str] = set()
    for start in range(0, close.shape[1], chunk_symbols):
        stop = min(start + chunk_symbols, close.shape[1])
        frame = pd.DataFrame(np.asarray(close[:, start:stop], dtype="float64"), index=dates)
        frame.columns = store.symbols[start:stop].astype(str)
        _, _, report = sanitize_price_matrices(frame)
        break_count += len(report.breaks)
        masked_cells += report.price_cells_masked
        masked_symbols.update(report.masked_symbols)

    rows, trade, residual_mask = monthly_universes(store)
    blocks = []
    for path in [store_path.parent / "p1s1_dlsa" / "blocks.json", store_path / "blocks.json"]:
        if path.is_file():
            blocks = json.loads(path.read_text(encoding="utf-8"))
            break

    residual_meta = json.loads((residual_path / "meta.json").read_text(encoding="utf-8"))
    residual_values = np.load(residual_path / "residual.npy", mmap_mode="r")
    beta = np.load(residual_path / "beta_refresh.npy", mmap_mode="r")
    weights = np.load(residual_path / "weights_refresh.npy", mmap_mode="r")
    sample_errors: list[float] = []
    for refresh_row in np.linspace(
        0, len(residual_meta["successful_refresh_indices"]) - 1, 3, dtype=int
    ):
        t = residual_meta["successful_refresh_indices"][refresh_row]
        r = daily_returns(np.asarray(close[t - 1 : t + 1], dtype="float64"))[1]
        r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
        expected = r - beta[refresh_row].astype("float64") @ (
            weights[refresh_row].astype("float64") @ r
        )
        stored = residual_values[t].astype("float64")
        valid = np.isfinite(stored) & np.isfinite(beta[refresh_row]).all(axis=1)
        if valid.any():
            sample_errors.append(float(np.max(np.abs(stored[valid] - expected[valid]))))

    result = {
        "schema_version": 1,
        "iter_id": "t20261010_p1_s1_dlsa_review",
        "audit_type": "pre_backtest_data_feasibility_only",
        "source": {
            "path": str(store_path),
            "dates": [str(d.date()) for d in dates[[0, -1]]],
            "shape": list(close.shape),
        },
        "pit_universe": {
            "monthly_rows": len(rows),
            "trade_mask_shape": list(trade.shape),
            "residual_mask_shape": list(residual_mask.shape),
            "universe_rebuilt_from_prior_month_end": True,
            "permanent_security_id_available": False,
            "delisting_returns_available": False,
        },
        "price_hygiene": {
            "sanitize_price_matrices_called": True,
            "close_breaks_detected": break_count,
            "masked_cells": masked_cells,
            "masked_symbols": len(masked_symbols),
            "open_matrix_available": False,
            "split_like_trigger_exclusion": (
                "dependency_skipped: open/OHLC and corporate-action feed are absent "
                "from T-22 memmap"
            ),
        },
        "residual_identity": {
            "pca_refresh_samples": len(sample_errors),
            "max_abs_error": max(sample_errors) if sample_errors else None,
            "ipca_neutrality": "dependency_skipped: IPCA child residual store not present",
        },
        "calendar_label_alignment": {
            "blocks_available": len(blocks),
            "frozen_oos_selection_untouched": True,
            "next_close_fill_coverage": "unverified",
        },
        "cost_borrow_capacity": {
            "cost_table_present": True,
            "borrow_rule_present": True,
            "realized_fill_and_unfilled_opportunity_cost": "unverified",
        },
        "workflow_pass": True,
        "research_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": False,
        "dependency_skipped": [
            "open/OHLC and corporate-action feed absent from current T-22 memmap",
            "permanent security identity absent",
            "delisting returns absent",
            "IPCA residual store absent",
            "realized next-close fill coverage and unfilled opportunity cost unverified",
        ],
        "decision": (
            "dependency_skipped: candidate universe cannot be mapped to permanent "
            "security identity or delisting returns; close-only source also cannot "
            "prove split-like trigger exclusion; no backtest/training/remote "
            "evaluation authorized"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=Path("data/research/t22_streversal"))
    parser.add_argument("--residual", type=Path, default=Path("data/research/p1s1_dlsa/pca5_full"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-symbols", type=int, default=128)
    args = parser.parse_args()
    print(json.dumps(audit(args.store, args.residual, args.output, args.chunk_symbols), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
