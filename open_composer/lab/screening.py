"""The existing screen CLI's common batch/ledger/result path; no new rule selection."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_composer.lab.adapters import screen_engine, screen_modules
from open_composer.lab.batch import Variant, run_batch, write_evidence
from open_composer.lab.ledger import TrialLedger
from open_composer.lab.metrics import DSRConfig
from open_composer.lab.models import Experiment
from open_composer.research.agent_workflow import identifier, require_research


def run_screen_batch(
    root: Path,
    batch_name: str,
    *,
    iteration: str | None,
    smoke: bool = False,
    direction: str | None = None,
    batch_id: str | None = None,
) -> Path:
    root = root.resolve()
    require_research(root)
    batch, lane = screen_modules(root)
    module = batch.load_batch_module(batch_name)
    candidates = batch.candidates_from_module(module)
    if not smoke:
        if not iteration:
            raise ValueError("A real screen batch needs its accepted iteration manifest")
        batch.load_manifest_guard(batch.ITERATIONS_DIR / iteration, [c.id for c in candidates])
    direction = identifier(direction or iteration or "screen_smoke")
    batch_id = identifier(batch_id or batch_name)
    target = root / "research" / direction
    if (target / "batches" / batch_id).exists():
        raise ValueError("Batch already exists; reconcile it instead of replaying")
    ledger = TrialLedger(target / "trials.jsonl")
    historical = root / "reports/research/screens" / batch_name / "leaderboard.json"
    import_id = f"legacy_screen_{batch_name}"
    if (
        not smoke
        and historical.exists()
        and not any(e.trial_id == import_id for e in ledger.events())
    ):
        saved = json.loads(historical.read_text())
        count = saved.get("n_trials")
        if isinstance(count, int) and count > 0:
            ledger.import_prior(
                import_id,
                count=count,
                evidence=[str(historical.relative_to(root))],
                note="Known original screen starts; unrelated/unknown history remains unknown",
            )
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel(
        candidates, getattr(module, "extend_panel", None)
    )
    problems = batch.calendar_anchor_problems(close, candidates)
    if problems:
        raise ValueError("; ".join(problems))
    shy = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3, _ = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    panel = dict(
        close=close, leg_open=leg_open, leg_close=leg_close, rf=rf, shy_ret=shy, s3_ret10=s3
    )
    capital = 20_000.0
    outputs = {}

    def evaluate(candidate):
        output = screen_engine(
            root, candidate, panel=panel, n_trials=ledger.n_trials, initial_equity_usd=capital
        )
        outputs[candidate.id] = output
        print(f"  {candidate.id} done", flush=True)
        return output

    def statistic(output):
        # Native first-valid dates can differ by candidate: retain each actual calendar.
        benchmark = rf.loc[output.net_returns.index]
        return DSRConfig(
            method="campaign_statistics",
            benchmark=benchmark,
            benchmark_note="Native BIL on the exact candidate anchor sessions",
            hac_lag=lane.DSR_HAC_LAG,
            assumptions="Cumulative known candidate starts including failures; native HAC; "
            "offsets are the original robustness rule, not newly selected trials. "
            "Other historical searches may be unknown; this is not promotion evidence.",
        )

    result = run_batch(
        root,
        experiment=Experiment(
            direction=direction,
            kind="diagnostic" if smoke else "financial",
            data_and_exposure=f"{iteration}: native windows; seen holdout remains contaminated",
            costs="Native next-open linear-leg ledger, 10/20 bp per side; SHY residual capital",
            baseline="Native BIL excess statistics; per-window same-volatility S3 control",
            limitations=(
                "Known trial inventory is a lower bound where earlier searches are unrecorded.",
                "USD values scale native returns to $20,000; capacity is not established.",
                "Per-candidate matched control stays in native.json; dollar baseline not inferred.",
            ),
        ),
        batch_id=batch_id,
        variants=[
            Variant(
                c.id,
                {"batch": batch_name, "source_card": c.source_card},
                lambda c=c: evaluate(c),
                counts_as_trial=not smoke,
                exposure_note="Diagnostic smoke" if smoke else "Selectable screen candidate",
            )
            for c in candidates
        ],
        dsr_config=statistic,
    )
    rows, return_columns = [], {}
    for candidate in candidates:
        output = outputs.get(candidate.id)
        if candidate.id not in result.results:
            rows.append(
                {
                    "id": candidate.id,
                    "skipped": True,
                    "skip_reason": result.failures.get(candidate.id, "No completed result"),
                }
            )
            continue
        row = dict(output.native)
        metrics = json.loads((result.results[candidate.id].parent / "metrics.json").read_text())
        row["source_dsr_anchor"] = row.get("dsr_anchor")
        row["source_n_trials"] = row["n_trials"]
        row["n_trials"] = result.n_trials
        row["dsr_anchor"] = metrics["dsr"]["dsr"]
        rows.append(row)
        for column, values in output.ledger.items():
            if column.startswith(("net10_", "net20_")):
                tag, offset = column.split("_offset_")
                return_columns[f"{candidate.id}__o{int(offset):02d}__{tag}"] = values
    leaderboard = dict(
        batch=batch_name,
        generated_at=pd.Timestamp.now(tz="UTC").isoformat(),
        git_commit=batch.git_commit(),
        engine_source_files=batch.ENGINE_SOURCES,
        cost_bps_primary=lane.COST_BPS_PRIMARY,
        cost_bps_stress=lane.COST_BPS_STRESS,
        windows=lane.WINDOWS,
        contaminated_windows=sorted(lane.CONTAMINATED_WINDOWS),
        n_trials=result.n_trials,
        smoke=smoke,
        iteration=iteration,
        candidates=rows,
    )
    write_evidence(result.folder / "leaderboard.json", leaderboard)
    (result.folder / "leaderboard.md").write_text(batch.render_leaderboard_md(leaderboard))
    if return_columns:
        pd.DataFrame(return_columns).to_parquet(result.folder / "returns.parquet")
    return result.folder
