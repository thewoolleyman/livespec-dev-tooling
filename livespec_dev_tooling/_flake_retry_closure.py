"""Static import resolution for the flake-retry plugin's closure analysis.

The plugin decides whether a failing test may be retried by reading the
test's import closure without executing it. These helpers resolve one
module's in-repository imports and a test's `conftest.py` chain; the
plugin parses each module once and memoises what these return.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = ["conftest_chain", "module_imports"]


def _module_path(*, repo_root: Path, module: str) -> Path | None:
    """Resolve an in-repository dotted module without importing user code."""
    stem = Path(*module.split("."))
    for candidate in (repo_root / stem.with_suffix(".py"), repo_root / stem / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def module_imports(*, tree: ast.AST, path: Path, repo_root: Path) -> set[Path]:
    """Resolve direct static imports in one source module conservatively."""
    found: set[Path] = set()
    package = path.relative_to(repo_root).parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidate = _module_path(repo_root=repo_root, module=alias.name)
                if candidate is not None:
                    found.add(candidate)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: max(0, len(package) - node.level + 1)] if node.level else ()
            module = ".".join((*prefix, *(node.module or "").split("."))).strip(".")
            if module:
                candidate = _module_path(repo_root=repo_root, module=module)
                if candidate is not None:
                    found.add(candidate)
            for alias in node.names:
                candidate = _module_path(
                    repo_root=repo_root, module=".".join((module, alias.name)).strip(".")
                )
                if candidate is not None:
                    found.add(candidate)
    return found


def conftest_chain(*, repo_root: Path, test_path: Path) -> list[Path]:
    """Every `conftest.py` from the test's directory up to the repository root."""
    chain: list[Path] = []
    current = test_path.parent
    while True:
        conftest = current / "conftest.py"
        if conftest.is_file():
            chain.append(conftest)
        if current in (repo_root, current.parent):
            return chain
        current = current.parent
