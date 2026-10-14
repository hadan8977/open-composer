"""Read scalar native cursor metadata without torch, unpickling or tensor/model loads."""

import argparse
import hashlib
import json
import math
import pickletools
import re
import zipfile
from pathlib import Path

SCALAR_KEYS = {
    "schema_version",
    "plan_sha256",
    "fit_id",
    "input_manifest_sha256",
    "epoch_next",
    "batch_next",
    "optimizer_updates_completed",
    "CPU_seconds_cumulative",
    "role",
}
STRING_OPS = {"UNICODE", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8"}
SCALAR_OPS = STRING_OPS | {
    "INT",
    "BININT",
    "BININT1",
    "BININT2",
    "LONG",
    "LONG1",
    "LONG4",
    "FLOAT",
    "BINFLOAT",
}
MEMO_OPS = {"BINPUT", "LONG_BINPUT", "PUT", "MEMOIZE"}


def inspect(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("one bounded actual checkpoint file only")
    with zipfile.ZipFile(path) as archive:
        rows = [x for x in archive.infolist() if x.filename.endswith("/data.pkl")]
        if len(rows) != 1 or rows[0].file_size > 1024 * 1024:
            raise ValueError("one<=1MiB native pickle metadata member required")
        operations = list(pickletools.genops(archive.read(rows[0])))
        members = len(archive.infolist())
    values = {}
    for index, (opcode, argument, _) in enumerate(operations):
        if opcode.name not in STRING_OPS or argument not in SCALAR_KEYS:
            continue
        if argument in values:
            raise ValueError("ambiguous scalar key in checkpoint")
        successor = index + 1
        while operations[successor][0].name in MEMO_OPS:
            successor += 1
        value_opcode, value, _ = operations[successor]
        if value_opcode.name not in SCALAR_OPS:
            raise ValueError("metadata is not a directly encoded scalar: " + argument)
        values[argument] = value
    if set(values) != SCALAR_KEYS:
        raise ValueError("native scalar metadata incomplete")
    if (
        values["schema_version"] != 1
        or values["plan_sha256"]
        != ("65779a75814f4ac09a9f68baa009dd5c0595f9cab9ee745dab46b34c8197bf6d")
        or not re.fullmatch(r"A(?:05|06|07|08|09|10)-fold10", values["fit_id"])
    ):
        raise ValueError("original method/sixfit checkpoint identity mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", values["input_manifest_sha256"]):
        raise ValueError("actual input manifest SHA required")
    epoch, batch, updates = (
        values[k] for k in ("epoch_next", "batch_next", "optimizer_updates_completed")
    )
    if (
        any(type(x) is not int for x in (epoch, batch, updates))
        or not 0 <= epoch <= 100
        or not (0 <= batch < 8)
        or updates != epoch * 8 + batch
        or updates > 800
    ):
        raise ValueError("invalid original800wholebatch next cursor")
    if not math.isfinite(values["CPU_seconds_cumulative"]) or values["CPU_seconds_cumulative"] < 0:
        raise ValueError("finite nonnegative cumulative fit CPU required")
    if values["role"] != "public_anonymous_method_only":
        raise ValueError("wrong method role")
    names = {x[1] for x in operations if x[0].name in STRING_OPS}
    required_names = {
        "model_state_dict",
        "optimizer_state_dict",
        "rng_state",
        "torch_cpu",
        "torch_cuda",
        "python",
        "previous_epoch_samebatch_normalized_residual_bank",
    }
    if not required_names.issubset(names):
        raise ValueError("required native state names absent")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "native_scalars": values,
        "required_state_names_present": True,
        "zip_members": members,
        "pickle_executed": False,
        "torch_or_model_or_tensor_values_loaded": False,
        "state_tensor_contents_or_resume_equivalence_verified": False,
        "complete_fit_at_saved_cursor": updates == 800,
        "old_job_termination_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.checkpoint), indent=2))


if __name__ == "__main__":
    main()
