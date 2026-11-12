"""Refuse consumer reaches outside an installed dev-tooling public surface."""

from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._import_resolution import (  # noqa: E402
    attribute_reaches,
    module_aliases,
    module_name,
    name_imports,
    suffix_index,
    top_level_functions,
)
from livespec_dev_tooling.checks._public_api_consumption import (  # noqa: E402
    repo_local_public_names,
)
from livespec_dev_tooling.config import load_config, resolve_repo_root  # noqa: E402
from livespec_dev_tooling.fleet._member_sources import read_member_sources  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__: list[str] = []


_DECLARATIONS = "data/cross_repo_public_api.json"
_FAIL_VARIABLE = "LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS"


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One consumer reach not covered by the installed public surface."""

    source: Path
    line: int
    definition: Path
    function: str


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("dev_tooling_imports_declared")


def _installed_sources() -> dict[Path, str]:
    """Read installed package sources without importing a consumer module."""
    package = Path(__file__).resolve().parent.parent
    root = package.parent
    return {
        path.relative_to(root): path.read_text(encoding="utf-8")
        for path in sorted(package.rglob("*.py"))
        if "_vendor" not in path.relative_to(root).parts
    }


def _declared_api() -> frozenset[tuple[Path, str]]:
    """Return the declarations shipped beside this installed package."""
    path = Path(__file__).resolve().parent.parent / _DECLARATIONS
    rows = cast("list[object]", json.loads(path.read_text(encoding="utf-8")))
    return frozenset(
        (
            Path(cast("dict[str, str]", row)["file"]),
            cast("dict[str, str]", row)["function"],
        )
        for row in rows
    )


def _source_reaches(
    *, tree: ast.Module, current: str, index: Mapping[str, frozenset[Path]]
) -> tuple[tuple[int, str, str], ...]:
    """Resolve direct and module-attribute reaches using the fleet resolver."""
    aliases = module_aliases(tree=tree, current=current, index=index)
    imported = name_imports(tree=tree, current=current, index=index)
    attributed = attribute_reaches(tree=tree, aliases=aliases, index=index)
    reaches: set[tuple[int, str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            for alias in node.names:
                if (node.module, alias.name) in imported:
                    reaches.add((node.lineno, node.module, alias.name))
        elif isinstance(node, ast.Attribute):
            target = aliases.get(ast.unparse(node.value))
            if target is not None and (target, node.attr) in attributed:
                reaches.add((node.lineno, target, node.attr))
    return tuple(sorted(reaches))


def _findings(*, consumer_sources: Mapping[Path, str]) -> tuple[_Finding, ...]:
    """Find consumer imports neither declared nor locally public in the package."""
    installed = _installed_sources()
    index = suffix_index(sources=installed)
    functions = {
        path: top_level_functions(tree=ast.parse(source)) for path, source in installed.items()
    }
    declared = _declared_api()
    locally_public = repo_local_public_names(sources=installed)
    findings: set[_Finding] = set()
    for source, text in consumer_sources.items():
        tree = ast.parse(text)
        for line, dotted, function in _source_reaches(
            tree=tree, current=module_name(rel=source), index=index
        ):
            if function.startswith("_"):
                continue
            for definition in index[dotted]:
                reach = (definition, function)
                if function in functions[definition] and reach not in declared | locally_public:
                    findings.add(
                        _Finding(
                            source=source,
                            line=line,
                            definition=definition,
                            function=function,
                        )
                    )
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.source.as_posix(),
                finding.line,
                finding.definition.as_posix(),
                finding.function,
            ),
        )
    )


def main() -> int:
    """Report undeclared imports and optionally refuse the consumer check."""
    root = resolve_repo_root()
    consumer = unsafe_perform_io(
        read_member_sources(root=root, config=load_config(repo_root=root)).unwrap()
    )
    findings = _findings(consumer_sources=consumer.consuming)
    fail = _FAIL_VARIABLE in os.environ
    log = _configure_logger()
    for finding in findings:
        emit = log.error if fail else log.warning
        emit(
            "undeclared livespec_dev_tooling function import",
            check_id="dev-tooling-imports-declared",
            source=finding.source.as_posix(),
            line=finding.line,
            definition=finding.definition.as_posix(),
            function=finding.function,
        )
    return 4 if findings and fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
