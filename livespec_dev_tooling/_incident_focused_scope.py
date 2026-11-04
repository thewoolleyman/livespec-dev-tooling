"""Validate cumulative incident scope and choose tracked related tests."""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

from livespec_dev_tooling._incident_focused_types import FocusedScope, Identity
from livespec_dev_tooling.config import derive_source_prefixes, is_generated, load_config

__all__: list[str] = [
    "changed_paths",
    "classify",
    "exact_tree",
    "preflight",
    "scoped_path",
    "select_tests",
]

_MAX_SECONDS = 60


def _git(*, root: Path, args: tuple[str, ...]) -> str:
    return subprocess.run(  # noqa: S603 — fixed git executable; argv is never shell evaluated.
        ["git", *args],  # noqa: S607 — use the configured git on PATH.
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def scoped_path(*, root: Path, name: str) -> Path | None:
    candidate = root / name
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        return None
    return candidate if candidate.resolve().is_relative_to(root.resolve()) else None


def classify(*, path: Path, name: str, source_prefixes: tuple[str, ...]) -> str:
    if not path.exists():
        return "deleted"
    if is_generated(path=path):
        return "generated"
    if path.suffix != ".py":
        executable_suffixes = {".sh", ".bash", ".rs", ".js", ".ts", ".tsx", ".c", ".cpp", ".go"}
        if path.suffix in executable_suffixes or os.access(path, os.X_OK):
            return "unsupported-executable"
        return "non-executable"
    if not name.startswith(source_prefixes):
        return "non-executable"
    nodes = ast.parse(path.read_text(encoding="utf-8")).body
    executable = [
        node
        for node in nodes
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    return "executable" if executable else "non-executable"


def _nested(*, path: Path) -> bool:
    """Conservatively refuse selected tests that launch another test aggregate."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else ""
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "pytest"
            and name == "main"
        ):
            return True
        if name not in {"run", "Popen", "call", "check_call", "check_output", "system", "main"}:
            continue
        literals = (
            child.value
            for arg in node.args
            for child in ast.walk(arg)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        )
        if any(
            word in value
            for value in literals
            for word in ("pytest", "check-per-file-coverage", "just check")
        ):
            return True
    return False


def _scope_reason(*, repo_root: Path, scope: FocusedScope) -> str:
    config = load_config(repo_root=repo_root)
    canonical = derive_source_prefixes(config=config)
    if not canonical or set(scope.source_prefixes) != set(canonical):
        return "source prefixes must match the repository's configured source scope"
    if not scope.test_prefixes or any(not prefix.strip("/") for prefix in scope.test_prefixes):
        return "explicit test prefixes required"
    if set(scope.test_prefixes) != {config.tests_tree_prefix}:
        return "test prefixes must match the repository's configured test scope"
    return ""


def preflight(*, repo_root: Path, identity: Identity, scope: FocusedScope) -> str:
    reason = _scope_reason(repo_root=repo_root, scope=scope)
    if reason:
        return reason
    if not 0 < scope.timeout < _MAX_SECONDS:
        return "timeout must be below sixty seconds"
    if not exact_tree(repo_root=repo_root, identity=identity, tree_hash=scope.tree_hash):
        return "worktree differs from exact incident tree"
    untracked = _git(
        root=repo_root,
        args=("ls-files", "--others", "--exclude-standard", "-z"),
    ).split("\0")
    if any(
        name.startswith(scope.source_prefixes + scope.test_prefixes) for name in untracked if name
    ):
        return "untracked source or tests are outside the exact incident tree"
    return ""


def exact_tree(*, repo_root: Path, identity: Identity, tree_hash: str) -> bool:
    return (
        _git(root=repo_root, args=("write-tree",)) == tree_hash
        and _git(root=repo_root, args=("rev-parse", "HEAD")) == identity.head_sha
        and not _git(root=repo_root, args=("diff", "--name-only"))
    )


def changed_paths(*, repo_root: Path, identity: Identity, scope: FocusedScope) -> set[str]:
    changed = set(
        _git(
            root=repo_root,
            args=("diff", "--name-only", "-z", identity.base_sha, scope.tree_hash),
        ).split("\0")
    ) - {""}
    previous = set(
        _git(
            root=repo_root,
            args=("diff", "--name-only", "-z", identity.base_sha, identity.head_sha),
        ).split("\0")
    ) - {""}
    return changed | previous | set(scope.prior_paths)


def select_tests(
    *, repo_root: Path, paths: set[str], dispositions: dict[str, str], scope: FocusedScope
) -> set[str] | str:
    changed_tests = {
        name
        for name in paths
        if name.startswith(scope.test_prefixes)
        and Path(name).name.startswith("test_")
        and name.endswith(".py")
        and (repo_root / name).is_file()
    }
    support = {
        name
        for name in paths
        if name.startswith(scope.test_prefixes)
        and name not in changed_tests
        and dispositions[name] != "deleted"
    }
    if support and (not scope.related_tests or not scope.related_test_reason.strip()):
        return "shared test support requires related selection rationale"
    selected = changed_tests | set(scope.related_tests)
    deferred = dict(scope.deferred_tests)
    if any(name not in selected or not reason.strip() for name, reason in deferred.items()):
        return "invalid deferred test disposition"
    selected -= deferred.keys()
    if not selected or any(not (repo_root / name).is_file() for name in selected):
        return "explicit existing tests required"
    tracked = set(
        _git(
            root=repo_root,
            args=("ls-files", "-z"),
        ).split("\0")
    )
    if not selected <= tracked:
        return "selected tests must belong to the exact tracked tree"
    helpers = {
        name
        for name in tracked
        if name.startswith(scope.test_prefixes)
        and name.endswith(".py")
        and not Path(name).name.startswith("test_")
        and (repo_root / name).is_file()
    }
    if any(_nested(path=repo_root / name) for name in selected | helpers):
        return "nested suite launcher requires explicit deferral"
    return selected
