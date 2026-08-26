from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from open_composer.adapters.execution.nautilus_runtime import _build_feature_data
from open_composer.expressions import ExpressionError, prepare_factor_frame
from open_composer.models.strategy_spec import FactorConfig

FACTOR_NAME = "term_structure"
FACTOR_FIELD = "normalized_term_slope"
INSTRUMENT_ID = InstrumentId(Symbol("TQQQ"), Venue("NASDAQ"))


def test_symbol_less_packet_uses_visible_at_and_preserves_fetched_at(tmp_path: Path) -> None:
    packet_path = tmp_path / "cboe-volatility-packets.jsonl"
    visible_at = pd.Timestamp("2026-01-05T14:30:00Z")
    fetched_at = pd.Timestamp("2026-08-14T16:22:05Z")
    _write_packets(
        packet_path,
        [
            {
                "observation_date": "2026-01-02",
                "published_at": "2026-01-02T21:15:00Z",
                "visible_at": visible_at.isoformat(),
                "fetched_at": fetched_at.isoformat(),
                FACTOR_FIELD: 0.125,
            }
        ],
    )
    factor = _factor(packet_path)
    frame = _price_frame(
        [
            "2026-01-05T14:29:59Z",
            "2026-01-05T14:30:00Z",
            "2026-01-05T14:31:00Z",
        ]
    )

    prepared = prepare_factor_frame(
        frame,
        {FACTOR_NAME: factor},
        symbol="TQQQ",
        require_feature_symbol=False,
    )
    events = _build_feature_data(_spec(factor), tmp_path, INSTRUMENT_ID)

    assert prepared[FACTOR_NAME].tolist() == [0.0, 0.125, 0.125]
    assert len(events) == 1
    assert _event_timestamp(events[0].ts_event) == visible_at
    assert _event_timestamp(events[0].ts_init) == visible_at
    assert _event_timestamp(events[0].source_fetched_at_ns) == fetched_at

    with pytest.raises(ExpressionError, match="missing required symbol"):
        prepare_factor_frame(
            frame,
            {FACTOR_NAME: factor},
            symbol="TQQQ",
            require_feature_symbol=True,
        )


def test_observation_timestamp_cannot_leak_before_visible_at(tmp_path: Path) -> None:
    packet_path = tmp_path / "future-visible.jsonl"
    visible_at = pd.Timestamp("2026-01-05T14:30:00Z")
    _write_packets(
        packet_path,
        [
            {
                "timestamp": "2026-01-02T21:15:00Z",
                "published_at": "2026-01-02T21:15:00Z",
                "visible_at": visible_at.isoformat(),
                "fetched_at": "2026-01-05T14:29:30Z",
                "symbol": "TQQQ",
                "features": {FACTOR_FIELD: -0.25},
            }
        ],
    )
    factor = _factor(packet_path)
    frame = _price_frame(
        [
            "2026-01-02T21:15:00Z",
            "2026-01-05T14:29:59Z",
            "2026-01-05T14:30:00Z",
        ]
    )

    prepared = prepare_factor_frame(frame, {FACTOR_NAME: factor}, symbol="TQQQ")
    events = _build_feature_data(_spec(factor), tmp_path, INSTRUMENT_ID)

    assert prepared[FACTOR_NAME].tolist() == [0.0, 0.0, -0.25]
    assert [_event_timestamp(event.ts_event) for event in events] == [visible_at]


def test_python_and_nautilus_use_the_same_effective_availability(tmp_path: Path) -> None:
    packet_path = tmp_path / "availability.jsonl"
    _write_packets(
        packet_path,
        [
            {
                "published_at": "2026-01-02T21:15:00Z",
                "visible_at": "2026-01-05T14:30:00Z",
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.2,
            },
            {
                "published_at": "2026-01-05T21:00:00Z",
                "fetched_at": "2026-01-05T21:05:00Z",
                FACTOR_FIELD: -0.1,
            },
        ],
    )
    factor = _factor(packet_path)
    frame = _price_frame(
        [
            "2026-01-05T14:29:59Z",
            "2026-01-05T14:30:00Z",
            "2026-01-05T21:04:59Z",
            "2026-01-05T21:05:00Z",
        ]
    )

    prepared = prepare_factor_frame(frame, {FACTOR_NAME: factor}, symbol="TQQQ")
    events = _build_feature_data(_spec(factor), tmp_path, INSTRUMENT_ID)

    assert [_event_timestamp(event.ts_event).isoformat() for event in events] == [
        "2026-01-05T14:30:00+00:00",
        "2026-01-05T21:05:00+00:00",
    ]
    assert prepared[FACTOR_NAME].tolist() == _nautilus_asof_values(
        events,
        pd.to_datetime(frame["timestamp"], utc=True),
        default=0.0,
    )


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("missing_path", "missing packet path"),
        ("missing_file", "packet does not exist"),
        ("empty_file", "is empty"),
        ("no_matching_symbol", "has no records matching TQQQ"),
    ],
)
def test_missing_or_unusable_packet_fails_closed_in_both_loaders(
    tmp_path: Path,
    case: str,
    error: str,
) -> None:
    packet_path = tmp_path / f"{case}.jsonl"
    if case == "missing_path":
        factor = FactorConfig(source="feature_packet", field=FACTOR_FIELD, default=0.0)
    else:
        if case == "empty_file":
            _write_packets(packet_path, [])
        elif case == "no_matching_symbol":
            _write_packets(
                packet_path,
                [
                    {
                        "symbol": "QQQ",
                        "visible_at": "2026-01-05T14:30:00Z",
                        "fetched_at": "2026-08-14T16:22:05Z",
                        FACTOR_FIELD: 0.1,
                    }
                ],
            )
        factor = _factor(packet_path)
    frame = _price_frame(["2026-01-05T14:30:00Z"])

    _assert_both_loaders_fail(factor, frame, tmp_path, error)


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("duplicate", "duplicates visible_at"),
        ("out_of_order", "out of visible_at order"),
        ("missing_session", "has a missing session"),
    ],
)
def test_duplicate_out_of_order_and_gapped_packets_fail_closed(
    tmp_path: Path,
    case: str,
    error: str,
) -> None:
    packet_path = tmp_path / f"{case}.jsonl"
    first_visible = "2026-03-06T14:30:00Z"
    if case == "duplicate":
        second_visible = first_visible
    elif case == "out_of_order":
        first_visible = "2026-03-09T13:30:00Z"
        second_visible = "2026-03-06T14:30:00Z"
    else:
        second_visible = "2026-03-10T13:30:00Z"
    _write_packets(
        packet_path,
        [
            {
                "visible_at": first_visible,
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.1,
            },
            {
                "visible_at": second_visible,
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.2,
            },
        ],
    )
    factor = _factor(
        packet_path,
        params={"availability_field": "visible_at", "forward_fill_allowed": False},
    )
    frame = _price_frame(["2026-03-09T13:30:00Z", "2026-03-10T13:30:00Z"])

    _assert_both_loaders_fail(factor, frame, tmp_path, error)


def test_stale_packet_fails_closed_in_both_loaders(tmp_path: Path) -> None:
    packet_path = tmp_path / "stale.jsonl"
    _write_packets(
        packet_path,
        [
            {
                "visible_at": "2026-03-06T14:30:00Z",
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.1,
            }
        ],
    )
    factor = _factor(packet_path, params={"max_age_sessions": 1})
    frame = _price_frame(["2026-03-09T13:30:00Z", "2026-03-10T13:30:00Z"])

    _assert_both_loaders_fail(factor, frame, tmp_path, "packet is stale")


def test_dst_and_holiday_session_age_match_in_both_loaders(tmp_path: Path) -> None:
    dst_path = tmp_path / "dst.jsonl"
    _write_packets(
        dst_path,
        [
            {
                "visible_at": "2026-03-06T14:30:00Z",
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.1,
            },
            {
                "visible_at": "2026-03-09T13:30:00Z",
                "fetched_at": "2026-08-14T16:22:05Z",
                FACTOR_FIELD: 0.2,
            },
        ],
    )
    dst_factor = _factor(
        dst_path,
        params={"forward_fill_allowed": False, "max_age_sessions": 1},
    )
    dst_frame = _price_frame(["2026-03-06T14:30:00Z", "2026-03-09T13:30:00Z"])

    dst_prepared = prepare_factor_frame(
        dst_frame,
        {FACTOR_NAME: dst_factor},
        symbol="TQQQ",
    )
    dst_events = _build_feature_data(
        _spec(dst_factor),
        tmp_path,
        INSTRUMENT_ID,
        decision_timestamps=dst_frame["timestamp"],
    )

    assert dst_prepared[FACTOR_NAME].tolist() == [0.1, 0.2]
    assert dst_prepared[FACTOR_NAME].tolist() == _nautilus_asof_values(
        dst_events,
        pd.to_datetime(dst_frame["timestamp"], utc=True),
        default=0.0,
    )

    holiday_path = tmp_path / "holiday.jsonl"
    _write_packets(
        holiday_path,
        [
            {
                "visible_at": "2026-11-25T14:30:00Z",
                "fetched_at": "2026-11-27T15:00:00Z",
                FACTOR_FIELD: 0.3,
            }
        ],
    )
    holiday_factor = _factor(holiday_path, params={"max_age_sessions": 1})
    holiday_frame = _price_frame(["2026-11-27T14:30:00Z"])

    holiday_prepared = prepare_factor_frame(
        holiday_frame,
        {FACTOR_NAME: holiday_factor},
        symbol="TQQQ",
    )
    holiday_events = _build_feature_data(
        _spec(holiday_factor),
        tmp_path,
        INSTRUMENT_ID,
        decision_timestamps=holiday_frame["timestamp"],
    )

    assert holiday_prepared[FACTOR_NAME].tolist() == [0.3]
    assert holiday_prepared[FACTOR_NAME].tolist() == _nautilus_asof_values(
        holiday_events,
        pd.to_datetime(holiday_frame["timestamp"], utc=True),
        default=0.0,
    )


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("missing_value", "missing field"),
        ("null_value", "finite numeric value"),
        ("nan_value", "finite numeric value"),
        ("infinite_value", "finite numeric value"),
        ("invalid_visible_at", "invalid visible_at"),
        ("missing_fetched_at", "missing fetched_at"),
    ],
)
def test_invalid_packet_rows_fail_closed_in_both_loaders(
    tmp_path: Path,
    case: str,
    error: str,
) -> None:
    packet_path = tmp_path / f"invalid-{case}.jsonl"
    row: dict[str, Any] = {
        "published_at": "2026-01-02T21:15:00Z",
        "visible_at": "2026-01-05T14:30:00Z",
        "fetched_at": "2026-08-14T16:22:05Z",
        FACTOR_FIELD: 0.2,
    }
    if case == "missing_value":
        row.pop(FACTOR_FIELD)
    elif case == "null_value":
        row[FACTOR_FIELD] = None
    elif case == "nan_value":
        row[FACTOR_FIELD] = float("nan")
    elif case == "infinite_value":
        row[FACTOR_FIELD] = float("inf")
    elif case == "invalid_visible_at":
        row["visible_at"] = "not-a-timestamp"
    elif case == "missing_fetched_at":
        row.pop("fetched_at")
    _write_packets(packet_path, [row])
    factor = _factor(packet_path)
    frame = _price_frame(["2026-01-05T14:30:00Z"])

    with pytest.raises(ExpressionError, match=error):
        prepare_factor_frame(frame, {FACTOR_NAME: factor}, symbol="TQQQ")
    with pytest.raises(ExpressionError, match=error):
        _build_feature_data(_spec(factor), tmp_path, INSTRUMENT_ID)


def _factor(path: Path, *, params: dict[str, Any] | None = None) -> FactorConfig:
    return FactorConfig(
        source="feature_packet",
        path=str(path),
        field=FACTOR_FIELD,
        default=0.0,
        params=params or {},
    )


def _spec(factor: FactorConfig) -> Any:
    return SimpleNamespace(
        factors={FACTOR_NAME: factor},
        primary_symbol="TQQQ",
        name="test_cboe_packet_parity",
    )


def _assert_both_loaders_fail(
    factor: Any,
    frame: pd.DataFrame,
    root: Path,
    error: str,
) -> None:
    with pytest.raises(ExpressionError, match=error):
        prepare_factor_frame(
            frame,
            {FACTOR_NAME: factor},
            root=root,
            symbol="TQQQ",
        )
    with pytest.raises(ExpressionError, match=error):
        _build_feature_data(
            _spec(factor),
            root,
            INSTRUMENT_ID,
            decision_timestamps=frame["timestamp"],
        )


def _price_frame(timestamps: list[str]) -> pd.DataFrame:
    count = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "open": [100.0] * count,
            "high": [101.0] * count,
            "low": [99.0] * count,
            "close": [100.0] * count,
            "volume": [1_000.0] * count,
        }
    )


def _write_packets(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _event_timestamp(nanos: int) -> pd.Timestamp:
    return pd.Timestamp(nanos, unit="ns", tz="UTC")


def _nautilus_asof_values(
    events: list[Any],
    timestamps: pd.Series,
    *,
    default: float,
) -> list[float]:
    values: list[float] = []
    cursor = 0
    current = default
    for timestamp in timestamps:
        while cursor < len(events) and events[cursor].ts_event <= timestamp.value:
            current = events[cursor].value
            cursor += 1
        values.append(current)
    return values
