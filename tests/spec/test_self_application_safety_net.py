"""§"Self-application" — "as part of the standard local + CI safety net", which is the whole clause.

The section's first sentence defers: "The library MUST apply its own checks to
itself per `constraints.md` §'Self-application'". Two siblings already hold that
half — `tests.spec.test_self_application` asserts the configured universe is this
library's own modules, and `tests.spec.test_definition_of_done_gates` asserts
every shipped slug is a target of the aggregate. Restating either here would be
tautological.

The second sentence adds something neither covers: `just check` must exercise
every shared check "as part of the STANDARD LOCAL + CI SAFETY NET". That names a
PATH, not a target list, and the path is where self-application quietly stops
being total:

- **A subset on the push-gating path.** A predicate that routes a doc-only push
  to a smaller aggregate makes the branch gate weaker than the master gate. It
  is not hypothetical here: this repository shipped exactly that branch, and its
  own `check-pre-push.sh` records that it "made a doc-only push run fewer checks
  than master, the exact PR-gate-weaker-than-master hole that reddened master on
  2026-09-04". Nothing failed on the way in — the smaller gate was green.
- **A quiet growth of the hook-path omission list.** The hook path does omit
  one member, deliberately and by name, and that omission is sound only while
  what it omits is a check about OTHER repositories' live state rather than a
  check this library applies to its own tree. A shipped slug added to that list
  would leave `just check` green locally while one of the library's own checks
  never ran against the library — self-application partial, with no diagnostic.

Both are read off the committed shell rather than by running the aggregate: the
scripts ARE the wiring under assertion, and running `just check` from inside the
suite it gates would be a second execution of it rather than a test of it.

The green-token skip in the pre-push script is not a subset and is not asserted
against: it skips the aggregate only for a tree byte-identical to one the
aggregate already passed, which is a caching argument rather than a narrowing of
what runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_PUSH = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"
_CHECK_SH = _REPO_ROOT / "scripts" / "just" / "check.sh"
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"

# The reduced aggregate. Reaching it from the push gate or from CI is the
# PR-gate-weaker-than-master hole; from pre-commit it is a local speed choice.
_SUBSET_RECIPE = "check-pre-commit-doc-only"

# The full aggregate, and the hook-path omission list that is allowed to
# shrink it — one literal assignment, so a growth of it is one visible diff.
_FULL_AGGREGATE = re.compile(r"^just(?: [a-z_]+=\S+)* check$", re.MULTILINE)
_HOOK_GATE_SKIPS = re.compile(r'^hook_gate_skips="(?P<slugs>[^"]*)"$', re.MULTILINE)


def _uncommented_lines(*, source: Path) -> list[str]:
    """Every non-comment, non-blank line of a shell script."""
    return [
        line.strip()
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _shipped_slugs() -> set[str]:
    """Every canonical check slug this library ships."""
    resolved = canonical_check_slugs()
    assert isinstance(resolved, IOSuccess), f"canonical slug discovery must succeed; got {resolved}"
    return set(unsafe_perform_io(resolved.unwrap()))


def test_the_push_gate_runs_the_full_aggregate_and_delegates_to_no_subset() -> None:
    """The push-gating path is the standard safety net, not a sample of it."""
    lines = _uncommented_lines(source=_PRE_PUSH)
    delegating = [line for line in lines if _SUBSET_RECIPE in line]
    assert not delegating, (
        f"the push gate must not route to `{_SUBSET_RECIPE}`. A change-class predicate "
        f"there makes the branch gate weaker than the master gate — this repository "
        f"shipped that branch and its own script records it reddening master on "
        f"2026-09-04 — and it fails by passing: the smaller aggregate is green; "
        f"delegating={delegating}"
    )
    runs_full = [line for line in lines if _FULL_AGGREGATE.match(line)]
    assert runs_full, (
        f"the push gate must invoke the FULL `just check` aggregate, which is what makes "
        f"`just check` the standard local safety net the section names; "
        f"script={_PRE_PUSH.relative_to(_REPO_ROOT)} lines={lines}"
    )


def test_no_ci_workflow_gates_on_the_reduced_aggregate() -> None:
    """The other half of "local + CI": the merge gate never samples either."""
    reaching = sorted(
        f"{path.name}:{number}"
        for path in sorted(_WORKFLOWS_DIR.glob("*.y*ml"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _SUBSET_RECIPE in line and not line.strip().startswith("#")
    )
    assert not reaching, (
        f"CI is the authoritative half of the safety net, so no workflow may gate on "
        f"`{_SUBSET_RECIPE}`: a merge decided by the reduced aggregate is a merge for "
        f"which most of this library's self-application never ran; reaching={reaching}"
    )


def test_the_hook_path_omits_no_check_this_library_ships() -> None:
    """The one deliberate omission stays a fact about other repositories, not about this one."""
    matched = _HOOK_GATE_SKIPS.search(_CHECK_SH.read_text(encoding="utf-8"))
    assert matched is not None, (
        f"the hook path's omissions must be ONE literal enumeration in "
        f"`{_CHECK_SH.relative_to(_REPO_ROOT)}`, so that shrinking the local safety net "
        f"is a single visible diff rather than a predicate that can rot"
    )
    omitted = set(matched.group("slugs").split())
    self_applied = sorted(omitted & _shipped_slugs())
    assert not self_applied, (
        f"these are checks this library SHIPS, and the hook path omits them. The section "
        f"requires `just check` to exercise every shared check against this repository's "
        f"own tree as part of the local safety net; an omitted shipped check leaves the "
        f"aggregate green locally while one of the library's own checks never ran against "
        f"the library — partial self-application, reported as a pass; "
        f"self_applied={self_applied} omitted={sorted(omitted)}"
    )
