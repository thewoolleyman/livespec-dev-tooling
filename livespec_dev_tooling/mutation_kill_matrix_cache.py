"""The Rule-26 kill matrix's result cache: reuse an outcome only when nothing it rests on moved.

A cached outcome is keyed by everything re-testing its mutant could depend on:

- the engine, mutmut, Python and dependency versions, the per-test timeout and
  the target's settings files (`pyproject.toml`, lock files and the like);
- every non-Python file of the tree, every `conftest.py` and settings file, and
  every code unit executed outside any test (at import or collection time), as
  one digest, because a test may read any data file and nothing measures which
  one, and import-time code reaches every test without a coverage context;
- the mutant's identifier and its function's text;
- the tests selected for it, each with a digest of the code its coverage
  context executed: the text of every function holding an executed line, and
  the module-level text of every file it touched.

When the code a mutant's tests depend on is not fully measured (no per-test
coverage, an unlocatable function, a body executed outside any test, or a
selected test with no coverage context), the whole of the tree's Python
source stands in for that last part.  A key that matches therefore names a
re-test whose inputs are byte-identical, and anything else is re-tested.
"""

from __future__ import annotations

import ast
import hashlib
import json
import platform
from collections import defaultdict
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import cast

from livespec_dev_tooling.mutation_kill_matrix_execution import CommandExecutor
from livespec_dev_tooling.mutation_kill_matrix_selection import (
    MutantSpan,
    PerTestCoverage,
    text_digest,
)

__all__: list[str] = [
    "CACHE_SCHEMA",
    "CacheKeys",
    "CachedOutcome",
    "load_cache",
    "save_cache",
    "tree_files",
]


CACHE_SCHEMA = "rule-26-kill-matrix-cache/1"
_SETTINGS_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "pytest.ini",
        "tox.ini",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        ".python-version",
    }
)
_SKIPPED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        ".mutmut-cache",
    }
)
_SKIPPED_AT_ROOT = frozenset({"mutants", "reports"})
_OUTSIDE_ANY_TEST = ""


@dataclass(frozen=True, kw_only=True)
class CachedOutcome:
    """One mutant's reusable outcome: unapplied, or the tests that killed it."""

    unapplied: bool
    killed_by: tuple[str, ...]


def _kept(*, relative: Path) -> bool:
    """Whether a target-relative path is an input rather than a cache or an output."""
    parts = relative.parts
    if not parts or _SKIPPED_PARTS.intersection(parts) or parts[0] in _SKIPPED_AT_ROOT:
        return False
    return not (relative.suffix == ".pyc" or relative.name.startswith(".coverage"))


def tree_files(*, target: Path, execute: CommandExecutor) -> list[Path]:
    """List the target's input files: git's tracked and unignored files when it is a checkout."""
    listed = execute(
        args=["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=target
    )
    if listed.returncode == 0:
        candidates = [Path(name) for name in listed.stdout.split("\0") if name]
    else:
        candidates = [path.relative_to(target) for path in target.rglob("*") if path.is_file()]
    return sorted(
        relative
        for relative in candidates
        if _kept(relative=relative) and (target / relative).is_file()
    )


def _digest(*parts: str) -> str:
    """Digest an ordered sequence of strings without ambiguity between them."""
    return hashlib.sha256(json.dumps(list(parts)).encode("utf-8")).hexdigest()


def _file_digest(*, path: Path) -> str:
    """Digest one file's bytes, so a binary data file is covered as well as a text one."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environmental(*, relative: Path) -> bool:
    """Whether a file can reach every test: data, settings, or a pytest `conftest.py`."""
    return (
        relative.suffix != ".py"
        or relative.name == "conftest.py"
        or relative.name in _SETTINGS_NAMES
        or relative.name.startswith("requirements")
    )


def _import_time_units(
    *, coverage: PerTestCoverage | None, units: dict[str, _FileUnits]
) -> list[str]:
    """Name every code unit executed outside any test, which every test inherits."""
    if coverage is None:
        return []
    return sorted(
        {
            f"{path}:{units[path].unit(line=line)}"
            for path, lines in coverage.items()
            if path in units
            for line, tests in lines.items()
            if _OUTSIDE_ANY_TEST in tests
        }
    )


def _dependency_set() -> list[str]:
    """Name every distribution the engine's interpreter, and so every test, can import."""
    return sorted({f"{dist.metadata['Name']}=={dist.version}" for dist in metadata.distributions()})


@dataclass(frozen=True, kw_only=True)
class _Function:
    """One function's line span, with digests of its whole text and of its header."""

    first: int
    body_first: int
    last: int
    digest: str
    header: str


def _function_unit(
    *, text: str, lines: list[str], node: ast.FunctionDef | ast.AsyncFunctionDef
) -> _Function:
    """Describe one function: its decorators and signature form its header."""
    first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    body_first = node.body[0].lineno
    return _Function(
        first=first,
        body_first=body_first,
        last=node.end_lineno or node.lineno,
        digest=text_digest(text=ast.get_source_segment(text, node) or ""),
        header=text_digest(text="\n".join(lines[first - 1 : max(first, body_first - 1)])),
    )


class _FileUnits:
    """Map a Python file's lines to the digest of the code unit holding each one.

    A line in a function's body belongs to that (innermost) function.  A line of
    a function's header (its decorators and `def` line, which run when the
    function is DEFINED rather than called) belongs to the header alone, so an
    edited body does not move what import-time execution depends on.  Every
    other line belongs to the module-level text.
    """

    def __init__(self, *, text: str) -> None:
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            self.functions: list[_Function] = []
            self.module = text_digest(text=text)
            return
        self.functions = sorted(
            (
                _function_unit(text=text, lines=lines, node=node)
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            ),
            key=lambda function: function.last - function.first,
        )
        inside = {
            line for function in self.functions for line in range(function.first, function.last + 1)
        }
        self.module = text_digest(
            text="\n".join(
                line for number, line in enumerate(lines, start=1) if number not in inside
            )
        )

    def unit(self, *, line: int) -> str:
        """Return the unit holding `line`: a function body, a function header, or the module."""
        for function in self.functions:
            if function.first <= line <= function.last:
                return function.header if line < function.body_first else function.digest
        return self.module


class CacheKeys:
    """Compute each mutant's cache key from one snapshot of the target."""

    def __init__(
        self,
        *,
        target: Path,
        coverage: PerTestCoverage | None,
        engine_version: str,
        timeout: float,
        execute: CommandExecutor,
    ) -> None:
        files = tree_files(target=target, execute=execute)
        python_files = [relative for relative in files if relative.suffix == ".py"]
        texts = {
            relative.as_posix(): (target / relative).read_text(encoding="utf-8", errors="replace")
            for relative in python_files
        }
        self._whole_code = _digest(
            *(f"{name}:{text_digest(text=text)}" for name, text in sorted(texts.items()))
        )
        units = {name: _FileUnits(text=text) for name, text in texts.items()}
        self._environment = _digest(
            CACHE_SCHEMA,
            engine_version,
            platform.python_version(),
            repr(timeout),
            *_dependency_set(),
            *(
                f"{relative.as_posix()}:{_file_digest(path=target / relative)}"
                for relative in files
                if _environmental(relative=relative)
            ),
            *_import_time_units(coverage=coverage, units=units),
        )
        self._test_code = self._per_test_code(coverage=coverage, units=units)

    @staticmethod
    def _per_test_code(
        *, coverage: PerTestCoverage | None, units: dict[str, _FileUnits]
    ) -> dict[str, str]:
        """Digest, per test, the code units its coverage context executed."""
        if coverage is None:
            return {}
        found_units: dict[str, set[str]] = defaultdict(set)
        for path, lines in coverage.items():
            file_units = units.get(path)
            if file_units is None:
                continue
            for line, tests in lines.items():
                unit = f"{path}:{file_units.unit(line=line)}"
                module = f"{path}:{file_units.module}"
                for test in tests - {_OUTSIDE_ANY_TEST}:
                    found_units[test].add(unit)
                    found_units[test].add(module)
        return {test: _digest(*sorted(found)) for test, found in found_units.items()}

    def key(self, *, identifier: str, span: MutantSpan | None, selected: list[str]) -> str:
        """Return one mutant's key, standing the whole source in for code it cannot attribute."""
        code = (
            [f"{test}:{self._test_code[test]}" for test in sorted(selected)]
            if span is not None and all(test in self._test_code for test in selected)
            else ["whole-code", self._whole_code, *sorted(selected)]
        )
        return _digest(
            self._environment,
            identifier,
            span.function_digest or "" if span is not None else "",
            *code,
        )


def load_cache(*, path: Path | None) -> dict[str, CachedOutcome] | None:
    """Load a cache, or None when there is none, it is unreadable, or its schema is foreign."""
    if path is None or not path.is_file():
        return None
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict):
        return None
    document = cast("dict[str, object]", loaded)
    if document.get("schema") != CACHE_SCHEMA:
        return None
    entries = cast("dict[str, dict[str, object]]", document.get("entries", {}))
    return {
        key: CachedOutcome(
            unapplied=bool(entry.get("unapplied", False)),
            killed_by=tuple(str(test) for test in cast("list[object]", entry.get("killed_by", []))),
        )
        for key, entry in entries.items()
    }


def save_cache(*, path: Path, entries: dict[str, CachedOutcome]) -> None:
    """Write the cache holding exactly this run's outcomes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": CACHE_SCHEMA,
        "entries": {
            key: {"unapplied": outcome.unapplied, "killed_by": list(outcome.killed_by)}
            for key, outcome in sorted(entries.items())
        },
    }
    _ = path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
