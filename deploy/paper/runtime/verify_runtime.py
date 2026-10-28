"""Read-only verification of the two existing paper interpreters and frozen source."""

import argparse
import ast
import hashlib
import importlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path


def verify(root, environment):
    root = Path(root)
    manifest = json.loads((root / "deploy/paper/runtime/environment.json").read_text())
    expected = manifest["environments"][environment]
    errors = []
    if Path(sys.executable).absolute() != Path(expected["executable"]):
        errors.append("interpreter path differs")
    if platform.python_version() != expected["python"]:
        errors.append("Python version differs")
    if (
        hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        != expected["executable_sha256"]
    ):
        errors.append("interpreter binary differs")
    for name, version in expected["packages"].items():
        try:
            if importlib.metadata.version(name) != version:
                errors.append("package version differs: " + name)
        except importlib.metadata.PackageNotFoundError:
            errors.append("package missing: " + name)
    readers = []
    for module, distribution in expected.get("numeric_readers", {}).items():
        if distribution not in expected["packages"]:
            errors.append("numeric reader is not version pinned: " + module)
            continue
        try:
            # Import the local reader implementation without reading a dataset,
            # loading a model, or constructing a network/broker client.
            importlib.import_module(module)
            readers.append(module)
        except Exception as error:
            errors.append(
                "numeric reader unavailable: " + module + " (" + type(error).__name__ + ")"
            )
    if environment == "inference":
        try:
            path = Path(importlib.metadata.distribution("torch").locate_file("torch/version.py"))
            actual = {}
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    actual[node.targets[0].id] = ast.literal_eval(node.value)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    actual[node.target.id] = ast.literal_eval(node.value)
            if any(actual.get(k) != v for k, v in expected["torch_build"].items()):
                errors.append("Torch build differs")
        except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
            errors.append("Torch build metadata unavailable")
    else:
        package = root / "open_composer/paper_runtime"
        for row in json.loads((package / "source-manifest.json").read_text())["files"]:
            body = (package / row["package_path"]).read_bytes()
            if len(body) != row["bytes"] or hashlib.sha256(body).hexdigest() != row["sha256"]:
                errors.append("frozen source differs: " + row["package_path"])
    return dict(
        environment=environment,
        verified=not errors,
        errors=errors,
        numeric_readers_verified=readers,
        broker_calls=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--environment", choices=("service", "inference"), required=True)
    args = parser.parse_args()
    result = verify(args.root, args.environment)
    print(json.dumps(result))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
