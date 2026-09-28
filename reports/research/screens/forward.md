# Forward (shadow) tracking of kept candidates

Generated 2026-09-28T06:31:57.146092+00:00. T-20260928-07. Forward period = sessions strictly after `kept_at`; Sharpe/max DD reported only with >= 20 forward sessions (`MIN_SHARPE_SESSIONS=20`). `watch_recent` exit rule needs >= 63 forward sessions.

| id | tier | relation | integrity | n_fwd | fwd period | cum ret | sharpe | max DD | S3 cum ret | S3 sharpe | SPY cum ret | SPY sharpe | watch_exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| kept:h20260928_05_registry_etf_batch2:EOM_REVERSAL_SPY | watch_recent |  | ok | 0 | -..- | n/a | n/a | n/a | n/a | n/a | n/a | n/a | too early |
| kept:h20260928_05_registry_etf_batch2:FRONT_RUN_SECTOR_TOP2 | watch_recent |  | ok | 0 | -..- | n/a | n/a | n/a | n/a | n/a | n/a | n/a | too early |

## Dropped (not tracked)

| id | tier_raw | dropped_note |
|---|---|---|
| kept:h20260928_02_cross_asset_sleeve:D1 | dropped_by_owner | owner 2026-09-28: Defense First not needed; no cross-asset strategies |
