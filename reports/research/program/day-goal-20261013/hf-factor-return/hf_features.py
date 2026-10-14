"""Frozen causal source transformations and full input preparation, without fits."""

import hashlib
import json
import mmap
import os
import resource
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

P = Path(__file__).parent
FEATURE = P / "features"
VIEWS = ["IDX", "SUM", "INV", "IDX_STALE", "INV_STALE"]


def bind(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"path": str(path), "sha256": h.hexdigest(), "bytes": path.stat().st_size}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def flush_evict(*arrays):
    for a in arrays:
        a.flush()
        a._mmap.madvise(mmap.MADV_DONTNEED)


def aggregate_day(minutes, values, n_windows):
    """Slot0 is observed overnight; slot k ends 09:30+15*k, with exact15 rows."""
    if not np.any(minutes == 570):
        return None
    assert len(np.unique(minutes)) == len(minutes)
    idx = np.zeros((27, values.shape[1]), dtype=np.float64)
    sums = np.zeros_like(idx)
    valid = np.zeros(27, dtype=bool)
    overnight = values[minutes == 570][0]
    idx[0], sums[0], valid[0] = np.log1p(overnight), overnight, True
    for k in range(1, n_windows + 1):
        wanted = np.arange(571 + 15 * (k - 1), 571 + 15 * k)
        keep = (minutes >= wanted[0]) & (minutes <= wanted[-1])
        if np.array_equal(minutes[keep], wanted):
            sums[k] = values[keep].sum(axis=0)
            idx[k] = np.log1p(values[keep]).sum(axis=0)
            valid[k] = True
    return idx, sums, valid


def prior_channels(idx, sums, valid):
    if not valid[0] or not valid[1] or valid[1:].sum() < 4:
        return None
    completed = np.flatnonzero(valid[1:]) + 1
    return {
        "IDX": idx[completed].sum(axis=0) + idx[0],
        "SUM": sums[completed].sum(axis=0) + sums[0],
        "INV": (sums[completed] - sums[1]).sum(axis=0),
    }


def current_har(idx, sums, valid, k, previous):
    """Input availability depends only on the preceding/current completed four grids."""
    if previous is None or k < 4 or not valid[k - 3 : k + 1].all() or not valid[1]:
        return None
    inv = sums[k - 3 : k + 1] - sums[1]
    return {
        "IDX": np.concatenate((idx[k], idx[k - 3 : k + 1].mean(axis=0), previous["IDX"])),
        "SUM": np.concatenate((sums[k], sums[k - 3 : k + 1].mean(axis=0), previous["SUM"])),
        "INV": np.concatenate((inv[-1], inv.mean(axis=0), previous["INV"])),
    }


class CausalJumpFilter:
    def __init__(self):
        self.alpha = 1 - np.exp(-np.log(2) / 26)
        self.last = deque(maxlen=2)
        self.ewma = None
        self.full_days = deque(maxlen=252)

    def day_tau(self):
        if len(self.full_days) < 52:
            return None
        mean_squares = np.square(np.array(self.full_days)).mean(axis=0)
        overall = mean_squares.mean()
        return mean_squares / overall if overall > 0 else None

    def observe_completed(self, value, k, tau):
        # The BV product and tau use information available before this return.
        if len(self.last) == 2:
            product = abs(self.last[-1] * self.last[-2])
            self.ewma = (
                product
                if self.ewma is None
                else self.alpha * product + (1 - self.alpha) * self.ewma
            )
        threshold = None
        if tau is not None and self.ewma is not None:
            sigma2 = (np.pi / 2) * 26 * self.ewma * tau[k - 1]
            threshold = 3.5 * np.sqrt(sigma2) * (1 / 26) ** 0.49
        self.last.append(value)
        return (
            value
            if threshold is not None and abs(value) <= threshold
            else 0.0
            if threshold is not None
            else np.nan
        ), threshold


def build_inputs():
    import pyarrow as pa
    import pyarrow.parquet as pq

    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (620, 620))
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    FEATURE.mkdir(exist_ok=True)
    source = json.loads((P / "complete-source-input-manifest.json").read_text())
    review = json.loads((P / "independent-plan-review.json").read_text())
    accepted = json.loads((P / "independent-complete-source-input-acceptance.json").read_text())
    assert review["verdict"] == "approve_deep_plan"
    assert accepted["verdict"] == "accept_complete_conditional_source_input"
    schema = json.loads((P / "complete-source-input-QA.json").read_text())
    factors = schema["factor_columns"]
    assert len(factors) == 272
    mkt = factors.index("ff__mkt")
    plan = json.loads((P / "scientific-plan.json").read_text())
    keys = [factors.index(name) for name in plan["feature_and_label"]["key5"]]
    policies = json.loads((P / "source-conditional-clock.json").read_text())["rows"]
    policy = {row["date"]: row for row in policies}
    # Storage indices do not determine whether a source packet can be activated.
    days = [d["date"] for d in schema["days"]]
    index = {d: i for i, d in enumerate(days)}
    shape = (len(days), 27, 272)
    compact_idx = np.lib.format.open_memmap(
        FEATURE / "source-IDX.npy", mode="w+", dtype="float64", shape=shape
    )
    compact_sum = np.lib.format.open_memmap(
        FEATURE / "source-SUM.npy", mode="w+", dtype="float64", shape=shape
    )
    valid = np.zeros((len(days), 27), dtype=bool)
    nominal = np.zeros(len(days), dtype=np.int16)
    activated = []
    day_qa = []
    for item in source["files"]:
        path = Path(item["path"])
        assert bind(path)["sha256"] == item["sha256"]
        table = pq.read_table(path, use_threads=False)
        assert table.column_names == factors + ["datetime"] or set(table.column_names) == set(
            factors + ["datetime"]
        )
        ticks = table.column("datetime").to_numpy()
        dates = ticks.astype("datetime64[D]")
        values = np.column_stack([table.column(name).to_numpy() for name in factors])
        assert values.shape == (item["rows"], 272)
        assert np.isfinite(values).all() and (values > -1).all()
        groups, starts, counts = np.unique(dates, return_index=True, return_counts=True)
        for day, start, count in zip(groups, starts, counts, strict=True):
            ds = str(day)
            minutes = ((ticks[start : start + count] - day) / np.timedelta64(1, "m")).astype(int)
            assert np.all(ticks[start : start + count] == day + minutes * np.timedelta64(1, "m"))
            row = policy.get(ds)
            n = 14 if row and row["nominal_source_close"] == "13:00:00" else 26
            result = aggregate_day(minutes, values[start : start + count], n) if row else None
            i = index[ds]
            if result is None:
                day_qa.append(
                    dict(date=ds, activated=False, reason="no_frozenweekday_policy_or_observed0930")
                )
                continue
            idx, sums, mask = result
            compact_idx[i], compact_sum[i], valid[i], nominal[i] = idx, sums, mask, n
            activated.append(i)
            day_qa.append(
                dict(
                    date=ds,
                    activated=True,
                    nominal=n,
                    mature_windows=(np.flatnonzero(mask[1:]) + 1).tolist(),
                    missing_windows=(np.flatnonzero(~mask[1 : n + 1]) + 1).tolist(),
                    quarantined_post_cutoff_rows=int((minutes > 570 + 15 * n).sum()),
                )
            )
        del values, table
        flush_evict(compact_idx, compact_sum)
        save(
            FEATURE / "preparation-progress.json",
            dict(stage="source15", last_month=item["month"], economic_fits=0),
        )
        print("compact", item["month"], flush=True)
    np.save(FEATURE / "source-valid.npy", valid)
    np.save(FEATURE / "source-nominal.npy", nominal)
    save(FEATURE / "source-day-QA.json", day_qa)
    # Allocate an upper bound; expose only the actually written n_rows in metadata.
    upper = len(activated) * 22
    matrices = {
        name: np.lib.format.open_memmap(
            FEATURE / f"HAR-{name}.npy", mode="w+", dtype="float64", shape=(upper, 816)
        )
        for name in VIEWS
    }
    labels = np.lib.format.open_memmap(
        FEATURE / "labels.npy", mode="w+", dtype="float64", shape=(upper, 2)
    )
    ar = np.lib.format.open_memmap(
        FEATURE / "AR26.npy", mode="w+", dtype="float64", shape=(upper, 26)
    )
    records = []
    jump = CausalJumpFilter()
    market_history = deque(maxlen=26)
    nrow = 0
    prevchannels = {}
    predictions_by_year = {}
    for packet, i in enumerate(activated):
        idx, sums, mask, n = compact_idx[i], compact_sum[i], valid[i], int(nominal[i])
        tau = jump.day_tau()
        filtered = np.full(27, np.nan)
        thresholds = np.full(27, np.nan)
        histories = {}
        for k in range(1, n + 1):
            if mask[k]:
                r = float(idx[k, mkt])
                filtered[k], threshold = jump.observe_completed(r, k, tau)
                if threshold is not None:
                    thresholds[k] = threshold
                market_history.append(r)
            if k >= 4 and k < n:
                histories[k] = list(reversed(market_history)) if len(market_history) == 26 else None
        current_previous = prevchannels.get(activated[packet - 1]) if packet >= 1 else None
        for k in range(4, n):
            current = current_har(idx, sums, mask, k, current_previous)
            if current is None or packet < 21 or histories[k] is None:
                continue
            stale_i = activated[packet - 20]
            if k >= nominal[stale_i]:
                continue
            stale_previous = prevchannels.get(activated[packet - 21])
            stale = current_har(
                compact_idx[stale_i], compact_sum[stale_i], valid[stale_i], k, stale_previous
            )
            if stale is None:
                continue
            for view in ["IDX", "SUM", "INV"]:
                matrices[view][nrow] = current[view]
            for view in ["IDX", "INV"]:
                x = stale[view].copy()
                for channel in range(3):
                    x[channel * 272 + mkt] = current[view][channel * 272 + mkt]
                matrices[view + "_STALE"][nrow] = x
            ar[nrow] = histories[k]
            labels[nrow] = [float(idx[k + 1, mkt]) if mask[k + 1] else np.nan, filtered[k + 1]]
            minute = 570 + 15 * k
            ds = days[i]
            records.append(
                dict(
                    row=nrow,
                    date=ds,
                    minute=minute,
                    packet_index=packet,
                    source_day_index=i,
                    target_mature=bool(mask[k + 1]),
                    cts_target_available=bool(np.isfinite(filtered[k + 1])),
                    tau_from_prior_complete_days=tau is not None,
                    target_threshold=float(thresholds[k + 1])
                    if np.isfinite(thresholds[k + 1])
                    else None,
                )
            )
            predictions_by_year[ds[:4]] = predictions_by_year.get(ds[:4], 0) + 1
            nrow += 1
        prevchannels[i] = prior_channels(idx, sums, mask)
        if n == 26 and mask[1:27].all():
            jump.full_days.append(np.array(idx[1:27, mkt], copy=True))
        if packet % 64 == 0:
            flush_evict(compact_idx, compact_sum, *matrices.values(), labels, ar)
            save(
                FEATURE / "preparation-progress.json",
                dict(stage="HAR", last_date=days[i], n_rows=nrow, economic_fits=0),
            )
    flush_evict(compact_idx, compact_sum, *matrices.values(), labels, ar)
    save(FEATURE / "packet-row-clock.json", records)
    metadata = dict(
        schema_version=1,
        as_of_utc=datetime.now(UTC).isoformat(),
        n_rows=nrow,
        allocated_rows=upper,
        factors=factors,
        market_column=mkt,
        key5_columns=keys,
        channels=["current15", "same_day_last4_mean", "previous_packet_day"],
        feature_layout="channel-major,272actualsourcefactors perchannel",
        views=VIEWS,
        rows_by_year=predictions_by_year,
        common_clock_includes_unmatured_future_targets=True,
        n_missing_future_labels=sum(not r["target_mature"] for r in records),
        n_unavailable_cts_labels=sum(not r["cts_target_available"] for r in records),
        scientific_plan=bind(P / "scientific-plan.json"),
        source_manifest=bind(P / "complete-source-input-manifest.json"),
        source_review=bind(P / "independent-complete-source-input-acceptance.json"),
        causal_builder=bind(Path(__file__)),
        source_calendars_verified_venue=False,
        new_model_fits=0,
        economic_returns_computed=False,
        CPU_process=resource.getrusage(resource.RUSAGE_SELF).ru_utime
        + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    save(FEATURE / "feature-metadata.json", metadata)
    save(
        FEATURE / "feature-input-manifest.json",
        dict(
            metadata=bind(FEATURE / "feature-metadata.json"),
            files=[bind(path) for path in FEATURE.glob("*.npy")]
            + [bind(FEATURE / "packet-row-clock.json"), bind(FEATURE / "source-day-QA.json")],
            actual_complete=True,
            economic_ready=False,
        ),
    )
    save(
        FEATURE / "preparation-progress.json", dict(stage="complete", n_rows=nrow, economic_fits=0)
    )
    print("feature_complete", nrow, metadata["CPU_process"], flush=True)


if __name__ == "__main__":
    build_inputs()
