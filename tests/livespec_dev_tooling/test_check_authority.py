"""Mirror of `livespec_dev_tooling.check_authority` — the members a gate Job must not run.

The "What the delegated gate runs" bullet of `SPECIFICATION/contracts.md`, in
its delegated pre-push gate section (ratified v082): a member that declares it
reads an AUTHORIZATION held outside the tree does not run in the gate Job, the
declaration is carried with the member the way its purity declaration is, and a
member with no such declaration runs in the Job.

THE DEFAULT RUNS THE OPPOSITE WAY FROM PURITY'S, which is the one thing a
resolver here can get backwards while looking right. An undeclared member must
stay in the Job, where the whole aggregate runs; reading absence as "needs the
pushing host" would quietly move members off the cluster one at a time, and
nothing would say so.

THE TWO REFUSALS ARE ASSERTED AS REFUSALS, not as empty answers. A malformed
declaration and an unreadable registry both have an obvious wrong spelling —
report nothing, exit zero — and that spelling reads to the aggregate as "no
member needs the pushing host", which is exactly how a ledger-reading member
gets handed back to a pod holding no ledger.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "check_authority.py"
_MODULE_NAME = "livespec_dev_tooling.check_authority"

# The aggregate script that owns the gate Job's member list. The resolver answers
# WHICH members, and this file is what acts on the answer — so the wiring is read
# back out of the file that owns it rather than assumed.
_CHECK_SH = _REPO_ROOT / "scripts" / "just" / "check.sh"

# The one signal that says "this aggregate run IS a delegated gate Job". The gate
# pod's template sets it and nothing else does, which is what keeps the skip from
# firing on a contributor's machine, where the member CAN read its authorization.
_GATE_CONTEXT_GUARD = 'if [[ -n "${LIVESPEC_GATE_CONTEXT:-}" ]]; then'

# This repository's own repo-private member that reads a ledger-held
# authorization — the `approval:workflow-edit` label on a named work item.
_WORKFLOW_EDIT_GUARD = "check-no-workflow-edits"


def _module() -> Any:
    """The module under test, imported here so its ABSENCE is a test failure."""
    return importlib.import_module(_MODULE_NAME)


def _fixture_inventory(*, repo_root: Path, lines: tuple[str, ...]) -> None:
    """Write a consumer's own `check-targets.txt` holding exactly `lines`."""
    _ = (repo_root / "check-targets.txt").write_text(
        "# Canonical check inventory for `just check`.\n" + "".join(f"{line}\n" for line in lines),
        encoding="utf-8",
    )


def _members(*, repo_root: Path) -> tuple[str, ...]:
    """The authority-declaring members of `repo_root`, asserting the read succeeded."""
    resolved = _module().repository_authority_members(repo_root=repo_root)
    assert is_successful(resolved), f"the authority resolution must succeed; got {resolved}"
    return unsafe_perform_io(resolved.unwrap())


def _gate_context_block(*, script: str) -> str:
    """The lines `check.sh` runs ONLY inside a delegated gate Job.

    Delimited by the guard line and the first `fi` at column zero, so a skip
    that drifted out from under the gate-context signal is not found here.
    """
    lines = script.splitlines()
    assert _GATE_CONTEXT_GUARD in lines, f"{_CHECK_SH} must carry {_GATE_CONTEXT_GUARD!r}"
    opened = lines.index(_GATE_CONTEXT_GUARD)
    closed = lines.index("fi", opened)
    return "\n".join(lines[opened + 1 : closed])


def test_a_declaring_member_is_resolved_out_of_the_gate_jobs_run_set(*, tmp_path: Path) -> None:
    """A member declaring an outside-the-tree authorization does not run in the gate Job.

    TWO HALVES, and the second is the one a resolver alone cannot prove. The
    resolver names the declaring member — here a repo-private one carrying the
    `# authority:` annotation on its inventory line, beside a member that
    declares nothing. And the aggregate ACTS on that answer: `check.sh` resolves
    the set and adds it to the run's skip, under the gate pod's own
    `LIVESPEC_GATE_CONTEXT` signal and nowhere else, so the members leave the
    Job's run set exactly where the Job's member list is decided.

    The wiring is read back out of `check.sh` rather than assumed because that
    file IS the decision: a resolver whose answer nothing consumed would report
    the member correctly and still let the pod run it, which is the defect
    measured on gate-livespec-dev-tooling-54f19942138d.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} must exist to resolve authority declarations"

    _fixture_inventory(
        repo_root=tmp_path,
        lines=("check-widget-approval  # authority: ledger", "check-widget-lint"),
    )

    assert _members(repo_root=tmp_path) == ("check-widget-approval",)

    script = _CHECK_SH.read_text(encoding="utf-8")
    guarded = _gate_context_block(script=script)

    assert "livespec_dev_tooling.check_authority members" in guarded
    assert "effective_skip" in guarded
    assert script.count("livespec_dev_tooling.check_authority") == 1


def test_a_declaration_outside_the_vocabulary_refuses_rather_than_reading_as_absent(
    *, tmp_path: Path
) -> None:
    """A typo'd declaration is a registry bug, and must not be spelled like an absent one.

    The whole asymmetry: folded into the runs-in-the-Job default, a mistyped
    declaration would behave exactly like a member that needs no authority, and
    the member would keep failing inside a pod that cannot answer for it — which
    is indistinguishable from the state before this resolver existed. The
    refusal names the member AND the value, because a caller that cannot read a
    declaration has to say which one.
    """
    _fixture_inventory(
        repo_root=tmp_path,
        lines=(
            "check-widget-approval  # authority: beads",
            "check-widget-lint  # authority: ledger",
        ),
    )

    resolved = _module().repository_authority_members(repo_root=tmp_path)

    assert not is_successful(
        resolved
    ), f"a value outside the vocabulary must refuse; got {resolved}"
    malformed = unsafe_perform_io(resolved.failure())
    assert malformed.target == "check-widget-approval"
    assert malformed.value == "beads"
    assert "ledger" in malformed.reason


def test_a_repository_with_no_inventory_declares_no_authority_member(*, tmp_path: Path) -> None:
    """An unreadable inventory yields no members rather than refusing every gate.

    The direction is safe HERE and only here: a repository whose aggregate is
    declared somewhere else entirely has no inventory line that could carry an
    annotation, so there is nothing to misread. Refusing instead would refuse the
    delegated gate of every such consumer on a file this repository's convention
    happens to name.
    """
    assert _members(repo_root=tmp_path) == ()


def test_the_members_subcommand_reports_the_set_and_refuses_a_registry_it_cannot_read(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI `check.sh` reads: one name per line on stdout, and nothing on a refusal.

    Both arms, because the aggregate branches on the exit code and reads the
    names from stdout. A refusal that still printed a partial set would narrow
    the gate on a classification whose remainder was never examined, so the
    failing arm must emit NO names at all.
    """
    module = _module()
    _fixture_inventory(
        repo_root=tmp_path,
        lines=(
            "check-widget-approval  # purity: world-reading  # authority: ledger",
            "check-widget-lint  # purity: tree-pure",
            "check-widget-protection  # authority: forge-admin",
        ),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["check_authority", "members"])

    assert module.main() == 0
    assert capsys.readouterr().out == "check-widget-approval\ncheck-widget-protection\n"

    _fixture_inventory(repo_root=tmp_path, lines=("check-widget-approval  # authority: nonsense",))

    assert module.main() == 1
    refused = capsys.readouterr()
    assert refused.out == ""
    assert "check-widget-approval" in refused.err


def test_this_repositorys_workflow_edit_guard_declares_the_ledger_authorization() -> None:
    """`check-no-workflow-edits` reads a ledger-held authorization, and now says so.

    THE MEMBER THAT PAID FOR THIS WHOLE EXCEPTION. It authorizes a workflow
    change by reading the `approval:workflow-edit` label off a named work item
    through `bd`, and it FAILS CLOSED when it cannot — which is right. A gate pod
    holds neither `bd` nor the ledger credential, so inside the Job it can only
    ever fail closed: measured 2026-10-19 on gate
    `gate-livespec-dev-tooling-54f19942138d`, which refused an authorized tree
    carrying its label with "the ledger-held authorization could not be
    evaluated -- FAILING CLOSED". The verdict was correct about the pod and
    wrong about the tree, and no credential may be added to the Job to fix it.

    DECLARED ON ITS OWN INVENTORY LINE, because the member exists only in this
    repository — there is no shipped `checks/<slug>.py` to carry a module
    constant, exactly as its purity declaration already rides that same line.
    Asserted through the live resolution rather than by reading the file,
    because the resolution is what the delegated gate acts on.
    """
    assert _WORKFLOW_EDIT_GUARD in _members(repo_root=_REPO_ROOT)
