"""Read the sealed, reconciled all-strategy projection without refreshing it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _chart(points, field):
    values = [p[field] for p in points if p[field] is not None]
    low, high = min([0, *values]), max([0, *values])
    span = high - low or 1

    def y(v):
        return 150 - (v - low) / span * 135

    step = 780 / max(1, len(points))
    return dict(
        baseline=y(0),
        low=low,
        high=high,
        bars=[
            dict(
                day=p["day"],
                value=p[field],
                x=i * step + 1,
                width=max(1, step - 2),
                y=min(y(0), y(p[field])) if p[field] is not None else None,
                height=max(1, abs(y(p[field]) - y(0))) if p[field] is not None else None,
                pools=p["pools"],
                missing=p["missing"]
                + (
                    ["本金生效时点未证实: " + n for n in p.get("capital_missing_details", [])]
                    if field == "return_pct"
                    else []
                ),
            )
            for i, p in enumerate(points)
        ],
    )


def load_paper_overview(root: Path) -> dict:
    try:
        config = json.loads((root / "config/paper-overview-dashboard.json").read_text())
        path = (root / config["path"]).resolve()
        if not path.is_relative_to((root / "reports/paper").resolve()):
            raise ValueError("overview outside paper reports")
        with path.open("rb") as stream:
            raw = stream.read(2_097_153)
        if len(raw) > 2_097_152 or hashlib.sha256(raw).hexdigest() != config["sha256"]:
            raise ValueError("overview projection changed")
        data = json.loads(raw)
        if data["schema_version"] != 1 or not data["daily"]:
            raise ValueError("unsupported overview")
        return {
            **data,
            "available": True,
            "artifact_sha256": config["sha256"],
            "charts": {k: _chart(data["daily"], k) for k in ("pnl_usd", "return_pct")},
        }
    except (OSError, KeyError, TypeError, ValueError):
        return {"available": False, "warning": "总览数据尚不可用", "daily": []}
