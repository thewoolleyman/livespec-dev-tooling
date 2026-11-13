"""Static import resolution for the flake-retry plugin's closure analysis.

The plugin decides whether a failing test may be retried by reading the
test's import closure without executing it. These helpers resolve one
module's in-repository imports and a test's `conftest.py` chain; the
plugin parses each module once and memoises what these return.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

__all__: list[str] = ["conftest_chain", "from_import_sources", "module_imports"]


def _module_path(*, repo_root: Path, module: str) -> Path | None:
    """Resolve an in-repository dotted module without importing user code."""
    stem = Path(*module.split("."))
    for candidate in (repo_root / stem.with_suffix(".py"), repo_root / stem / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _from_module(*, node: ast.ImportFrom, package: tuple[str, ...]) -> str:
    """The dotted module a `from` import reads, with relative levels resolved."""
    prefix = package[: max(0, len(package) - node.level + 1)] if node.level else ()
    return ".".join((*prefix, *(node.module or "").split("."))).strip(".")


def _plugin_modules(*, tree: ast.AST) -> list[str]:
    """The modules a module-level `pytest_plugins` assignment names."""
    body = tree.body if isinstance(tree, ast.Module) else []
    named: list[str] = []
    for node in body:
        if not isinstance(node, ast.Assign) or not any(
            getattr(target, "id", "") == "pytest_plugins" for target in node.targets
        ):
            continue
        value = node.value
        elements = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
        named.extend(
            element.value
            for element in elements
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        )
    return named


def module_imports(*, tree: ast.AST, path: Path, repo_root: Path) -> set[Path]:
    """Resolve direct static imports, and `pytest_plugins` modules, in one module conservatively."""
    found: set[Path] = set()
    package = path.relative_to(repo_root).parent.parts
    modules = list(_plugin_modules(tree=tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _from_module(node=node, package=package)
            modules.append(module)
            modules.extend(".".join((module, alias.name)).strip(".") for alias in node.names)
    for module in modules:
        candidate = _module_path(repo_root=repo_root, module=module) if module else None
        if candidate is not None:
            found.add(candidate)
    return found


def from_import_sources(*, nodes: Iterable[ast.AST], path: Path, repo_root: Path) -> dict[int, str]:
    """Map each name a `from` import reads out of an in-repository module to that module."""
    sources: dict[int, str] = {}
    package = path.relative_to(repo_root).parent.parts
    for node in nodes:
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _from_module(node=node, package=package)
        source = _module_path(repo_root=repo_root, module=module) if module else None
        if source is None:
            continue
        for alias in node.names:
            submodule = _module_path(repo_root=repo_root, module=f"{module}.{alias.name}")
            if submodule is None:
                sources[id(alias)] = str(source)
    return sources


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
