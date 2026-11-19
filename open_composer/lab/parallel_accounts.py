"""Ordered independent account groups. Each child runs in a capped Windows Job."""
import os
import pickle
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from joblib.externals import cloudpickle

from open_composer.research.platform_runtime import capped_process

ROOT = Path(__file__).resolve().parents[2]


def parallel_map(function, values):
    values = list(values)
    workers = min(5, len(values))
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        with (directory / "function").open("wb") as stream:
            pickle.dump(sys.path, stream)
            cloudpickle.dump(function, stream)

        def execute(i):
            chunk = values[i * len(values) // workers:(i + 1) * len(values) // workers]
            path = directory / str(i)
            with path.open("wb") as stream:
                cloudpickle.dump(chunk, stream)
            command = [sys.executable, "-m", "open_composer.lab.parallel_accounts", str(path)]
            env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
            with capped_process(command, root=ROOT, mem="900M", env=env) as process:
                if process.wait():
                    raise RuntimeError(f"Account group {i} exited with {process.returncode}")
            return path

        with ThreadPoolExecutor(workers) as pool:
            for path in pool.map(execute, range(workers)):
                with path.with_suffix(".out").open("rb") as stream:
                    yield from pickle.load(stream)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    # Load the registered modules from this batch's private staging directory.
    with (path.parent / "function").open("rb") as stream:
        sys.path[:] = pickle.load(stream)
        function = pickle.load(stream)
    with path.open("rb") as stream:
        values = pickle.load(stream)
    with path.with_suffix(".out").open("wb") as stream:
        pickle.dump([function(value) for value in values], stream, protocol=5)
