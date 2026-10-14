"""commit_metadata_invariance — no fleet check's verdict moves with rebase-merge metadata.

GitHub's rebase-merge does not land the commit a pull request's CI judged. It
MINTS A NEW ONE: same tree, same author fields, same message — and a new SHA, a
new committer date, and the committer's own timezone offset. A check whose
verdict reads any of those three gives one answer at pull-request time and
another on master, and nothing observable at pull-request time can catch it.

That is not hypothetical. On 2026-10-14 orchestrator PR #2917 passed CI (run
38493306513); rebase-merge minted `35fea321` with committer date
`2026-10-13T18:12:41-07:00`; master run 38494465107 then failed
`check-heading-coverage-debt-register`, which read `%cs` — the committer date in
the COMMIT'S OWN TIMEZONE, so one instant carried two calendar dates. Master was
red ~38 minutes and the green-master gate refused every factory dispatch from
that repository for the whole window. Filed as livespec-dev-tooling-a6gq5n;
this module is the generalization (livespec-dev-tooling-yfqvqm, plan
`red-master-self-healing`).

WHAT IT ENFORCES. Every git pretty-format read of a rebase-merge-VARIANT commit
field in the shipped library is either absent or REGISTERED in
`INVARIANCE_PROOFS` with a recorded reason it cannot move a verdict. The
registry is deliberately keyed by (module, specifier) and deliberately small: a
new variant read has to be argued for in writing, and a proof that outlives its
read is reported STALE, so the registry cannot quietly become an exemption list.

THREE CLASSES, because their remedies differ:

- `TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS` — the committer date rendered in the
  commit's own timezone. BANNED outright and never registrable: one instant
  renders as two different calendar dates depending on the offset the
  committer's clock was set to, so there is no invariance argument to record.
  The remedy is `%cI` normalized to UTC, or the author date, or the tree.
- `ABSOLUTE_COMMITTER_SPECIFIERS` — the committer date as one instant on one
  basis: strict ISO (`%cI`, which carries its offset explicitly) and the epoch
  (`%ct`). Registrable, because a rebase-merge still RE-STAMPS the instant: the
  proof has to say why the later instant cannot flip the verdict.
- `COMMIT_SHA_SPECIFIERS` — registrable, because a SHA used as a HANDLE (it
  addresses a commit or a tree, and the content it addresses is unchanged) is
  invariant, while a SHA used as a VALUE (compared, matched, or recorded as
  evidence a later verdict reads) is not. Which one it is cannot be decided
  statically; the proof says which, and why.

WHY IT IS NOT A CHECK SLUG. A module under `checks/` becomes a canonical check
slug, and a canonical slug obliges EVERY consumer to wire it into `just check`
AND its CI matrix — the obligation `SPECIFICATION/contracts.md` of this
repository records where it partitions the shared check inventory, with the
same mechanical reasoning it gives for `charters/` and `workflow_checks/`,
which sit outside `checks/` for exactly this. The inventory ships from THIS
repository
alone, so this repository's own test suite
(`tests/livespec_dev_tooling/test_commit_metadata_invariance.py`) is the
enforcement point, and arming it fleet-wide would conscript consumers who
author no shared checks.

WHY THE SCAN IS AST-BASED, AND WHAT THAT BUYS. A text matcher would convict
`heading_coverage_debt.py`, which documents the `%cs` defect it was repaired of
at length and on purpose — and the only way back to green would be deleting
that rationale. Docstrings are skipped and comments never reach the AST, so the
design record is safe to keep. A git format INTRODUCER (`--format`, `--pretty`,
`--date`) is required in the same argument vector, which is what tells git's
`%H` (the commit SHA) from `strftime`'s `%H` (the hour): three live call sites
stamp `"%Y-%m-%dT%H:%M:%SZ"` and a bare specifier scan would convict all three.

SCOPE LIMIT, STATED RATHER THAN HIDDEN. The scan sees literals, f-strings, and
module-level `NAME = "<literal>"` constants substituted into an argument
vector. A format assembled at runtime — read from a config file, concatenated
from a function parameter, built in a loop — is beyond it. This is a
REINTRODUCTION GUARD against the shape the defect actually took, not a proof of
impossibility; the audit note at
`plan/red-master-self-healing/research/003-commit-metadata-invariance-audit.md`
carries the per-check reasoning for every read that exists today.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.config import iter_py_files

__all__: list[str] = [
    "ABSOLUTE_COMMITTER_SPECIFIERS",
    "COMMIT_SHA_SPECIFIERS",
    "FORMAT_INTRODUCERS",
    "INVARIANCE_PROOFS",
    "TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS",
    "CommitMetadataRead",
    "InvarianceFindings",
    "InvarianceProof",
    "commit_metadata_reads",
    "invariance_findings",
    "shipped_library_sources",
]

# The committer date rendered in the COMMIT'S OWN TIMEZONE. `%cs` is the
# spelling that reddened orchestrator master on 2026-10-14; the other three are
# the same hazard in different clothes (`%cd`/`%cD` render under `--date`, `%ci`
# is the local-offset rendering, `%cr` is relative to now).
TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS: tuple[str, ...] = ("%cD", "%cd", "%ci", "%cr", "%cs")
ABSOLUTE_COMMITTER_SPECIFIERS: tuple[str, ...] = ("%cI", "%ct")
COMMIT_SHA_SPECIFIERS: tuple[str, ...] = ("%H", "%h")
# A git pretty-format argument announces itself. Requiring the announcement in
# the same argument vector is what keeps `strftime`'s `%H` out of the findings.
FORMAT_INTRODUCERS: tuple[str, ...] = ("--date", "--format", "--pretty")

_ALL_SPECIFIERS: tuple[str, ...] = (
    *TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS,
    *ABSOLUTE_COMMITTER_SPECIFIERS,
    *COMMIT_SHA_SPECIFIERS,
)
_VECTOR_NODES = (ast.List, ast.Tuple, ast.Call, ast.Constant, ast.JoinedStr)
_DOCSTRING_HOLDERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True, kw_only=True)
class CommitMetadataRead:
    """One rebase-merge-variant commit field read at one source location."""

    path: Path
    line: int
    specifier: str


@dataclass(frozen=True, kw_only=True)
class InvarianceProof:
    """A recorded argument that one (module, specifier) read cannot move a verdict.

    `module` is the path relative to the shipped package root, so the registry
    reads the same from any checkout.
    """

    module: str
    specifier: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class InvarianceFindings:
    """The three ways the invariance rule breaks, kept apart because their remedies are.

    `banned` is repaired by changing the read. `unproven` is repaired by
    changing the read OR by recording a proof. `stale_proofs` is reported at all
    because a registry that outlives its reads stops being evidence of anything
    and starts being an exemption list nobody re-reads.
    """

    banned: tuple[CommitMetadataRead, ...]
    unproven: tuple[CommitMetadataRead, ...]
    stale_proofs: tuple[InvarianceProof, ...]


INVARIANCE_PROOFS: tuple[InvarianceProof, ...] = (
    InvarianceProof(
        module="heading_coverage_debt.py",
        specifier="%H",
        reason=(
            "HANDLE, not value. The SHA addresses the registry blob of that revision via "
            "`git show <revision>:tests/heading-coverage.json`, and a rebase-merge replay "
            "addresses a byte-identical blob, so every date the generator derives is "
            "unchanged. The SHA is never compared, recorded, or emitted"
        ),
    ),
    InvarianceProof(
        module="heading_coverage_debt.py",
        specifier="%cI",
        reason=(
            "ONE-SIDED BOUND. The instant is normalized to UTC by `_utc_calendar_date`, so "
            "the committer's offset cannot move the calendar date, and the only verdict it "
            "reaches (`_heading_coverage_first_seen`: a recorded `first_seen` MUST NOT be "
            "LATER than this evidence) is monotone in it. A replay can only re-stamp the "
            "instant LATER, which loosens that bound and can never flip the verdict. The "
            "repair of the `%cs` read this replaced is carried by "
            "livespec-dev-tooling-a6gq5n under plan fleet-heading-coverage-convergence"
        ),
    ),
)

_PROVEN_PAIRS: frozenset[tuple[str, str]] = frozenset(
    (proof.module, proof.specifier) for proof in INVARIANCE_PROOFS
)


def shipped_library_sources(*, package_root: Path) -> tuple[Path, ...]:
    """Every first-party `.py` of the shipped library, `_vendor`/`__pycache__` aside.

    The universe is the WHOLE library rather than the slug modules alone,
    because a check's verdict is computed by whatever it delegates to:
    `heading_coverage_debt_register` reads its git evidence through
    `_heading_coverage_first_seen` and `heading_coverage_debt`, and neither is a
    slug. A superset is the only sound universe over which a clean scan says
    anything about the inventory, and the companion test is what proves this set
    IS a superset of it.
    """
    return tuple(iter_py_files(root=package_root))


def _constant_strings(*, tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "<literal>"` bindings, for substitution into a vector.

    Single-target module-level assignment of a bare string only. That is the
    shape a format constant actually takes (`_LOG_FORMAT = "%s%x00%b%x1e"`);
    anything assembled at runtime is out of reach by construction — see the
    module docstring's scope limit.
    """
    bindings: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            bindings[node.targets[0].id] = node.value.value
    return bindings


def _rendered(*, node: ast.expr, constants: dict[str, str]) -> str | None:
    """The string this expression contributes to an argument vector, or None.

    An f-string renders as its literal parts plus any substituted module
    constant, concatenated — `f"--format={_LOG_FORMAT}"` is how a format
    argument reaches git with neither half a literal of its own.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.FormattedValue):
        return _rendered(node=node.value, constants=constants)
    if isinstance(node, ast.JoinedStr):
        parts = [_rendered(node=value, constants=constants) for value in node.values]
        return "".join(part for part in parts if part is not None)
    return None


def _vector_strings(*, node: ast.expr, constants: dict[str, str]) -> tuple[str, ...]:
    """The strings one argument vector carries; a bare expression is a vector of one."""
    if isinstance(node, ast.List | ast.Tuple):
        elements: list[ast.expr] = list(node.elts)
    elif isinstance(node, ast.Call):
        elements = [*node.args, *(keyword.value for keyword in node.keywords)]
    else:
        elements = [node]
    rendered = [_rendered(node=element, constants=constants) for element in elements]
    return tuple(part for part in rendered if part is not None)


def _specifiers_in(*, strings: tuple[str, ...]) -> tuple[str, ...]:
    """The variant specifiers this vector names — empty unless it announces a format.

    The introducer requirement is the whole precision of this detector: without
    it, `"%Y-%m-%dT%H:%M:%SZ"` reads as a commit-SHA read.
    """
    if not any(introducer in text for text in strings for introducer in FORMAT_INTRODUCERS):
        return ()
    return tuple(
        specifier for specifier in _ALL_SPECIFIERS if any(specifier in text for text in strings)
    )


def _docstring_ids(*, tree: ast.Module) -> frozenset[int]:
    """`id()`s of every docstring expression, which carry prose and never a read."""
    ids: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, _DOCSTRING_HOLDERS)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        ):
            ids.append(id(node.body[0].value))
    return frozenset(ids)


def commit_metadata_reads(*, source: str, path: Path) -> tuple[CommitMetadataRead, ...]:
    """Every rebase-merge-variant commit field this module reads, at its earliest line.

    ONE READ PER SPECIFIER, because the verdict is keyed by (module, specifier)
    and because the same read is reached twice by construction: a literal
    carrying both introducer and specifier matches on its own AND inside the
    argument vector that holds it. Reporting both would print a format constant
    twice and say nothing more. The line is the earliest match, which is where a
    reader starts; the module is where the remedy is.
    """
    tree = ast.parse(source)
    constants = _constant_strings(tree=tree)
    skip = _docstring_ids(tree=tree)
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, _VECTOR_NODES) or id(node) in skip:
            continue
        strings = _vector_strings(node=node, constants=constants)
        for specifier in _specifiers_in(strings=strings):
            found[specifier] = min(found.get(specifier, node.lineno), node.lineno)
    return tuple(
        CommitMetadataRead(path=path, line=line, specifier=specifier)
        for specifier, line in sorted(found.items(), key=lambda item: (item[1], item[0]))
    )


def invariance_findings(*, package_root: Path) -> InvarianceFindings:
    """Classify every variant metadata read under `package_root` against the registry.

    FAIL-CLOSED by shape: a read is a finding unless a proof names its exact
    (module, specifier) pair, and a banned specifier is a finding BEFORE the
    registry is consulted at all, so no entry can sanction one.
    """
    banned: list[CommitMetadataRead] = []
    unproven: list[CommitMetadataRead] = []
    seen: set[tuple[str, str]] = set()
    for path in shipped_library_sources(package_root=package_root):
        module = path.relative_to(package_root).as_posix()
        for read in commit_metadata_reads(source=path.read_text(encoding="utf-8"), path=path):
            if read.specifier in TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS:
                banned.append(read)
                continue
            seen.add((module, read.specifier))
            if (module, read.specifier) not in _PROVEN_PAIRS:
                unproven.append(read)
    return InvarianceFindings(
        banned=tuple(banned),
        unproven=tuple(unproven),
        stale_proofs=tuple(
            proof for proof in INVARIANCE_PROOFS if (proof.module, proof.specifier) not in seen
        ),
    )
