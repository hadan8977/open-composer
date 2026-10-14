"""Optional runtime limits; absent environment preserves legacy defaults."""

from __future__ import annotations

import os


def apply_forward_limits(connection):
    size = os.environ.get("OC_FORWARD_SPILL_BYTES")
    if size is not None:
        value = int(size)
        if value <= 0:
            raise ValueError("invalid admitted forward spill limit")
        connection.execute(f"SET max_temp_directory_size='{value}B'")
        connection.execute("SET threads=1")
    return connection
