"""Modal App template, driven entirely by environment variables.

Not meant to be edited per job: `scripts/modal_run.py` sets `OC_*` env vars
and then runs `modal run scripts/modal_app.py` as a subprocess. This file is
parsed by the `modal` CLI's OWN Python interpreter (the isolated `uv tool
install modal` venv), not this project's `.venv` -- so only the standard
library and the `modal` package may be imported at module scope. Project
dependencies (pandas, duckdb, ...) are only ever imported inside `run_shard`,
which executes remotely inside the container image built from the repo's
locked dependencies.

Resource shape (cpu/memory/timeout/gpu) has to be known when the `@app.
function` decorator runs, i.e. at import time -- that is why it comes from
env vars set just before this file is invoked, rather than from `modal run`'s
own CLI-argument parsing.
"""

from __future__ import annotations

import json
import os
import tarfile
import tempfile
import time
from pathlib import Path

import modal

# Modal re-imports this exact module a SECOND time inside the container, to
# get a live reference to the decorated function -- not just once, locally,
# to build the App/Image/Function definitions. Every `OC_*` variable this
# file reads therefore has to be reachable from *both* places with the *same*
# value (an App/Function built with a different job name, thread count, or
# volume set locally than what the container sees on re-import would not
# hydrate correctly) -- so every one of them is echoed into `_oc_env` below
# and handed to `@app.function(env=...)`, which Modal sets as real container
# OS env vars before that re-import happens.
JOB = os.environ["OC_JOB"]
CPU = float(os.environ["OC_CPU"])
MEMORY_GIB = float(os.environ["OC_MEMORY_GIB"])
TIMEOUT_MIN = float(os.environ["OC_TIMEOUT_MIN"])
GPU = os.environ.get("OC_GPU") or None
STAGE_DIR = os.environ["OC_STAGE_DIR"]
THREADS = int(os.environ["OC_THREADS"])
OC_DATA_DIRS_RAW = os.environ.get("OC_DATA_DIRS", "[]")
DATA_DIRS: list[str] = json.loads(OC_DATA_DIRS_RAW)
VOLUME_MOUNT = "/mnt/oc-data"
OC_OUT_DIR_RAW = os.environ["OC_OUT_DIR"]
OUT_DIR = Path(OC_OUT_DIR_RAW)
OC_LOG_PATH_RAW = os.environ["OC_LOG_PATH"]
LOG_PATH = Path(OC_LOG_PATH_RAW)
OC_SHARD_COMMANDS_RAW = os.environ["OC_SHARD_COMMANDS"]
SHARD_COMMANDS: list[dict[str, object]] = json.loads(OC_SHARD_COMMANDS_RAW)

app = modal.App(f"oc-{JOB}")

_oc_env = {
    "OC_JOB": JOB,
    "OC_CPU": os.environ["OC_CPU"],
    "OC_MEMORY_GIB": os.environ["OC_MEMORY_GIB"],
    "OC_TIMEOUT_MIN": os.environ["OC_TIMEOUT_MIN"],
    "OC_GPU": os.environ.get("OC_GPU", ""),
    "OC_STAGE_DIR": STAGE_DIR,
    "OC_THREADS": str(THREADS),
    "OC_DATA_DIRS": OC_DATA_DIRS_RAW,
    "OC_OUT_DIR": OC_OUT_DIR_RAW,
    "OC_LOG_PATH": OC_LOG_PATH_RAW,
    "OC_SHARD_COMMANDS": OC_SHARD_COMMANDS_RAW,
    "POLARS_MAX_THREADS": str(THREADS),
    "OMP_NUM_THREADS": str(THREADS),
    "MKL_NUM_THREADS": str(THREADS),
    "OPENBLAS_NUM_THREADS": str(THREADS),
    "NUMEXPR_MAX_THREADS": str(THREADS),
    "OC_NUM_THREADS": str(THREADS),
    "POLARS_SKIP_CPU_CHECK": "1",
    # `--no-install-project` (below) means `open_composer` is never installed
    # into site-packages (editable or otherwise) -- it only ever exists as
    # the plain directory added by `add_local_dir`. PYTHONPATH makes
    # `import open_composer...` resolve against that directory instead.
    "PYTHONPATH": "/root/repo",
    # The venv was already built at image-build time (see below); this stops
    # `uv run` from re-checking/re-syncing (and re-hitting the same
    # editable-install issue) on every invocation at container run time.
    "UV_NO_SYNC": "1",
}

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("uv")
    # These two files are added individually, before the expensive sync, so
    # this layer's cache key is exactly `uv.lock` + `pyproject.toml` content
    # -- it only rebuilds when the lockfile changes, regardless of how often
    # the rest of the repo's code changes.
    .add_local_file(f"{STAGE_DIR}/pyproject.toml", "/root/repo/pyproject.toml", copy=True)
    .add_local_file(f"{STAGE_DIR}/uv.lock", "/root/repo/uv.lock", copy=True)
    # `--no-install-package longbridge`: that broker SDK only ships wheels for
    # a newer glibc (manylinux_2_39+) than Modal's debian_slim base currently
    # provides (manylinux_2_36); nothing this runner executes imports it, so
    # it is skipped rather than failing every job. `--no-install-project`:
    # this early layer only has pyproject.toml/uv.lock (no source tree yet,
    # see below), so hatchling can't build an editable `open_composer` wheel
    # here anyway -- the real source is added afterwards and reached via
    # `PYTHONPATH` instead (see `_oc_env`). Everything else in the frozen
    # lock (third-party dependencies) installs as-is.
    .run_commands(
        "cd /root/repo && uv sync --frozen --no-dev "
        "--no-install-package longbridge --no-install-project"
    )
    # The full allowlisted code tree, added last so code-only changes never
    # invalidate the dependency-install layer above.
    .add_local_dir(STAGE_DIR, "/root/repo", copy=True)
)

volumes: dict[str, modal.Volume] = {}
if DATA_DIRS:
    volumes[VOLUME_MOUNT] = modal.Volume.from_name("oc-data", create_if_missing=True)

# Shard outputs travel through a volume, not through the function's return value:
# returned tarballs were buffered by the local `modal run` client (several shards at
# once, whatever order we consumed them in) and pushed it to 1.9 GB on 2026-10-07,
# then past its 1 GB cap four times (docs/runbook-memory.zh.md). Each shard writes
# its tarball to OUT_MOUNT and commits; the client streams it to a local temp file,
# extracts it and deletes the remote copy. RUN_ID is the log file stem
# (modal-<job>-<stamp>), identical locally and in the container.
OUT_MOUNT = "/mnt/oc-out"
RUN_ID = Path(OC_LOG_PATH_RAW).stem
out_volume = modal.Volume.from_name("oc-out", create_if_missing=True)
volumes[OUT_MOUNT] = out_volume


@app.function(
    image=image,
    cpu=CPU,
    memory=int(MEMORY_GIB * 1024),
    timeout=int(TIMEOUT_MIN * 60),
    gpu=GPU,
    volumes=volumes,
    env=_oc_env,
)
def run_shard(argv: list[str], out_rel: str, index: int = 0) -> dict[str, object]:
    import subprocess

    os.chdir("/root/repo")
    # Mirror each synced `--data` path back onto the repo layout the target
    # script expects, so its own relative paths resolve unchanged.
    for rel in DATA_DIRS:
        link_path = Path("/root/repo") / rel
        if link_path.exists() or link_path.is_symlink():
            continue
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(f"{VOLUME_MOUNT}/{rel}")

    # Stream the command's output live (Modal forwards container stdout to the
    # local `modal run` driver log), so a timeout still shows how far the job
    # got; keep only the tail for the returned summary.
    t0 = time.time()
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[{time.time() - t0:7.1f}s] {line}", end="", flush=True)
        tail.append(line)
        if len(tail) > 400:
            del tail[:200]
    proc.wait()
    wall = time.time() - t0
    out_path = Path("/root/repo") / out_rel
    out_remote = ""
    if out_path.exists():
        out_remote = f"{RUN_ID}/shard_{index}.tar.gz"
        target = Path(OUT_MOUNT) / out_remote
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(target, mode="w:gz", dereference=True) as tf:
            tf.add(out_path, arcname=".")
        out_volume.commit()
    return {
        "index": index,
        "returncode": proc.returncode,
        "stdout": "".join(tail)[-20000:],
        "stderr": "",
        "wall_seconds": wall,
        "out_remote": out_remote,
    }


@app.local_entrypoint()
def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Take each shard's result as soon as it finishes (completion order) and drop
    # its output tarball after extracting it. Collecting them all first held every
    # shard's output in this local process at once: 1.9 GB on 2026-10-07
    # (t21-features, 4 shards); shard order still buffered finished shards behind a
    # slow one, and the driver hit its 1 GB cap. The owner keeps 500 MB free
    # (docs/runbook-memory.zh.md), so the local driver must stay small.
    inputs = [(sc["argv"], sc["out_rel"], i) for i, sc in enumerate(SHARD_COMMANDS)]
    results = run_shard.starmap(inputs, order_outputs=False)
    single = len(SHARD_COMMANDS) == 1
    summary = []
    with LOG_PATH.open("w", encoding="utf-8") as logf:
        for r in results:
            i = int(r["index"])
            logf.write(
                f"=== shard {i} argv={SHARD_COMMANDS[i]['argv']} "
                f"returncode={r['returncode']} wall={r['wall_seconds']:.1f}s ===\n"
            )
            logf.write(str(r["stdout"]))
            logf.write(str(r["stderr"]))
            logf.write("\n")
            dest = OUT_DIR if single else OUT_DIR / f"shard_{i}"
            dest.mkdir(parents=True, exist_ok=True)
            remote = str(r.get("out_remote") or "")
            if remote:
                with tempfile.TemporaryFile() as tmp:
                    out_volume.read_file_into_fileobj(remote, tmp)
                    tmp.seek(0)
                    with tarfile.open(fileobj=tmp, mode="r:gz") as tf:
                        tf.extractall(dest, filter="data")  # noqa: S202 -- our own container output
                try:
                    out_volume.remove_file(remote)
                except Exception as exc:  # cleanup only; the result is already local
                    logf.write(f"(could not delete remote {remote}: {exc!r})\n")
            summary.append(
                {
                    "shard": i,
                    "returncode": r["returncode"],
                    "wall_seconds": r["wall_seconds"],
                    "out": str(dest),
                }
            )
            logf.flush()
    summary.sort(key=lambda row: row["shard"])
    try:
        out_volume.remove_file(RUN_ID, recursive=True)
    except Exception:  # noqa: S110 -- already empty or never created
        pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "_modal_shards.json").write_text(json.dumps(summary, indent=2))
    print("OC_MODAL_SUMMARY_JSON:" + json.dumps(summary))
