"""release_bump_classification — refuse a release whose bump is weaker than its surface delta.

Per `SPECIFICATION/contracts.md` section "`release_bump_classification`
check" (a release-workflow check, per section "Shared check inventory"),
this check compares the public-surface delta between the last release
tag and `HEAD` against the semver classification the Conventional-Commit
types over that same range declare, and REFUSES when the declared
classification is strictly weaker than the delta requires.

It is invoked by a consumer's release-gating step — a `pre-push` script,
a release job, or any step that runs before a version number becomes
final — and has NO mandated caller: adoption is per-consumer opt-in. It
lives under `livespec_dev_tooling/workflow_checks/` (NOT `checks/`) so
the canonical-set derivation auto-excludes it; it is NOT a member of the
per-commit `just check` aggregate and NOT subject to the
wiring-completeness invariant.

The check exists because nothing otherwise binds a repository's ratified
`SPECIFICATION/contracts.md`'s bump rules to the version its release automation
computes. `release-please` derives the bump purely from the
Conventional-Commit type, so a change that `SPECIFICATION/contracts.md`
classifies as MAJOR ships as a patch whenever the commit carrying it was
typed `fix:`. No per-commit aggregate check can observe the mismatch: it
exists only between a RANGE of commits and a tag, and only at the moment
a version number is about to become final.

Algorithm (per the contracts section "`release_bump_classification` check"):

1. Resolve the last release tag — the highest `v[0-9]*` tag by version
   sort. No such tag → exit `0` with an `info` log (graceful skip; a
   repository before its first release has no baseline).
2. Build BOTH inventories from COMMITTED trees, never the working tree:
   the tag side via `git show <tag>:<path>`, the `HEAD` side via
   `git show HEAD:<path>`.
3. Compute the REQUIRED classification: any entry present at the tag and
   absent at `HEAD` (removal/rename) → `major`; otherwise any entry
   absent at the tag and present at `HEAD` (addition) → `minor`;
   otherwise (equal) → `none`.
4. Compute the DECLARED classification over `<tag>..HEAD`, strongest
   wins: `!` in the type/scope prefix or a `BREAKING CHANGE:` /
   `BREAKING-CHANGE:` footer → `major`; `feat` → `minor`; `fix` or
   `perf` → `patch`; anything else contributes nothing.
5. REFUSE (exit `4`) when declared is STRICTLY weaker than required,
   ordering `none` < `patch` < `minor` < `major`. Exit `0` otherwise.

Why both inventories read committed trees: the named `pre-push`
enforcement point commonly runs against a dirty tree. Reading the
working tree for the `HEAD` side would let an uncommitted `__all__` edit
inflate that inventory while step 4 reads only the committed
`<tag>..HEAD` range, producing a spurious refusal.

Why classifications and not version numbers: under a pre-`1.0.0`
version, `release-please` maps a `major` classification onto a minor
version bump and a `minor` onto a patch version bump (its
`bump-minor-pre-major` / `bump-patch-for-minor-pre-major` behavior).
Comparing computed VERSION bumps would therefore refuse every
correctly-typed `feat:` on a `0.y.z` repository. Comparing
classifications is correct on both sides of `1.0.0`.

THE HONEST LIMIT, which the ratified section requires this docstring to
state: the required classification derived from the `__all__` inventory
is a LOWER BOUND on what `SPECIFICATION/contracts.md` requires, never the whole
of it. It detects a surface element appearing or disappearing; it CANNOT
detect a behavior-only break — a tightened parse contract, a narrowed
glob, a changed return shape behind an unchanged name — which
`SPECIFICATION/contracts.md` independently classifies as MAJOR. A green result
means "no surface element changed incompatibly", NOT "the declared bump
is correct". This is stated rather than left implicit because the
incident that motivated the check was itself a mechanically-verified
signal mistaken for the behavior it was assumed to guarantee.

The inventory is derived by parsing each file with `ast` and reading the
module-level `__all__` assignment's literal string elements — never by
importing the module, which would both break determinism and execute
consumer code. A file with no module-level `__all__`, or one whose
`__all__` is not a literal list/tuple of strings, contributes nothing
and is not itself an error.

Exit codes:

- `0` — declared classification covers the surface delta, OR the
  graceful no-tag skip.
- `2` — usage error (bad CLI invocation).
- `4` — declared is strictly weaker than required; structured finding
  on stderr.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time so the check works equally well via `python -m` and
via direct script invocation.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_config  # noqa: E402  — after sys.path insert.

__all__: list[str] = []


_RELEASE_TAG_GLOB = "v[0-9]*"
_CLASSIFICATION_ORDER: dict[str, int] = {"none": 0, "patch": 1, "minor": 2, "major": 3}
_MINOR_TYPES = frozenset({"feat"})
_PATCH_TYPES = frozenset({"fix", "perf"})
# Conventional-Commit subject prefix: `type(scope)!: subject`. The `!` group is
# the breaking marker; scope is optional and its contents are not inspected.
_SUBJECT_PREFIX = re.compile(r"^(?P<type>[a-zA-Z]+)(?P<scope>\([^)]*\))?(?P<bang>!)?:")
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
# `%x00` separates the subject from the body; `%x1e` terminates each record.
# Both are chosen because git never emits them inside a commit message.
_LOG_FORMAT = "%s%x00%b%x1e"
_RECORD_SEPARATOR = "\x1e"
_FIELD_SEPARATOR = "\x00"
_LOG_RECORD_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class _Mismatch:
    """One refusal payload — the two classifications plus the delta that forced it."""

    required: str
    declared: str
    baseline_tag: str
    added: tuple[str, ...]
    removed: tuple[str, ...]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release-bump-classification",
        description=(
            "Refuse a release whose declared semver classification is weaker "
            "than its public-surface delta requires. Compares the `__all__` "
            "inventory between the last release tag and HEAD against the "
            "Conventional-Commit types over that range. Exits 4 on a "
            "mismatch, 0 when the declaration covers the delta or when the "
            "repository carries no release tag yet."
        ),
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("release_bump_classification")


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke git with a fixed argv, never raising on a non-zero exit."""
    # S603/S607: argv is a fixed list (literal `git` + caller-built repo
    # arguments), never a shell string, so no injection surface exists.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _baseline_tag(*, cwd: Path) -> str | None:
    """Return the highest `v[0-9]*` tag by version sort, or None when absent."""
    completed = _git(cwd=cwd, args=["tag", "--list", _RELEASE_TAG_GLOB, "--sort=-v:refname"])
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return None


def _exported_names(*, source: str, rel_path: str) -> frozenset[str]:
    """Parse one module's literal `__all__` entries into `<path>:<name>` keys.

    Returns an empty set for a file that declares no module-level
    `__all__`, or whose `__all__` is not a literal list or tuple of
    strings. Neither is an error: the inventory is a lower bound by
    construction.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in tree.body:
        if not _is_all_assignment(node=node):
            continue
        value = getattr(node, "value", None)
        if not isinstance(value, ast.List | ast.Tuple):
            continue
        for element in value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                names.add(f"{rel_path}:{element.value}")
    return frozenset(names)


def _is_all_assignment(*, node: ast.stmt) -> bool:
    """Report whether `node` assigns to a module-level `__all__` name."""
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == "__all__"
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    return False


def _tracked_python_files(*, cwd: Path, rev: str, trees: tuple[str, ...]) -> tuple[str, ...]:
    """List `.py` paths tracked at `rev` that sit under one of `trees`."""
    completed = _git(cwd=cwd, args=["ls-tree", "-r", "--name-only", rev])
    if completed.returncode != 0:
        return ()
    paths = [
        line
        for line in completed.stdout.splitlines()
        if line.endswith(".py") and _under_any(rel=line, trees=trees)
    ]
    return tuple(sorted(paths))


def _under_any(*, rel: str, trees: tuple[str, ...]) -> bool:
    """Report whether `rel` equals or sits beneath any tree in `trees`."""
    return any(rel == tree or rel.startswith(f"{tree}/") for tree in trees)


def _inventory_at(*, cwd: Path, rev: str, trees: tuple[str, ...]) -> frozenset[str]:
    """Build the `<path>:<name>` inventory from the COMMITTED tree at `rev`."""
    inventory: set[str] = set()
    for rel_path in _tracked_python_files(cwd=cwd, rev=rev, trees=trees):
        blob = _git(cwd=cwd, args=["show", f"{rev}:{rel_path}"])
        if blob.returncode != 0:
            continue
        inventory |= _exported_names(source=blob.stdout, rel_path=rel_path)
    return frozenset(inventory)


def _subject_classification(*, subject: str) -> str:
    """Classify one Conventional-Commit subject line."""
    match = _SUBJECT_PREFIX.match(subject)
    if match is None:
        return "none"
    if match.group("bang"):
        return "major"
    commit_type = match.group("type").lower()
    if commit_type in _MINOR_TYPES:
        return "minor"
    if commit_type in _PATCH_TYPES:
        return "patch"
    return "none"


def _declared_classification(*, cwd: Path, tag: str) -> str:
    """Return the strongest classification declared across `<tag>..HEAD`."""
    completed = _git(cwd=cwd, args=["log", f"--format={_LOG_FORMAT}", f"{tag}..HEAD"])
    if completed.returncode != 0:
        return "none"
    strongest = "none"
    for record in completed.stdout.split(_RECORD_SEPARATOR):
        fields = record.strip("\n").split(_FIELD_SEPARATOR)
        if len(fields) < _LOG_RECORD_FIELDS:
            continue
        classification = _subject_classification(subject=fields[0])
        if _BREAKING_FOOTER.search(fields[1]):
            classification = "major"
        if _CLASSIFICATION_ORDER[classification] > _CLASSIFICATION_ORDER[strongest]:
            strongest = classification
    return strongest


def _required_classification(*, added: tuple[str, ...], removed: tuple[str, ...]) -> str:
    """Map the surface delta onto the classification it demands."""
    if removed:
        return "major"
    if added:
        return "minor"
    return "none"


def _emit_finding(*, log: structlog.stdlib.BoundLogger, mismatch: _Mismatch) -> None:
    message = (
        f"public surface requires a {mismatch.required} bump but the commits "
        f"since {mismatch.baseline_tag} declare {mismatch.declared}"
    )
    fields = {
        "check_id": "release_bump_classification",
        "required_classification": mismatch.required,
        "declared_classification": mismatch.declared,
        "baseline_tag": mismatch.baseline_tag,
        "added": list(mismatch.added),
        "removed": list(mismatch.removed),
        "hint": (
            "retype the offending commit, or record the intended release "
            "explicitly, so the automation derives the classification the "
            "surface delta requires"
        ),
        "path": "",
        "line": 0,
    }
    log.error(message, status="fail", **fields)


def main() -> int:
    parser = _build_parser()
    _ = parser.parse_args()
    log = _configure_logger()
    cwd = Path.cwd()
    tag = _baseline_tag(cwd=cwd)
    if tag is None:
        log.info(
            "no release tag matching v[0-9]*; skipping",
            check_id="release_bump_classification",
            hint="a repository before its first release has no baseline to compare against",
        )
        return 0
    trees = tuple(str(tree) for tree in load_config(repo_root=cwd).source_trees)
    baseline = _inventory_at(cwd=cwd, rev=tag, trees=trees)
    head = _inventory_at(cwd=cwd, rev="HEAD", trees=trees)
    added = tuple(sorted(head - baseline))
    removed = tuple(sorted(baseline - head))
    required = _required_classification(added=added, removed=removed)
    declared = _declared_classification(cwd=cwd, tag=tag)
    if _CLASSIFICATION_ORDER[declared] >= _CLASSIFICATION_ORDER[required]:
        return 0
    _emit_finding(
        log=log,
        mismatch=_Mismatch(
            required=required,
            declared=declared,
            baseline_tag=tag,
            added=added,
            removed=removed,
        ),
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
