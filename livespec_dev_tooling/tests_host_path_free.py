"""tests_host_path_free — no test under `tests/` reaches a real host path.

A test that reads, stats or writes an absolute path under `/etc`, `/var`,
`/usr`, `/opt` or `/run`, or converges an Ansible task whose destination is one,
grades the MACHINE pytest happens to run on rather than the committed tree.
Measured in this repository on 2026-10-18 (the F-az incident recorded on
work-item `livespec-dev-tooling-weuhac`): a test ran the `fabro_factory_registry`
role in `--check --diff` against the default destination
`/etc/livespec/fabro-factories.json`, so it read an install diff of all `+`
lines on a host without the file and a no-op-or-partial diff on a host with it.
Master CI and every factory sandbox stayed green while every pre-push from the
control node, which had just converged itself, failed on `assert 0 == 2` — the
worst shape, because the verdict moved with the filesystem instead of with the
code. `--check` is not the fix and neither is a comment: re-pointing the
destination is, and this check refuses the authoring mistake instead of waiting
for a host to disagree.

WHAT FAILS. A host-path string literal that reaches

- a pathlib read / stat / write method as the path it is called on
  (`read_text`, `is_file`, `stat`, `write_text`, `mkdir`, `unlink`, …) or a
  file handle's own `read` / `write`,
- one of the `open` / `os.*` / `shutil.*` path functions as an argument, or
- the DESTINATION key of a mapping the module builds — `dest`, `destination`,
  `path`, or any `<prefix>_dest` / `<prefix>_path`, which is both an Ansible
  task body's destination and the `-e` extra-var a converge overrides it with

is a finding naming the file, the line and the path. Which paths an expression
names, and the fixed-point name-following that reports a module-level constant
at the line where it is USED, are the sibling `_tests_host_path_reach`'s half.

WHAT PASSES. MENTIONING a host path is not using it. A test may hold the
documented default of a role variable in a constant and assert that the role's
`defaults/main.yml` declares it, because nothing in that reaches a filesystem —
and that assertion is worth keeping, since the override is a testing seam and
never a change to what the fleet publishes. A path derived from `tmp_path`
never matches at all; the sibling module's docstring carries that rule.

THE ONE EXEMPTION IS CONFIGURATION, NEVER A COMMENT. `ALLOW_LISTED_FIXTURES`
below is this check's own configuration: a list of FIXTURE NAMES. A test that
declares one of those fixtures as a parameter may reach host paths, because the
fixture is then the single reviewed place that reach is centralised. Nothing a
test module says about ITSELF exempts it — this check never reads comments, so a
`# noqa`, a `# host-captured` marker and a paragraph of justification all leave
both the finding and the exit status exactly as they were. Note what the two
mechanisms are for: `tmp_path` is how a path is DERIVED, the allow-list is how
host reach is PERMITTED, and declaring `tmp_path` never permits anything. The
allow-list ships EMPTY — no test in this repository needs to reach a real host
path today, and a name added to it is a deliberate edit to the check.

REPO-PRIVATE CHECK. The module lives OUTSIDE `livespec_dev_tooling/checks/` so
it stays out of the canonical (fleet-universal) slug set. This repository's
`SPECIFICATION/contracts.md`, where the shared inventory of checks is
specified, obliges every consumer of a canonical slug to wire it into `just
check` and into its CI matrix — and the host-path tests this one polices are
this repository's own Ansible role tests. Wired into this repo's justfile
`check:` aggregate (repo-private block).

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import NamedTuple

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling._tests_host_path_reach import (  # noqa: E402
    bound_names,
    named_paths,
    string_constants,
)

__all__: list[str] = []


# THE CHECK'S OWN CONFIGURATION. A test that declares one of these fixtures as a
# parameter may reach host paths; nothing else exempts one. Empty on purpose —
# see the module docstring.
ALLOW_LISTED_FIXTURES: frozenset[str] = frozenset()

_TESTS_DIR = Path("tests")

# The destination key of an Ansible task body (`dest`, `path`) and of the
# extra-var a converge re-points it with (`<role>_dest`, `<role>_path`).
_DESTINATION_KEY = re.compile(r"^(?:\w+_)?(?:dest|destination|path)$")

# Methods that read, stat or write the path they are called on — pathlib's, plus
# the two a file handle carries, because a handle opened on a host path is the
# same reach by another name.
_READER_METHODS = frozenset(
    {
        "chmod",
        "exists",
        "glob",
        "is_dir",
        "is_file",
        "is_symlink",
        "iterdir",
        "lstat",
        "mkdir",
        "open",
        "read",
        "read_bytes",
        "read_text",
        "readline",
        "readlines",
        "rename",
        "replace",
        "rglob",
        "rmdir",
        "stat",
        "symlink_to",
        "touch",
        "unlink",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)

# Functions that take the path as an argument rather than as a receiver.
_READER_CALLS = frozenset(
    {
        "open",
        "os.listdir",
        "os.lstat",
        "os.makedirs",
        "os.mkdir",
        "os.path.exists",
        "os.path.getsize",
        "os.path.isdir",
        "os.path.isfile",
        "os.readlink",
        "os.remove",
        "os.rmdir",
        "os.stat",
        "os.unlink",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
    }
)

_REMEDIATION = (
    "derive the path from the `tmp_path` fixture — for an Ansible role, override its "
    "destination variable with a path inside the run's own tmp_path tree — so that a host "
    "which already holds the real file passes exactly as a host without it does"
)


class _Finding(NamedTuple):
    path: str
    line: int
    target: str
    kind: str


def _dotted(*, node: ast.expr) -> str:
    """The dotted name a call's callee spells, or a trailing-only name when it is computed."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    parts.append(current.id if isinstance(current, ast.Name) else "")
    return ".".join(reversed(parts))


def _call_findings(
    *, path: str, node: ast.Call, bound: Mapping[str, frozenset[str]]
) -> Iterator[_Finding]:
    dotted = _dotted(node=node.func)
    if dotted in _READER_CALLS:
        for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
            for target in named_paths(node=argument, bound=bound):
                yield _Finding(path=path, line=node.lineno, target=target, kind=f"call:{dotted}")
    if isinstance(node.func, ast.Attribute) and node.func.attr in _READER_METHODS:
        for target in named_paths(node=node.func.value, bound=bound):
            yield _Finding(
                path=path, line=node.lineno, target=target, kind=f"method:{node.func.attr}"
            )


def _key_name(*, node: ast.expr | None, constants: Mapping[str, str]) -> str:
    """One mapping key as a name: a string literal, a module constant holding one, or neither."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, "")
    return ""


def _destination_findings(
    *,
    path: str,
    node: ast.Dict,
    bound: Mapping[str, frozenset[str]],
    constants: Mapping[str, str],
) -> Iterator[_Finding]:
    for key, value in zip(node.keys, node.values, strict=True):
        name = _key_name(node=key, constants=constants)
        if _DESTINATION_KEY.match(name) is None:
            continue
        for target in named_paths(node=value, bound=bound):
            yield _Finding(path=path, line=value.lineno, target=target, kind=f"destination:{name}")


def _parameters(*, node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """Every parameter name one function declares, however it is passed."""
    arguments = node.args
    return frozenset(
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    )


def _lines(*, node: ast.AST) -> frozenset[int]:
    return frozenset(
        child.lineno for child in ast.walk(node) if isinstance(child, ast.stmt | ast.expr)
    )


def _exempt_lines(*, tree: ast.Module, allow_listed: frozenset[str]) -> frozenset[int]:
    """Every line of a function that DECLARES an allow-listed fixture."""
    return frozenset(
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and _parameters(node=node) & allow_listed
        for line in _lines(node=node)
    )


def _module_findings(
    *, path: str, tree: ast.Module, allow_listed: frozenset[str]
) -> list[_Finding]:
    bound = bound_names(tree=tree)
    constants = string_constants(tree=tree)
    exempt = _exempt_lines(tree=tree, allow_listed=allow_listed)
    findings: set[_Finding] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            findings.update(_call_findings(path=path, node=node, bound=bound))
        if isinstance(node, ast.Dict):
            findings.update(
                _destination_findings(path=path, node=node, bound=bound, constants=constants)
            )
    return sorted(
        (finding for finding in findings if finding.line not in exempt),
        key=lambda finding: (finding.line, finding.kind, finding.target),
    )


def _findings(*, cwd: Path, allow_listed: frozenset[str]) -> list[_Finding]:
    findings: list[_Finding] = []
    for file in sorted((cwd / _TESTS_DIR).rglob("*.py")):
        findings.extend(
            _module_findings(
                path=str(file.relative_to(cwd)),
                tree=ast.parse(file.read_text(encoding="utf-8")),
                allow_listed=allow_listed,
            )
        )
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("tests_host_path_free")
    findings = _findings(cwd=Path.cwd(), allow_listed=ALLOW_LISTED_FIXTURES)
    for finding in findings:
        log.error(
            "a test names a real host path as a filesystem target",
            path=finding.path,
            line=finding.line,
            target=finding.target,
            kind=finding.kind,
            remediation=_REMEDIATION,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
