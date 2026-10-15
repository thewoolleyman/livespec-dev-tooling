"""Rebase-merge metadata invariance for every module the shared check inventory reaches.

Plan `red-master-self-healing` design item 1 (livespec-dev-tooling-yfqvqm): a
commit and its rebase-merge replay — differing only in commit SHA, committer
date and committer timezone — MUST receive the same verdict from every check in
the shared check inventory. The 2026-10-14 incident is what the rule is made of:
livespec-orchestrator-beads-fabro PR #2917 passed its own CI, the forge's
rebase-merge minted `35fea321` over the UNCHANGED TREE with a committer date of
2026-10-13T18:12:41-07:00, and `check-heading-coverage-debt-register` — reading
`%cs`, the committer date in the commit's OWN timezone — convicted master on the
date the PR had just certified. Nothing available at PR time could have caught
it, and the green-master gate refused every dispatch from that repository until
a fix-forward landed.

WHY THIS IS A STATIC SCAN RATHER THAN A REPLAY HARNESS. The property is
universally quantified over the inventory, and the honest way to quantify over
seventy checks is to remove the dependency rather than to sample it: a check
that never READS a field cannot return a verdict that varies with it. Running
each check twice over a synthetic replay pair would prove the property only for
the fixture each check happened to be given, and would say nothing about the
branch the fixture did not reach. So the assertion is absence-of-dependency, and
it is exact in the direction that matters: a passing scan is a proof, not a
sample.

THE WALK SET IS THE PACKAGE, NOT `checks/`, AND THE INCIDENT IS WHY. A check's
verdict can depend on any module it imports, and the read that reddened master
did not live in `checks/` at all — it lived in the top-level
`heading_coverage_debt.py` that `checks/heading_coverage_debt_register.py`
reaches through. Scoping this scan to the canonical `checks/*.py` directory would
therefore have acquitted the one defect it exists to convict. The walk set is the
whole shipped package (minus the vendored and byte-cache trees), which is a
superset of the inventory — every canonical check, every workflow check, every
importable charter detector, and everything any of them imports.

TWO TIERS, BECAUSE THE FIELDS ARE NOT EQUALLY HOPELESS.

- NEVER INVARIANT, no declaration possible. A committer date rendered in the
  commit's own timezone (`%cs`, `%cd`, `%cD`, `%ci`, `%cr`) carries the
  OBSERVER's offset into the answer, so one instant yields two calendar dates;
  the committer identity (`%cn`, `%cN`, `%ce`, `%cE`, `%cl`, `%cL`) is replaced
  wholesale by the forge's web-flow account on merge. A `git log` filtered with
  `--since` / `--until` / `--before` / `--after` is the same defect wearing a
  flag: those filters read the COMMITTER date by default, so a replay silently
  changes which commits the walk even sees. No rationale rescues these, so no
  registry entry can admit one.
- INSTANT-EXACT OR AN IDENTIFIER, admissible WITH a recorded argument. `%ct` and
  `%cI` name an instant rather than a local calendar date, so the timezone drops
  out — but the instant itself is still re-stamped, so a read needs an argument
  for why its verdict survives that. `%H` and `%h` name a commit, and naming one
  in order to read its TREE is not the same as resting a verdict on the SHA
  value. Each such read is declared below with the argument that makes it
  invariant, and the declaration is asserted in BOTH directions: an undeclared
  read fails, and a declaration whose read is gone fails too. The second
  direction is the one that keeps a registry from rotting into an unexamined
  exemption list — the `repo_local_ci_skips` precedent.

WHAT THIS DOES NOT SEE. The scan reads string literals in the AST, so it is
blind to a format spec assembled at runtime (`f"--format=%c{letter}"`) and to a
placeholder that reaches git through a variable built elsewhere. Neither shape
exists in the package today and both would be a strange way to spell a git
format; the mitigation is that any such read still has to pass review, and this
file is the thing review has to be checked against.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

# Vendored third-party code and byte caches are not this repository's reads to
# police; every check's own walk skips them for the same reason.
_UNSCANNED_PARTS = ("_vendor", "__pycache__")

# The trailing look-ahead keeps `%ci` from matching inside `%cia` and keeps the
# case-sensitive pair `%ci` / `%cI` apart — they are different fields, and only
# one of them is admissible.
_NEVER_INVARIANT = re.compile(r"%c(?:s|d|D|i|r|n|N|e|E|l|L)(?![A-Za-z])")

# `git log` applies these to the COMMITTER date unless `--author-date-order` or
# an explicit author-date form is used, so they select on the one field a
# rebase-merge rewrites.
_COMMITTER_DATE_FILTER = re.compile(r"--(?:since|until|before|after)(?![A-Za-z-])")

# `%ct`, `%cI` and the environment name have no collision with any other format
# language this package writes, so they are read wherever they appear.
_DECLARABLE_ANYWHERE = re.compile(r"%(?:ct|cI)(?![A-Za-z])|GIT_COMMITTER_DATE")

# `%H` AND `%h` COLLIDE WITH `strftime`, AND THE COLLISION IS NOT RARE. In git
# they are the full and abbreviated commit SHA; in `strftime` they are the
# zero-padded hour and the abbreviated month name. The first draft of this scan
# read them everywhere and convicted four `strftime("%Y-%m-%dT%H:%M:%SZ")`
# timestamps in `vendor_update` and `_red_green_replay_modes` — reads that touch
# no commit at all. So the SHA tier is read only inside a literal that IS a git
# pretty-format spec. The residual blind spot is a spec split across argv
# elements (`["log", "--format", "%H"]`), a form this package never uses.
_SHA_FIELD = re.compile(r"%(?:H|h)(?![A-Za-z])")
_GIT_FORMAT_SPEC = re.compile(r"--format=|--pretty|format:")

# Each row: the module, the field it reads, and the argument for why a replay
# cannot move its verdict. Audited 2026-10-15 for
# plan/red-master-self-healing/research/003-commit-metadata-invariance-audit.md.
_DECLARED_INVARIANT_READS: tuple[tuple[str, str, str], ...] = (
    (
        "livespec_dev_tooling/heading_coverage_debt.py",
        "%H",
        "Read beside `%cI` on the same log line and used ONLY as the revision the "
        "next statement reads the registry BLOB from. The verdict rests on that "
        "blob's content, never on the SHA value, so a replay with a new SHA reads "
        "the same bytes and answers the same way.",
    ),
    (
        "livespec_dev_tooling/heading_coverage_debt.py",
        "%cI",
        "Instant-exact, so the committer's offset drops out, and `_utc_calendar_date` "
        "normalizes it to a UTC calendar date before any comparison. The instant it "
        "names is still re-stamped by the merge, and the bound it feeds is ONE-SIDED "
        "— the ratchet forbids a `first_seen` LATER than this evidence and treats an "
        "earlier one as ordinary — so a rebase-merge, which can only move the "
        "committer instant later, loosens the bound and can never flip a pass to a "
        "fail. This read is the repair of the triggering defect, carried by "
        "livespec-dev-tooling-a6gq5n under plan fleet-heading-coverage-convergence.",
    ),
)


def _scanned_modules() -> list[Path]:
    """Every shipped `.py` file whose string literals could reach git."""
    return sorted(
        path
        for path in _PACKAGE_DIR.rglob("*.py")
        if not any(part in _UNSCANNED_PARTS for part in path.parts)
    )


def _code_string_constants(*, source: str) -> list[tuple[int, str]]:
    """Every string constant in `source` that is NOT a docstring, as `(line, text)`.

    Docstrings are excluded by NODE IDENTITY rather than by value: equal string
    literals can be interned to one object, so comparing values would acquit a
    real read that happened to spell the same thing as a nearby docstring.
    Comments never enter the AST at all, which is correct here — prose cannot
    reach git, and this repository's own prose discusses `%cs` at length.
    """
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _occurrences(
    *, pattern: re.Pattern[str], git_format_only: bool = False
) -> list[tuple[str, int, str]]:
    """`(repo-relative path, line, matched field)` for every match in the walk set.

    `git_format_only` narrows the read to literals that are git pretty-format
    specs, which is what keeps the SHA tier off `strftime`'s `%H` and `%h`.
    """
    found: list[tuple[str, int, str]] = []
    for path in _scanned_modules():
        relative = path.relative_to(_REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        for line, text in _code_string_constants(source=source):
            if git_format_only and _GIT_FORMAT_SPEC.search(text) is None:
                continue
            found.extend((relative, line, match.group()) for match in pattern.finditer(text))
    return found


def test_no_module_the_inventory_reaches_reads_a_timezone_rendered_committer_field() -> None:
    """No shipped read carries the committer's own offset or identity into a verdict."""
    offenders = _occurrences(pattern=_NEVER_INVARIANT)
    assert offenders == [], (
        "a rebase-merge rewrites the committer date, its timezone and the committer "
        "identity, so a verdict reading any of these fields is a verdict on the "
        f"merge rather than on the tree: {offenders}"
    )


def test_no_module_filters_git_history_on_the_committer_date() -> None:
    """No shipped `git` read selects commits with a committer-date window."""
    offenders = _occurrences(pattern=_COMMITTER_DATE_FILTER)
    assert offenders == [], (
        "`--since` / `--until` / `--before` / `--after` filter on the COMMITTER date, "
        "so a replay changes which commits the walk sees and the verdict moves with "
        f"the merge time: {offenders}"
    )


def test_every_instant_or_sha_read_is_declared_with_its_invariance_argument() -> None:
    """The instant-exact and SHA reads match the registry in BOTH directions."""
    read = [
        *_occurrences(pattern=_DECLARABLE_ANYWHERE),
        *_occurrences(pattern=_SHA_FIELD, git_format_only=True),
    ]
    found = {(relative, field) for relative, _, field in read}
    declared = {(relative, field) for relative, field, _ in _DECLARED_INVARIANT_READS}
    assert found - declared == set(), (
        "an instant-exact or SHA read with no recorded invariance argument; declare it "
        f"in `_DECLARED_INVARIANT_READS` with the reason a replay cannot move its "
        f"verdict, or remove the read: {sorted(found - declared)}"
    )
    assert declared - found == set(), (
        "a declaration naming a read the package no longer makes — drop the row, or a "
        f"registry of reasons rots into an exemption list nobody re-reads: "
        f"{sorted(declared - found)}"
    )
    assert all(reason.strip() for _, _, reason in _DECLARED_INVARIANT_READS), (
        "every declared read carries a non-empty argument; an empty reason is an "
        "exemption wearing a registry row"
    )


def test_the_detector_convicts_a_volatile_read_and_acquits_prose() -> None:
    """The scan fires on a real read and stays silent on prose that merely names one.

    The positive control of the two assertions above. Both of them pass over a
    clean tree, and a detector that matched nothing would pass over a dirty one
    identically — so the discriminating behaviour is asserted directly, against
    the exact pair of shapes this repository contains: a format spec in an argv
    list, and a docstring explaining the field that spec must not use.
    """
    read = '"""Explains %cs and why it is wrong."""\nARGS = ["log", "--format=%cs"]\n'
    prose_only = '"""Explains %cs and why it is wrong."""\nARGS = ["log", "--format=%cI"]\n'
    convicted = [
        text
        for _, text in _code_string_constants(source=read)
        if _NEVER_INVARIANT.search(text) is not None
    ]
    acquitted = [
        text
        for _, text in _code_string_constants(source=prose_only)
        if _NEVER_INVARIANT.search(text) is not None
    ]
    assert convicted == ["--format=%cs"], convicted
    assert acquitted == [], acquitted
    # The `strftime` collision, asserted rather than trusted: the hour in a
    # timestamp is not a commit SHA, and the git-format narrowing is the only
    # thing standing between the two.
    assert _SHA_FIELD.search("%Y-%m-%dT%H:%M:%SZ") is not None, "the collision is real"
    assert _GIT_FORMAT_SPEC.search("%Y-%m-%dT%H:%M:%SZ") is None, "a timestamp is not a git spec"
    assert _GIT_FORMAT_SPEC.search("--format=%H %cI") is not None, "a git spec is recognised"
