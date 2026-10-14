"""Render fixed anonymous-episode method comparisons, with no market NAV."""

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    start = time.process_time()
    result = json.loads((HERE / "matched-comparison.json").read_text())
    rows = {
        (r["fold"], r["stream"]): r
        for r in result["summaries"]
        if r["profile"] == "CONTINUOUS_TARGET_DIAGNOSTIC" and r["cost"] == "SOURCE_NATIVE"
    }
    names = ["A05\nH1 gross", "A07\nH1 cost", "A08\nstate+arch", "A09\nH5 gross", "A10\nH5 cost"]
    streams = ["A05", "A07", "A08", "A09", "A10"]
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.9), sharey=True)
    for ax, fold in zip(axes, [0, 10], strict=True):
        net = [rows[fold, s]["mean_net_bps"] for s in streams]
        gross = [rows[fold, s]["daily_means"]["gross"] * 10000 for s in streams]
        pos = np.arange(len(streams))
        ax.bar(pos, net, width=0.64, color=["#2d728f" if n >= 0 else "#ba4c4c" for n in net])
        ax.scatter(pos, gross, color="#222222", marker="_", s=150, linewidths=2, label="Gross")
        for i, n in enumerate(net):
            ax.annotate(
                f"{n:+.2f}",
                (i, n),
                xytext=(0, 5 if n >= 0 else -14),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.set_xticks(pos, names)
        ax.set_title(f"Anonymous episode {fold:02} | 125 rows")
        ax.grid(axis="y", alpha=0.16)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Mean common-H1 diagnostic return (bp / row)")
    axes[1].legend(frameon=False)
    fig.suptitle(
        "Original DLSA fixed final99: learned objective vs matched H1 accounting", fontsize=13
    )
    fig.text(
        0.5,
        0.025,
        "5bp asset turnover + 1bp short cost; flat initial entry. "
        "Bars = net; black marks = gross.\n"
        "Anonymous perturbed inputs, single seed; H5 objective is not a five-day stock NAV. "
        "New A09/A10 episode10 pending independent acceptance.",
        ha="center",
        fontsize=8,
        color="#444444",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))
    target = HERE / "matched-H1-method-comparison.png"
    assert not target.exists()
    fig.savefig(target, dpi=150)
    plt.close(fig)
    print(json.dumps({"path": str(target), "CPU_seconds": time.process_time() - start}))


if __name__ == "__main__":
    main()
