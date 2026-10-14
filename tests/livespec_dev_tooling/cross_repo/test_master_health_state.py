"""Tests for the master-health reconciler's recorded-state vocabulary.

This module owns the acceptance assertion that the reconciler "reaches its
decisions with no LLM call, reading only GitHub state and committed
configuration" (work-item `livespec-dev-tooling-hrpcgl`, child C1 of plan
`red-master-self-healing`).

THE CLOSURE TEST IS WRITTEN AS A GLOB, NOT A FIXED LIST. It walks every
`master_health_*.py` module in the package, so a sibling added later inherits
the no-LLM, no-network guarantee WITHOUT anyone remembering to extend this
file. A fixed list is the shape that rots: the module it fails to name is
exactly the one that reintroduces the call this assertion exists to forbid.

The modules are read as SOURCE and walked as an AST rather than imported and
introspected. An import proves only that the module did not call out AT import
time; the AST shows what it could call at decision time, which is the property
being asserted.
"""

from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path

from livespec_dev_tooling.cross_repo.master_health_state import (
    ReconcileConfig,
    ReconcileState,
)

_PACKAGE = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "cross_repo"

# Every module that could reach a network socket, spawn a process, or call a
# model. The decision path may import NONE of them. `subprocess` is on the list
# because a `gh` spawn is still a forge call, and `urllib`/`http`/`socket`
# because the two release-lane runners in this same package reach the REST API
# through exactly those — they are the shape a reconciler would drift into.
_FORBIDDEN_ROOTS = frozenset(
    {
        "anthropic",
        "http",
        "httpx",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
)


def _imported_roots(*, source: str) -> set[str]:
    """The top-level package name of every import in `source`."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_import_walk_sees_every_import_form_a_module_can_use() -> None:
    """The closure assertion is only as strong as the walk underneath it.

    A walk blind to one import form would report the decision path clean while
    the forbidden client sat in the blind spot — a VACUOUS pass, which is worse
    than no assertion at all because it reads as proof. The relative form is
    included because it carries no module name and must not crash the walk.
    """
    roots = _imported_roots(
        source="import socket.abc\nfrom urllib import request\nfrom . import sibling\n"
    )

    assert roots == {"socket", "urllib"}


def test_the_state_vocabulary_module_exists_at_its_expected_path() -> None:
    """The decision's input vocabulary is a module of its own, not inlined.

    Asserted first and on the PATH so this file's Red fails on a genuine
    assertion rather than at collection time.
    """
    assert (_PACKAGE / "master_health_state.py").is_file()


def test_no_master_health_module_can_reach_a_network_socket_or_a_model() -> None:
    """The no-LLM rule, enforced over the whole decision path by construction.

    The reconciler's verdicts must be reproducible from recorded state alone.
    An import of any client here would make a decision depend on something no
    replay can reproduce and no reviewer can audit.
    """
    modules = sorted(_PACKAGE.glob("master_health_*.py"))

    assert modules, "no master_health_* module found — the glob would pass vacuously"
    for module in modules:
        roots = _imported_roots(source=module.read_text(encoding="utf-8"))
        assert not (roots & _FORBIDDEN_ROOTS), (
            f"{module.name} imports {sorted(roots & _FORBIDDEN_ROOTS)} — "
            "the decision path must reach no socket, process or model"
        )


def test_the_decision_inputs_are_frozen_so_a_decision_cannot_mutate_them() -> None:
    """A reconcile run reads state; it never edits its own inputs.

    Frozen is what makes "GitHub is the state" true in the code rather than
    merely intended: a step cannot stash a decision back onto the state it was
    handed and have a later rule read it as forge truth.
    """
    for record in (ReconcileState, ReconcileConfig):
        assert is_dataclass(record)
        params = record.__dataclass_params__  # pyright: ignore[reportAttributeAccessIssue]
        assert params.frozen is True
        assert all(field.kw_only for field in fields(record))


def test_committed_configuration_carries_the_branch_and_the_outage_markers() -> None:
    """The two things the decision may read besides forge state.

    `target_branch` is a parameter rather than a hardcoded `master` so the
    scheduled drill can prove the revert path on a throwaway branch, and the
    outage markers are committed text rather than a model's judgement of a
    failure log.
    """
    declared = {field.name for field in fields(ReconcileConfig)}

    assert declared == {"target_branch", "infra_outage_markers"}
