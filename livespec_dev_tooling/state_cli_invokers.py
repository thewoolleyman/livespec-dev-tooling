"""Find committed invokers of a state-writing CLI that omit one of its state-location flags.

A command-line entry point whose run writes host state takes each state
location only from an explicit flag and has no default for it (the
host-state isolation bullet of the testing approach in this repository's
``non-functional-requirements.md``). The refusal at the entry point protects a
caller that forgets the flag; this scan protects the committed callers, so a
systemd unit, an ansible task file or template, or a script that invokes one of
these entry points without a flag fails the repository's test suite instead of
failing, on a host, at the next timer or guard operation.

A wrapper that only forwards its arguments names no entry point and is judged
through its callers, and a ``--help`` invocation writes nothing, so neither is
reported.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["Invoker", "find_unflagged_invokers"]


@dataclass(frozen=True, kw_only=True)
class Invoker:
    """One committed invoker and the state-location flag it does not pass."""

    path: str
    line: int
    cli: str
    flag: str

    def render(self) -> str:
        """Name the invoker file, the line and the missing flag."""
        return f"{self.path}:{self.line} invokes the {self.cli} without {self.flag}"


@dataclass(frozen=True, kw_only=True)
class _StateWritingCli:
    """One entry point that writes host state, how it is named, and its location flags."""

    name: str
    marker: re.Pattern[str]
    flags: tuple[str, ...]


# The entry points the specification names: the flake-retry filer's `--state-dir`
# and the Docker engine install guard's `--state-root` and `--runtime-root`. The
# preflight writes only under the state root. `docker_engine_guard_executable` is
# the role variable that holds the guard's installed path.
_STATE_WRITING_CLIS: tuple[_StateWritingCli, ...] = (
    _StateWritingCli(
        name="flake-retry filer",
        marker=re.compile(r"livespec_dev_tooling\.flake_retry_filer\b"),
        flags=("--state-dir",),
    ),
    _StateWritingCli(
        name="docker-engine-guard",
        marker=re.compile(
            r"/usr/local/libexec/docker-engine-guard(?![\w./-])|\bdocker_engine_guard_executable\b"
        ),
        flags=("--state-root", "--runtime-root"),
    ),
    _StateWritingCli(
        name="docker-engine-guard preflight",
        marker=re.compile(r"_docker_engine_guard_preflight_cli\.py"),
        flags=("--state-root",),
    ),
)

_YAML_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})
_INVOKER_SUFFIXES: frozenset[str] = frozenset({".sh", ".service", ".timer", ".j2", ".just"}) | (
    _YAML_SUFFIXES
)
_INVOKER_NAMES: frozenset[str] = frozenset({"justfile"})
# Trees that quote an invocation without making one: prose, the specification,
# the tests (which build their own fixtures) and everything vendored or generated.
_SKIPPED_TREES: frozenset[str] = frozenset(
    {".git", ".venv", "node_modules", "_vendor", "tmp", "docs", "tests", "SPECIFICATION"}
)
# An argv entry of an ansible task, as opposed to a `- name: ...` mapping item.
_ARGV_ITEM = re.compile(r"^(\s*)-\s+(?![A-Za-z_][\w.]*:(?:\s|$))")
_HELP = re.compile(r"(?<![\w-])(?:--help|-h)(?![\w-])")


def _invoker_files(*, root: Path) -> tuple[Path, ...]:
    """Every file under ``root`` that could invoke an entry point, in a stable order."""
    files: list[Path] = []
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = sorted(name for name in subdirectories if name not in _SKIPPED_TREES)
        files.extend(
            Path(directory) / name
            for name in sorted(names)
            if Path(name).suffix in _INVOKER_SUFFIXES or name in _INVOKER_NAMES
        )
    return tuple(files)


def _shell_statements(*, lines: list[str]) -> list[tuple[int, str]]:
    """Each logical line of a script, unit or template: backslash continuations joined."""
    statements: list[tuple[int, str]] = []
    start = 0
    joined: list[str] = []
    for index, line in enumerate(lines):
        joined.append(line)
        if line.rstrip().endswith("\\"):
            continue
        if not joined[0].lstrip().startswith("#"):
            statements.append((start, "\n".join(joined)))
        start = index + 1
        joined = []
    return statements


def _yaml_statements(*, lines: list[str]) -> list[tuple[int, str]]:
    """Each argv list of an ansible file, and each inline ``argv:`` line.

    An argv list is a run of contiguous list entries at one indentation, so a
    flag counts whether it comes before or after the entry naming the entry
    point. A comment inside the run is blanked rather than dropped: it keeps
    the line numbering, and a flag named only in a comment is not passed.
    """
    statements: list[tuple[int, str]] = []
    run_start = 0
    run_indent = -1
    run: list[str] = []
    for index, line in enumerate(lines):
        if run and line.lstrip().startswith("#"):
            run.append("")
            continue
        entry = _ARGV_ITEM.match(line)
        if run and entry is not None and len(entry.group(1)) == run_indent:
            run.append(line)
            continue
        if run:
            statements.append((run_start, "\n".join(run)))
            run = []
        if entry is not None:
            run_start, run_indent, run = index, len(entry.group(1)), [line]
        elif line.lstrip().startswith("argv:"):
            statements.append((index, line))
    if run:
        statements.append((run_start, "\n".join(run)))
    return statements


def _unflagged(*, relative: str, start: int, text: str) -> list[Invoker]:
    """Every state-location flag that the entry point named in ``text`` is not given."""
    if _HELP.search(text):
        return []
    found: list[Invoker] = []
    for cli in _STATE_WRITING_CLIS:
        marker = cli.marker.search(text)
        if marker is None:
            continue
        line = start + text.count("\n", 0, marker.start()) + 1
        found.extend(
            Invoker(path=relative, line=line, cli=cli.name, flag=flag)
            for flag in cli.flags
            if re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is None
        )
    return found


def find_unflagged_invokers(*, root: Path) -> tuple[Invoker, ...]:
    """Return every invoker under ``root`` that omits a state-location flag."""
    found: list[Invoker] = []
    for path in _invoker_files(root=root):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        statements = (
            _yaml_statements(lines=lines)
            if path.suffix in _YAML_SUFFIXES
            else _shell_statements(lines=lines)
        )
        relative = path.relative_to(root).as_posix()
        for start, text in statements:
            found.extend(_unflagged(relative=relative, start=start, text=text))
    return tuple(found)
