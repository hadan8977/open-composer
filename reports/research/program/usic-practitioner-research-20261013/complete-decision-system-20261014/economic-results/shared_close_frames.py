"""Lazy immutable source Frame reuse proposal; no account or engine state.

Kept isolated until affected consumer acceptance. Caller clears each synchronous
source interval after both independent accounts consume it. Decode per row stays
at its original callback, including errors; this is not eager future decoding.
"""

from dataclasses import dataclass

import msgspec


@dataclass(frozen=True)
class CloseRowHandle:
    payload: str
    index: int
    leadership_score: float
    prior_dollar_volume: float
    symbol: str


class SharedCloseFrames:
    def __init__(self, decoder, *, maximum_payloads=1024):
        self.decoder = decoder
        self.maximum_payloads = maximum_payloads
        self._source = {}
        self._frames = {}
        self.payload_decodes = 0
        self.frame_decodes = 0
        self.cache_hits = 0

    def rows(self, payload):
        if payload not in self._source:
            if len(self._source) >= self.maximum_payloads:
                raise ValueError("source_interval_cache_bound_requires_clear")
            rows = msgspec.json.decode(payload)
            # Same prior ranking, stable tie-break and error point as adapter.
            rows.sort(
                key=lambda r: (
                    -r["leadership_score"],
                    -r["prior_dollar_volume"],
                    r["frame"]["symbol"],
                )
            )
            self._source[payload] = rows
            self.payload_decodes += 1
        return tuple(
            CloseRowHandle(
                payload,
                i,
                row["leadership_score"],
                row["prior_dollar_volume"],
                row["frame"]["symbol"],
            )
            for i, row in enumerate(self._source[payload])
        )

    def frame(self, handle):
        source = self._source[handle.payload]
        if not 0 <= handle.index < len(source):
            raise ValueError("invalid_source_row_handle")
        key = (handle.payload, handle.index)
        if key not in self._frames:
            # Existing decoder makes a new dict and frozen Frame/supports/anchors.
            # Failures remain failures on this requested row, not cached results.
            parsed = self.decoder(source[handle.index]["frame"])
            self._frames[key] = parsed
            self.frame_decodes += 1
        else:
            self.cache_hits += 1
        return self._frames[key]

    def clear_interval(self):
        self._source.clear()
        self._frames.clear()
