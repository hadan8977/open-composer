from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def select_random_combinations(
    combinations: Sequence[T],
    *,
    max_candidates: int,
    seed: int | None = None,
) -> list[T]:
    """Return a deterministic random subset without replacement.

    Random search is the default scalable alternative to exhaustive grid
    discovery. It still obeys the pre-registered candidate budget; it only
    changes which combinations are explored when the full grid is larger.
    """
    if max_candidates < 1:
        msg = "max_candidates must be at least 1"
        raise ValueError(msg)
    selected = list(combinations)
    rng = random.Random(seed)
    rng.shuffle(selected)
    return selected[:max_candidates]
