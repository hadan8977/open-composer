from __future__ import annotations

import sys

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.multiasset_paper_control_r7_snapshot import (
    run_r7_forward_observation_cycle,
)
from open_composer.config import project_root


def main() -> int:
    try:
        result = run_r7_forward_observation_cycle(project_root())
    except (FileNotFoundError, OSError, ValueError, AlpacaDataError) as exc:
        print(f"R7 forward observation failed: {exc}", file=sys.stderr)
        return 1
    observation = result.observation
    print(
        "R7 forward observation complete "
        f"session={result.snapshot.market_session.isoformat()} "
        f"snapshot_reused={str(result.snapshot.reused_snapshot).lower()} "
        f"progress={observation.valid_session_count}/20 "
        f"forward_pass={str(observation.forward_observation_pass).lower()} "
        "broker_writes=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
