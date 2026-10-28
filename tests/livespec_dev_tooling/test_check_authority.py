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

AND AN EMPTY ANSWER IS EXACTLY WHAT A REPOSITORY DECLARING NO INVENTORY GOT.
The resolver read `check-targets.txt` and nothing else, so six of this fleet's
eight members — every one that declares its aggregate only in its justfile —
answered that no member reads an authorization held outside the tree. That is
the same wrong answer the refusals above are shaped to avoid, arriving through a
missing file instead of a bad declaration, and it is measured: on 2026-10-24
cluster gate Job `gate-livespec-overseer-tpfd2` ran livespec-overseer's master
green on every member but `check-branch-protection-alignment`, which got HTTP
403 on the gate forge credential. So the resolver falls back to the members the
repository's own `just check` aggregate SELECTS, and the tests below assert both
that fallback and the precedence that keeps an inventory-carrying repository
answering exactly as it did.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from returns.pipeline import is_successful
from returns.result import Success
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling._gate_host_authority import run_host_authority_members
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult

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

# The SHIPPED check that reads the forge's repository administration settings,
# and a shipped check that reads no authority at all — the two sides of the
# module-declaration precedence rule.
_BRANCH_PROTECTION = "check-branch-protection-alignment"
_SHIPPED_TREE_PURE = "check-file-lloc"

# The empty tree's hash — a real git object name, standing for the committed
# tree a delegated push hands both halves of its verdict.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class _CannedHost:
    """Every `just <member>` a delegated push issues here, answered with no host.

    Records the argv AND the working directory, because the contract's claim is
    that the member ran on the pushing host IN THE PUSHING WORKTREE — a member
    invoked somewhere else would read another tree and answer about it.
    """

    def __init__(self) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.cwds: list[Path] = []

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        self.argvs.append(tuple(argv))
        self.cwds.append(cwd)
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))


def _module() -> Any:
    """The module under test, imported here so its ABSENCE is a test failure."""
    return importlib.import_module(_MODULE_NAME)


def _fixture_inventory(*, repo_root: Path, lines: tuple[str, ...]) -> None:
    """Write a consumer's own `check-targets.txt` holding exactly `lines`."""
    _ = (repo_root / "check-targets.txt").write_text(
        "# Canonical check inventory for `just check`.\n" + "".join(f"{line}\n" for line in lines),
        encoding="utf-8",
    )


def _fixture_justfile_aggregate(*, repo_root: Path, slugs: tuple[str, ...]) -> None:
    """Write a consumer's own `just check` aggregate selecting exactly `slugs`.

    The shape every no-inventory member of this fleet carries: a bare `check:`
    recipe holding a one-slug-per-line `targets=(...)` array. Written rather
    than copied from a sibling clone so the fixture states what it depends on.
    """
    lines = [
        "check:",
        "    #!/usr/bin/env bash",
        "    set -uo pipefail",
        "    targets=(",
        *(f"        {slug}" for slug in slugs),
        "    )",
        '    for target in "${targets[@]}"; do just "${target}"; done',
    ]
    _ = (repo_root / "justfile").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def test_the_shipped_branch_protection_check_declares_the_forge_admin_authorization(
    *, tmp_path: Path
) -> None:
    """`check-branch-protection-alignment` reads the forge's admin settings, and now says so.

    THE OTHER MEASURED VICTIM, and the one that proves the declaration has to
    SHIP. livespec's first delegated run failed this member with HTTP 403 on the
    gate forge credential: the member reads a repository's live branch-protection
    settings, which needs admin scope, and the gate Job is handed a token that
    deliberately has none.

    SO THE DECLARATION IS A MODULE CONSTANT, not an inventory annotation. This
    member is one this library SHIPS, so its declaration has to reach every
    consuming repository with the wheel — asserted in BOTH vantages here: this
    repository's own inventory resolves it, and so does a consumer whose
    inventory line carries no annotation at all. An annotation would have had to
    be written into nine repositories by hand, and the one that was missed would
    fail closed in its pod exactly as before.
    """
    assert _BRANCH_PROTECTION in _members(repo_root=_REPO_ROOT)

    _fixture_inventory(repo_root=tmp_path, lines=(_BRANCH_PROTECTION, "check-widget-lint"))

    assert _members(repo_root=tmp_path) == (_BRANCH_PROTECTION,)


def test_an_inventory_annotation_cannot_demote_a_shipped_checks_own_declaration(
    *, tmp_path: Path
) -> None:
    """A shipped module's declaration OUTRANKS the consumer's inventory line.

    The precedence is load-bearing rather than arbitrary, and it runs the same
    way `check_purity`'s does: the module declaration is the one that reaches
    every consuming repository, so one repository's inventory must not be able
    to move a shipped member off the cluster — or onto it — while the library
    says otherwise everywhere else. `check-file-lloc` ships a module and
    declares no authority, so it runs in the Job however its line is annotated.
    """
    _fixture_inventory(repo_root=tmp_path, lines=(f"{_SHIPPED_TREE_PURE}  # authority: ledger",))

    assert _members(repo_root=tmp_path) == ()


def test_an_annotated_module_declaration_is_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both spellings say the same thing, so both are accepted.

    A resolver that read only the bare assignment would report a correctly
    declared module as declaring nothing — and that error runs in the unsafe
    direction here, handing an authority-reading member back to a pod holding no
    authority.
    """
    monkeypatch.setattr(_module(), "_CHECKS_PACKAGE_DIR", tmp_path, raising=False)
    _ = (tmp_path / "widget_protection.py").write_text(
        'CHECK_AUTHORITY: str = "forge-admin"\n', encoding="utf-8"
    )
    _fixture_inventory(repo_root=tmp_path, lines=("check-widget-protection",))

    assert _members(repo_root=tmp_path) == ("check-widget-protection",)


def test_a_module_declaration_that_is_not_a_string_literal_is_malformed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A computed declaration LOOKS declared and cannot be read, so it is convicted.

    Reading it would mean importing the module, which a resolution on the
    pre-push path must never do. Treating it as absent would be worse than
    having no declaration at all, because the author believes the member has
    one.
    """
    monkeypatch.setattr(_module(), "_CHECKS_PACKAGE_DIR", tmp_path, raising=False)
    _ = (tmp_path / "widget_protection.py").write_text(
        "CHECK_AUTHORITY = 1 + 1\n", encoding="utf-8"
    )
    _fixture_inventory(repo_root=tmp_path, lines=("check-widget-protection",))

    resolved = _module().repository_authority_members(repo_root=tmp_path)

    assert not is_successful(resolved), f"a computed declaration must refuse; got {resolved}"
    assert unsafe_perform_io(resolved.failure()).target == "check-widget-protection"


def test_a_module_that_cannot_be_parsed_declares_nothing_rather_than_refusing_every_gate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unparseable module has made NO claim, and the safe reading of no claim is the Job.

    The direction matters and it is the opposite of the malformed-DECLARATION
    case above. There, something was written and could not be acted on, which is
    a registry bug. Here nothing was written at all — the file does not parse, so
    there is no declaration to misread — and the member keeps the default every
    undeclared member has: it runs in the gate Job, where the whole aggregate
    runs. Refusing instead would make one syntactically broken check module
    refuse every delegated push in the fleet.

    Asserted beside a module in the SAME directory that does declare, so a
    resolver that had simply stopped reading modules altogether fails here.
    """
    monkeypatch.setattr(_module(), "_CHECKS_PACKAGE_DIR", tmp_path, raising=False)
    _ = (tmp_path / "widget_broken.py").write_text("def broken(:\n", encoding="utf-8")
    _ = (tmp_path / "widget_protection.py").write_text(
        'CHECK_AUTHORITY = "forge-admin"\n', encoding="utf-8"
    )
    _fixture_inventory(repo_root=tmp_path, lines=("check-widget-broken", "check-widget-protection"))

    assert _members(repo_root=tmp_path) == ("check-widget-protection",)


def test_a_consumer_with_no_inventory_resolves_the_members_its_aggregate_selects(
    *, tmp_path: Path
) -> None:
    """A repository declaring no inventory still names its authority-reading members.

    THE MEASURED DEFECT. The resolver read the consumer's `check-targets.txt`
    and nothing else, so a repository that declares its aggregate only in the
    justfile answered that NO member reads an authorization held outside the
    tree — the one answer that puts every such member back inside a pod holding
    none. On v1.127.0 `check_authority members` printed nothing in
    livespec-overseer and in livespec-orchestrator-beads-fabro, neither of which
    carries that file, while printing two names in this repository, which does.
    Measured 2026-10-24 01:41-01:45Z: cluster gate Job
    `gate-livespec-overseer-tpfd2` ran master e4a81525 green on every member
    except `check-branch-protection-alignment`, which got
    `gh: Resource not accessible by personal access token (HTTP 403)` and then
    refused to report a pass it had not verified. The verdict was right about
    the pod and wrong about the tree, and the fix may not hand the Job an
    admin-scoped forge credential — the authority stays with the host that holds
    it.

    SO THE AGGREGATE ITSELF IS THE FALLBACK, read from the one place such a
    repository does declare its check set: the literal `targets=(...)` array of
    its bare `check:` recipe, which is the same surface
    `canonical_recipe_fidelity` and the fleet's aggregate-wiring rows already
    read. `check-file-lloc` sits beside the declaring member here so a resolver
    that simply named every selected member fails this assertion rather than
    passing it by accident.
    """
    _fixture_justfile_aggregate(repo_root=tmp_path, slugs=(_SHIPPED_TREE_PURE, _BRANCH_PROTECTION))

    assert not (
        tmp_path / "check-targets.txt"
    ).exists(), "the whole point of this consumer is that it declares no inventory"
    assert _members(repo_root=tmp_path) == (_BRANCH_PROTECTION,)


def test_a_delegated_gate_of_an_inventory_free_consumer_runs_that_member_on_the_pushing_host(
    *, tmp_path: Path
) -> None:
    """Both halves of such a repository's delegated verdict, each asserted where it happens.

    The gate Job MUST NOT run the member. Asserted at the place the Job's member
    list is decided — `scripts/just/check.sh`, which resolves the declaring
    members and adds them to the run's skip, and does so only under the gate
    pod's own `LIVESPEC_GATE_CONTEXT` signal. A test cannot start a pod and does
    not have to: the skip is computed by shipped code from the committed
    declarations, so what the pod will not run is decidable here from the same
    files the pod reads.

    The pushing host MUST run it. Asserted as an INVOCATION through the gate
    client's own command seam — `just check-branch-protection-alignment`, in the
    pushing worktree — because "it ran on the pushing host with the host's own
    credentials" is a fact about a command, not about a message. The member that
    declares nothing is NOT invoked here: it stays in the Job, which is the
    direction a careless fallback drains, moving members onto the pushing host
    one at a time until the cluster gates nothing.
    """
    _fixture_justfile_aggregate(repo_root=tmp_path, slugs=(_SHIPPED_TREE_PURE, _BRANCH_PROTECTION))
    host = _CannedHost()

    ran = run_host_authority_members(repo_root=tmp_path, tree_hash=_TREE, runner=host)

    assert tuple(one.member for one in ran) == (_BRANCH_PROTECTION,)
    assert tuple(one.returncode for one in ran) == (0,)
    assert host.argvs == [("just", _BRANCH_PROTECTION)]
    assert host.cwds == [tmp_path]

    guarded = _gate_context_block(script=_CHECK_SH.read_text(encoding="utf-8"))

    assert "livespec_dev_tooling.check_authority members" in guarded
    assert "effective_skip" in guarded


def test_a_consumer_carrying_an_inventory_is_resolved_from_it_and_not_from_its_justfile(
    *, tmp_path: Path
) -> None:
    """The inventory keeps PRECEDENCE, so a repository that has one answers as it did.

    The fallback is reached only in the inventory's ABSENCE. A repository that
    carries `check-targets.txt` is the one surface that can declare a
    repo-private member's authority at all — this repository's own
    `check-no-workflow-edits` is declared on its inventory line, because no
    shipped `checks/<slug>.py` exists to carry a module constant — so a resolver
    that preferred the justfile would silently drop every such declaration while
    still answering plausibly.

    Asserted with the two surfaces DISAGREEING, which is the only arrangement
    that can tell them apart: the inventory declares a repo-private member and
    the justfile aggregate selects a shipped forge-admin one instead.
    """
    _fixture_inventory(
        repo_root=tmp_path,
        lines=("check-widget-approval  # purity: world-reading  # authority: ledger",),
    )
    _fixture_justfile_aggregate(repo_root=tmp_path, slugs=(_BRANCH_PROTECTION,))

    assert _members(repo_root=tmp_path) == ("check-widget-approval",)


def test_an_undeclared_member_the_aggregate_selects_still_runs_in_the_gate_job(
    *, tmp_path: Path
) -> None:
    """Absence of a declaration still means the Job, read through the fallback too.

    THE DEFAULT RUNS THE OPPOSITE WAY FROM PURITY'S and the fallback must not
    quietly invert it. `check-file-lloc` ships a module that declares no
    authority; `check-widget-lint` ships none at all and carries no annotation,
    because a justfile-declared aggregate has no annotation surface. Both keep
    the default every undeclared member has — they run in the gate Job, where
    the whole aggregate runs — so the resolver's answer here is EMPTY.
    """
    _fixture_justfile_aggregate(repo_root=tmp_path, slugs=(_SHIPPED_TREE_PURE, "check-widget-lint"))

    assert _members(repo_root=tmp_path) == ()


def test_an_aggregate_this_reader_cannot_enumerate_declares_no_authority_member(
    *, tmp_path: Path
) -> None:
    """A justfile whose aggregate shape this reader does not understand declares nothing.

    The same direction `_inventory_lines` takes on an absent file, and for the
    same reason: a repository whose aggregate this reader cannot enumerate has
    no selected member that could carry a declaration, so there is nothing to
    misread. Refusing instead would refuse the delegated gate of every consumer
    whose aggregate is shaped some other way — a repository with no bare
    `check:` recipe at all, and one whose recipe carries no literal
    `targets=(...)` array.
    """
    _ = (tmp_path / "justfile").write_text("lint:\n    uv run ruff check\n", encoding="utf-8")

    assert _members(repo_root=tmp_path) == ()

    _ = (tmp_path / "justfile").write_text("check:\n    uv run just lint\n", encoding="utf-8")

    assert _members(repo_root=tmp_path) == ()


def test_a_justfile_only_consumer_resolves_the_workflow_edit_guard_as_a_ledger_member(
    *, tmp_path: Path
) -> None:
    """`check-no-workflow-edits` is named from its pack identity, not from an inventory.

    THE MEASURED DEFECT. The guard ships as a worktree-pack SHELL script, so it
    has no `checks/<slug>.py` to carry a `CHECK_AUTHORITY` constant, and a
    repository with only a justfile aggregate has no inventory line to annotate.
    Measured 2026-10-28 on livespec-runtime PR 787: an authorized workflow edit
    failed gate Job `gate-livespec-runtime-k77pn` with "the ledger-held
    authorization could not be evaluated -- FAILING CLOSED", and the same class
    failed `gate-livespec-dev-tooling-54f19942138d` on 2026-10-19. Both verdicts
    were right about the pod and wrong about the tree.

    SO THE LIBRARY DECLARES IT, for every consumer, the way a shipped module's
    constant does, and the declaration OUTRANKS an inventory line: an
    unannotated inventory line must not put the guard back in a pod that holds
    no ledger. `check-file-lloc` sits beside it so a resolver naming every
    selected member fails rather than passing by accident.
    """
    _fixture_justfile_aggregate(
        repo_root=tmp_path, slugs=(_SHIPPED_TREE_PURE, _WORKFLOW_EDIT_GUARD)
    )

    assert _members(repo_root=tmp_path) == (_WORKFLOW_EDIT_GUARD,)

    inventoried = tmp_path / "inventoried"
    inventoried.mkdir()
    _fixture_inventory(
        repo_root=inventoried, lines=(f"{_WORKFLOW_EDIT_GUARD}  # purity: world-reading",)
    )

    assert _members(repo_root=inventoried) == (_WORKFLOW_EDIT_GUARD,)


def test_a_delegated_gate_of_a_justfile_only_consumer_runs_the_workflow_edit_guard_on_the_host(
    *, tmp_path: Path
) -> None:
    """The pushing host runs the guard against the ledger; the Job's skip is computed from the same names.

    The host half is asserted as an INVOCATION through the gate client's command
    seam, in the pushing worktree. The Job half is decided by the same
    resolution `scripts/just/check.sh` feeds into its skip under the gate pod's
    own `LIVESPEC_GATE_CONTEXT` signal, so the member the host runs is exactly
    the member the Job leaves out.
    """
    _fixture_justfile_aggregate(
        repo_root=tmp_path, slugs=(_SHIPPED_TREE_PURE, _WORKFLOW_EDIT_GUARD)
    )
    host = _CannedHost()

    ran = run_host_authority_members(repo_root=tmp_path, tree_hash=_TREE, runner=host)

    assert tuple(one.member for one in ran) == (_WORKFLOW_EDIT_GUARD,)
    assert host.argvs == [("just", _WORKFLOW_EDIT_GUARD)]
    assert host.cwds == [tmp_path]

    guarded = _gate_context_block(script=_CHECK_SH.read_text(encoding="utf-8"))

    assert "livespec_dev_tooling.check_authority members" in guarded
