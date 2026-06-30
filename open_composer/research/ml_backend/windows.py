from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from open_composer.research.kernel.windows import (
    PurgedEmbargoConfig,
    ResearchWindowSplit,
    WalkForwardSlice,
)


@dataclass(frozen=True)
class MLWindowSlice:
    fold: int
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int
    metadata: WalkForwardSlice


def ml_walk_forward_slices(
    frame: pd.DataFrame,
    *,
    window_bars: int,
    test_window_bars: int,
    retrain_every_bars: int,
    horizon_bars: int,
    embargo_bars: int,
) -> list[MLWindowSlice]:
    """Create purged+embargo walk-forward slices for future-label ML training."""
    n_rows = len(frame)
    if n_rows <= horizon_bars + test_window_bars:
        return []
    slices: list[MLWindowSlice] = []
    fold = 1
    test_start = min(window_bars, max(0, n_rows - test_window_bars))
    while test_start < n_rows - horizon_bars:
        test_end = min(test_start + test_window_bars, n_rows - horizon_bars)
        train_start = max(0, test_start - window_bars)
        train_end = max(train_start, test_start - horizon_bars - embargo_bars)
        if train_end > train_start and test_end > test_start:
            slices.append(
                MLWindowSlice(
                    fold=fold,
                    train_start_idx=train_start,
                    train_end_idx=train_end,
                    test_start_idx=test_start,
                    test_end_idx=test_end,
                    metadata=WalkForwardSlice(
                        fold=fold,
                        train=_split_payload(
                            frame,
                            start=train_start,
                            end=train_end,
                            embargo=PurgedEmbargoConfig(
                                purged=True,
                                embargo_bars=embargo_bars,
                                reason=(
                                    "future-label purge removes horizon rows before test; "
                                    "embargo removes additional adjacent rows"
                                ),
                            ),
                        ),
                        test=_split_payload(
                            frame,
                            start=test_start,
                            end=test_end,
                            embargo=PurgedEmbargoConfig(
                                purged=False,
                                embargo_bars=0,
                                reason="test window",
                            ),
                        ),
                    ),
                )
            )
            fold += 1
        test_start += retrain_every_bars
    return slices


def _split_payload(
    frame: pd.DataFrame,
    *,
    start: int,
    end: int,
    embargo: PurgedEmbargoConfig,
) -> ResearchWindowSplit:
    if end <= start:
        return ResearchWindowSplit(train_rows=0, test_rows=0, embargo=embargo)
    start_ts = _timestamp_at(frame, start)
    end_ts = _timestamp_at(frame, end - 1)
    return ResearchWindowSplit(
        train_start=start_ts,
        train_end=end_ts,
        test_start=start_ts,
        test_end=end_ts,
        train_rows=end - start,
        test_rows=end - start,
        embargo=embargo,
    )


def _timestamp_at(frame: pd.DataFrame, index: int) -> str | None:
    if "timestamp" not in frame or index < 0 or index >= len(frame):
        return None
    value = frame.iloc[index]["timestamp"]
    return pd.Timestamp(value).isoformat()
