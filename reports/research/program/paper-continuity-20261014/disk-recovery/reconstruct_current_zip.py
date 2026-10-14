"""Offline exact restoration; no network or credential access."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = json.loads((HERE / "exact-current-zip-delta.json").read_text())
    if args.output:
        if args.output.exists():
            raise ValueError("refuse to replace an existing artifact")
        stat = os.statvfs(args.output.parent)
        if stat.f_bavail * stat.f_frsize < value["original"]["bytes"] + 512 * 1024**2:
            raise OSError("insufficient exact reconstruction headroom")
    import contextlib
    digest = hashlib.sha256()
    total = 0
    with Path(value["retained_base"]["path"]).open("rb") as base, Path(value["literals"]["path"]).open("rb") as literals, (args.output.open("xb") if args.output else contextlib.nullcontext()) as output:
        for segment in value["segments"]:
            stream = base if segment["kind"] == "base" else literals
            stream.seek(segment["offset"])
            left = segment["bytes"]
            sd = hashlib.sha256()
            while left:
                data = stream.read(min(left, 1048576))
                if not data:
                    raise ValueError("truncated retained entity")
                sd.update(data)
                digest.update(data)
                if output:
                    output.write(data)
                total += len(data)
                left -= len(data)
            assert sd.hexdigest() == segment["sha256"]
    assert total == value["original"]["bytes"] and digest.hexdigest() == value["original"]["sha256"]
    print(json.dumps({"reconstructed_bytes": total, "sha256": digest.hexdigest(), "output": str(args.output) if args.output else None}))


if __name__ == "__main__":
    main()
