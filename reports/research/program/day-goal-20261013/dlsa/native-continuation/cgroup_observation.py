"""Small read-only startup observation for a future admitted native continuation."""

import json
from pathlib import Path, PurePosixPath


def observe():
    membership = Path("/proc/self/cgroup").read_text()
    self_paths = [
        line.split(":", 2)[2] for line in membership.splitlines() if line.startswith("0::")
    ]
    mounts = []
    candidates = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        if right.split()[0] != "cgroup2":
            continue
        fields = left.split()
        root, mountpoint = fields[3], fields[4]
        mounts.append({"root": root, "mountpoint": mountpoint, "filesystem": "cgroup2"})
        for self_path in self_paths:
            if ".." in PurePosixPath(self_path).parts:
                continue
            try:
                relative = PurePosixPath(self_path).relative_to(PurePosixPath(root))
            except ValueError:
                continue
            candidates.append((Path(mountpoint) / relative, "proc_membership_plus_actual_mount"))
    if not candidates:
        candidates.append((Path("/sys/fs/cgroup"), "fallback_scope_not_certified"))
    observations = []
    for directory, identity in candidates:
        metrics = {}
        errors = {}
        for name in ["memory.current", "memory.max", "memory.peak"]:
            try:
                metrics[name] = (directory / name).read_text().strip()
            except OSError as error:
                metrics[name] = None
                errors[name] = type(error).__name__
        observations.append(
            {
                "path": str(directory),
                "identity": identity,
                "metrics": metrics,
                "read_errors": errors,
            }
        )
    return {
        "proc_self_cgroup": membership,
        "actual_cgroup2_mounts": mounts,
        "observations": observations,
        "all_three_metrics_visible_with_self_identity": any(
            x["identity"] == "proc_membership_plus_actual_mount"
            and all(v is not None for v in x["metrics"].values())
            for x in observations
        ),
        "unavailable_is_not_zero_or_sdk_request": True,
        "no_parent_walk_or_resource_change": True,
    }


if __name__ == "__main__":
    print(json.dumps(observe(), indent=2))
