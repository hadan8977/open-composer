"""Execute only versioned copies of accepted scientific source.

The frozen helpers identify immutable receipts using their historical __file__.
Keep that identity, while routing imports, dynamic source loads and source-text
reads through the explicit manifest. Data reads and all arithmetic remain intact.
No source outside this allowlist may execute from a research directory.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.abc
import importlib.util
import json
import sys
from pathlib import Path

from open_composer.paper_runtime.paths import repo_root

PACKAGE = Path(__file__).resolve().parent
FILES = {
    row["evidence_path"]: row
    for row in json.loads((PACKAGE / "source-manifest.json").read_text())["files"]
}


def source_path(path, *, root=None):
    """Resolve an allowlisted source and verify the exact originally accepted bytes."""
    root = repo_root() if root is None else Path(root)
    path = Path(path)
    relative = path.relative_to(root) if path.is_absolute() else path
    row = FILES[str(relative)]
    actual = PACKAGE / row["package_path"]
    body = actual.read_bytes()
    if len(body) != row["bytes"] or hashlib.sha256(body).hexdigest() != row["sha256"]:
        raise ValueError("versioned scientific source hash differs")
    return actual


def source_bytes(path, *, root=None):
    root = repo_root() if root is None else Path(root)
    path = Path(path)
    relative = path.relative_to(root) if path.is_absolute() else path
    row = FILES[str(relative)]
    body = (PACKAGE / row["package_path"]).read_bytes()
    if len(body) != row["bytes"] or hashlib.sha256(body).hexdigest() != row["sha256"]:
        raise ValueError("versioned scientific source hash differs")
    return body


def _research_source(path, root):
    path = Path(path)
    return path.suffix == ".py" and path.is_relative_to(root / "reports/research/program")


class _SourceAccess(ast.NodeTransformer):
    """Adapt source access only; preserve the accepted numerical function bodies."""

    def __init__(self, root):
        self.root = Path(root)

    def visit_Constant(self, node):
        # Two accepted helpers hard-code the installation root. Resolve that
        # deployment path consistently with their preserved evidence __file__.
        if node.value == "/root/codex-test/open-composer":
            return ast.copy_location(ast.Constant(str(self.root)), node)
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"read_bytes", "read_text"}:
            node.args.insert(0, node.func.value)
            node.func = ast.Name(id="_oc_" + node.func.attr, ctx=ast.Load())
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "spec_from_file_location"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "util"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "importlib"
        ):
            node.func = ast.Name(id="_oc_source_spec", ctx=ast.Load())
        return node


class FrozenLoader(importlib.abc.Loader):
    def __init__(self, path, root):
        self.path, self.root = Path(path), Path(root)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        body = source_bytes(self.path, root=self.root)

        def read(path, method, *args, **kwargs):
            actual = (
                source_path(path, root=self.root) if _research_source(path, self.root) else path
            )
            return getattr(actual, method)(*args, **kwargs)

        def spec(name, path, **kwargs):
            return source_spec(name, path, root=self.root, **kwargs)

        module.__file__ = str(self.path)
        module.__dict__.update(
            _oc_read_bytes=lambda p, *a, **k: read(p, "read_bytes", *a, **k),
            _oc_read_text=lambda p, *a, **k: read(p, "read_text", *a, **k),
            _oc_source_spec=spec,
        )
        tree = _SourceAccess(self.root).visit(ast.parse(body, filename=str(self.path)))
        exec(compile(ast.fix_missing_locations(tree), str(self.path), "exec"), module.__dict__)


def source_spec(name, path, *, root=None, **kwargs):
    root = repo_root() if root is None else Path(root)
    path = Path(path)
    if _research_source(path, root):
        source_path(path, root=root)  # Refuse an unversioned fallback before execution.
        return importlib.util.spec_from_loader(name, FrozenLoader(path, root), origin=str(path))
    if "/reports/research/program/" in str(path):
        raise ValueError("scientific source belongs to a different repository root")
    return importlib.util.spec_from_file_location(name, path, **kwargs)


def load_source(name, path, *, root=None):
    spec = source_spec(name, path, root=root)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root):
        self.root = Path(root)

    def find_spec(self, fullname, path=None, target=None):
        for directory in sys.path if path is None else path:
            candidate = Path(directory) / (fullname.rsplit(".", 1)[-1] + ".py")
            if _research_source(candidate, self.root):
                relative = str(candidate.relative_to(self.root))
                if relative in FILES:
                    return source_spec(fullname, candidate, root=self.root)
                if candidate.exists():
                    raise ImportError("research source is absent from the production manifest")
        return None


def install_source_imports(root=None):
    """Install once in the finite scientific child; no background work or I/O."""
    root = repo_root() if root is None else Path(root)
    if not any(isinstance(f, FrozenFinder) and f.root == root for f in sys.meta_path):
        sys.meta_path.insert(0, FrozenFinder(root))
