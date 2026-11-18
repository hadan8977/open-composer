"""Task-local identities and strict JSON; no data/model/account work on import."""

import hashlib
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

V = Path(__file__).resolve().parent
ROOT = V.parents[3]
TASK = "SHARE-TURNOVER-INFORMATION-20261017"
STUDY = "SHARE_TURNOVER_INFORMATION_V1"
JOB = "share-turnover-information-v1-20261017"
ITER = "share_turnover_information_20261017"
OWNER = "f28170c4-1c44-491e-93ce-79c18a81e8dc"
PEER = "66ad4b54-ec62-400b-9a03-a29682cf58e6"
COHORTS = ["ORIGINAL32", "DIA28"]
POLICIES = ["BASE", "AUG", "WINNER_HIGH_T", "MOM1", "COHORT_EW"]
COSTS = [10, 20]
D = ROOT / "reports/research/program/dlsa-real-market-continuation-20261014"
TRANSFER = ROOT / "reports/research/program/return-line-replenishment-20261016"
DIA = TRANSFER / "peer-insider-cohort-transfer-20261016"


def load(path):
    return json.loads(Path(path).read_text())


def bind(path):
    path = Path(path).resolve()
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=sha)


def verify(value):
    if isinstance(value, dict) and {"path", "sha256", "bytes"} <= value.keys():
        assert bind(ROOT / value["path"]) == {k: value[k] for k in ["path", "bytes", "sha256"]}
    elif isinstance(value, dict):
        for x in value.values():
            verify(x)
    elif isinstance(value, list):
        for x in value:
            verify(x)


def clean(value):
    if type(value).__module__.startswith("numpy") and hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def save(path, value):
    path = Path(path)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(clean(value), indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
