"""Mirror of `livespec_dev_tooling.check_purity` — which members the green token may memoize.

The token-memoization contract of `SPECIFICATION/contracts.md`, in its
delegated pre-push gate section (ratified v080): the token memoizes only the
members whose verdict depends on the committed tree alone, every member carries
its own purity declaration, and "a member with no purity declaration MUST be
treated as world-reading".

The two directions that make the default SAFE are asserted here, because a
resolver that returned "tree-pure" for something it could not read would
reproduce the exact defect this module exists to close — a token asserting a
verdict about external state observed at an arbitrarily distant past moment
(work-item livespec-dev-tooling-aape, measured on a seven-week-old token):

- an UNDECLARED member is reported as undeclared, never as tree-pure;
- a declaration the vocabulary does not name is a FAILURE, never a silent
  fallback to the safe default. "I cannot read this declaration" and "this
  declaration says world-reading" must not be spelled the same way, because the
  first is a registry bug that `just check` has to name and the second is a
  normal answer.

The live-registry directions — every `world_gate_check_slugs()` slug and both
of the two gates the token actually memoized on a maintainer host — are asserted
against the SHIPPED declarations rather than a fixture, because the declarations
are the deliverable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import check_purity
from livespec_dev_tooling.canonical_checks import world_gate_check_slugs

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The two members that are BOTH world-reading and ACTIVE on a maintainer host
# whose `gh` credential carries admin scope, and so carry the live risk the
# work-item records: a push landing on a red master on the strength of a
# weeks-old observation.
_LIVE_RISK_GATES = ("check-branch-protection-alignment", "check-master-ci-green")


def _aggregate_members() -> tuple[str, ...]:
    """Every `check-` member of this repository's own aggregate inventory."""
    raw = (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8")
    members: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("check-"):
            continue
        members.append(stripped.split("#", 1)[0].strip())
    return tuple(members)


def _audit(*, targets: tuple[str, ...], repo_root: Path = _REPO_ROOT) -> check_purity.PurityAudit:
    """The audit for `targets`, asserting the read itself succeeded."""
    result = check_purity.audit_check_purity(targets=targets, repo_root=repo_root)
    assert is_successful(result), f"purity audit must succeed for {targets}; got {result}"
    return unsafe_perform_io(result.unwrap())


def test_the_two_gates_the_token_memoized_on_a_maintainer_host_are_world_reading() -> None:
    """These two are why the item exists: both impure, both active under admin scope."""
    audit = _audit(targets=_LIVE_RISK_GATES)

    assert audit.world_reading == _LIVE_RISK_GATES, (
        f"`check-master-ci-green` reads GitHub's check-run status for master's head commit "
        f"and `check-branch-protection-alignment` reads live branch-protection settings; "
        f"neither verdict is a function of the pushed tree, so neither may be memoized by a "
        f"tree-keyed token; audit={audit}"
    )


def test_every_world_gate_slug_is_declared_world_reading() -> None:
    """`world_gate_check_slugs()` IS the curated set of checks that verify the world."""
    resolved = world_gate_check_slugs()
    assert is_successful(resolved), f"world-gate slug discovery must succeed; got {resolved}"
    slugs = tuple(unsafe_perform_io(resolved.unwrap()))
    audit = _audit(targets=slugs)

    assert audit.tree_pure == () and audit.undeclared == (), (
        f"every member of the curated world-gate registry verifies the WORLD the change "
        f"lands on — master's CI state, live branch protection, or the work-items ledger — "
        f"so declaring one tree-pure, or leaving one undeclared while the registry names it, "
        f"would let the token memoize a verdict about state no tree determines; "
        f"slugs={slugs} audit={audit}"
    )


def test_every_member_of_this_repositorys_aggregate_carries_a_purity_declaration() -> None:
    """The saving is only safe while nothing falls through to the world-reading default."""
    members = _aggregate_members()
    audit = _audit(targets=members)

    assert audit.undeclared == (), (
        f"each member of this repository's check aggregate must declare its own purity — a "
        f"canonical check in its own module, a repo-private member in `check-targets.txt`. "
        f"An undeclared member is treated as world-reading and so still runs, but it shrinks "
        f"the saving the token exists for without anyone noticing; "
        f"undeclared={audit.undeclared}"
    )


def test_an_undeclared_member_is_reported_undeclared_rather_than_tree_pure() -> None:
    """The default is SAFE: absence of evidence is never read as evidence of purity."""
    audit = _audit(targets=("check-no-such-member",))

    assert audit.undeclared == ("check-no-such-member",), f"audit={audit}"
    assert audit.tree_pure == (), (
        f"a member whose declaration cannot be found must never be classified tree-pure: "
        f"that is the direction in which a mistake memoizes an impure verdict; audit={audit}"
    )


def test_a_member_outside_the_check_slug_namespace_resolves_from_the_inventory(
    *, tmp_path: Path
) -> None:
    """A consumer's aggregate holds members that are not `check-`-prefixed slugs."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-only  # purity: tree-pure\n", encoding="utf-8"
    )

    audit = _audit(targets=("e2e-test-claude-code-mock", "check-local-only"), repo_root=tmp_path)

    assert audit.undeclared == ("e2e-test-claude-code-mock",), f"audit={audit}"
    assert audit.tree_pure == ("check-local-only",), f"audit={audit}"


def test_an_absent_inventory_leaves_every_repo_private_member_undeclared(*, tmp_path: Path) -> None:
    """No inventory is no evidence — it must not read as "everything is pure"."""
    audit = _audit(targets=("check-local-only",), repo_root=tmp_path)

    assert audit.undeclared == ("check-local-only",), f"audit={audit}"


def test_inventory_lines_that_declare_nothing_are_not_mistaken_for_declarations(
    *, tmp_path: Path
) -> None:
    """A comment header and a bare member line both carry no declaration."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "# Canonical check inventory.\ncheck-bare\ncheck-annotated  # purity: world-reading\n",
        encoding="utf-8",
    )

    audit = _audit(targets=("check-bare", "check-annotated"), repo_root=tmp_path)

    assert audit.undeclared == ("check-bare",), f"audit={audit}"
    assert audit.world_reading == ("check-annotated",), f"audit={audit}"


def test_a_declaration_the_vocabulary_does_not_name_is_a_failure(*, tmp_path: Path) -> None:
    """A typo'd declaration is a registry bug, not a quiet fallback to the default."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-only  # purity: mostly-pure\n", encoding="utf-8"
    )

    result = check_purity.audit_check_purity(targets=("check-local-only",), repo_root=tmp_path)

    assert not is_successful(result), (
        f"a declaration naming neither `tree-pure` nor `world-reading` must reach the failure "
        f"track: folding it into the world-reading default would spell a registry bug the same "
        f"way as a legitimate answer, and nothing would ever name it; got {result}"
    )
    failure = unsafe_perform_io(result.failure())
    assert failure.target == "check-local-only", f"failure={failure}"
    assert failure.value == "mostly-pure", f"failure={failure}"


def test_a_canonical_modules_own_declaration_outranks_the_inventory(*, tmp_path: Path) -> None:
    """A shipped check declares its own purity, so the declaration travels with the library."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-master-ci-green  # purity: tree-pure\n", encoding="utf-8"
    )

    audit = _audit(targets=("check-master-ci-green",), repo_root=tmp_path)

    assert audit.world_reading == ("check-master-ci-green",), (
        f"the module's own declaration is the one that reaches every consuming repository, so "
        f"a consumer's inventory must not be able to demote a shipped check to tree-pure; "
        f"audit={audit}"
    )


def test_an_annotated_module_declaration_is_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CHECK_PURITY: str = "..."` declares exactly what the bare assignment declares."""
    monkeypatch.setattr(check_purity, "_CHECKS_PACKAGE_DIR", tmp_path)
    _ = (tmp_path / "synthetic.py").write_text(
        'CHECK_PURITY: str = "world-reading"\n', encoding="utf-8"
    )

    audit = _audit(targets=("check-synthetic",), repo_root=tmp_path)

    assert audit.world_reading == ("check-synthetic",), f"audit={audit}"


def test_a_module_declaration_that_is_not_a_string_literal_is_malformed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A computed declaration cannot be read statically, so it is not a declaration."""
    monkeypatch.setattr(check_purity, "_CHECKS_PACKAGE_DIR", tmp_path)
    _ = (tmp_path / "synthetic.py").write_text("CHECK_PURITY = 1 + 1\n", encoding="utf-8")

    result = check_purity.audit_check_purity(targets=("check-synthetic",), repo_root=tmp_path)

    assert not is_successful(result), f"got {result}"
    failure = unsafe_perform_io(result.failure())
    assert failure.target == "check-synthetic", f"failure={failure}"


def test_a_module_that_declares_nothing_is_undeclared(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every other module-level statement is passed over, including a near-miss name."""
    monkeypatch.setattr(check_purity, "_CHECKS_PACKAGE_DIR", tmp_path)
    _ = (tmp_path / "synthetic.py").write_text(
        'import sys\n\n_CHECK_PURITY = "tree-pure"\nCHECK_ID = "synthetic"\n', encoding="utf-8"
    )

    audit = _audit(targets=("check-synthetic",), repo_root=tmp_path)

    assert audit.undeclared == ("check-synthetic",), f"audit={audit}"


def test_a_module_that_cannot_be_parsed_is_undeclared_rather_than_pure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable module has made no claim, and the safe reading of no claim is impure."""
    monkeypatch.setattr(check_purity, "_CHECKS_PACKAGE_DIR", tmp_path)
    _ = (tmp_path / "synthetic.py").write_text("def broken(:\n", encoding="utf-8")

    audit = _audit(targets=("check-synthetic",), repo_root=tmp_path)

    assert audit.undeclared == ("check-synthetic",), f"audit={audit}"
