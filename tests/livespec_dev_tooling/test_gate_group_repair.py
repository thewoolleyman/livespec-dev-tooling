"""Re-running a gate under the credential's owning group — the host facts and the re-exec.

Nothing here reads `/etc/ci-runner`, changes a group, or spawns `sg`. The three
facts the repair rests on are read through `gates_kubeconfig_path`, so a fixture
credential under `tmp_path` answers them; the DECISION is a pure function over a
record of those facts; and the re-execution's own seam is `subprocess.run`,
stubbed exactly as `test_gate_remote_invocation` stubs the client's.

WHY THE DECISION IS A PURE FUNCTION OVER A RECORD rather than four probes read
inside it: the state this module exists for CANNOT be built in this suite. It
needs a credential the current process cannot read while the group database
lists the current user in its owning group — and this suite runs as root in the
factory sandbox, where a mode-0000 file is still perfectly readable, so the
unreadable half is unreachable here at any permission bit. A record lets every
shape the decision must REFUSE be asserted directly, and leaves the probes
themselves asserted against a real file whose facts the sandbox can produce.
"""

from __future__ import annotations

import dataclasses
import grp
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV
from livespec_dev_tooling.gate_group_repair import (
    GATE_MODULE,
    GATES_GROUP_REEXEC_ENV,
    SG,
    GateGroupFacts,
    gate_group_facts,
    gates_group_reexec_argv,
    group_repair_group,
    reexecuted_gates_group,
    repairable_group,
    run_under_gates_group,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


# The one shape that repairs: the credential is there and unreadable HERE, the
# group database lists this user in the group that owns it, and this PROCESS's
# group list does not carry that group. Every refusal below is this record with
# exactly one fact moved, so each test differs from the repair by one fact.
_REPAIRABLE = GateGroupFacts(
    readable=False,
    owning_group="gates-client",
    user_is_a_member=True,
    process_carries_it=False,
)


def _a_credential(*, root: Path) -> Path:
    """A stand-in gates kubeconfig — never a real credential."""
    credential = root / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    return credential


def test_a_process_lacking_the_owning_group_of_a_credential_it_may_read_repairs() -> None:
    """The VPS shape, named: an ELIGIBLE host whose pushing process lacks the group.

    `sg` grants nothing a fresh login would not — the group database already
    lists the user, and `sg` refuses a non-member — so this conjunction is a
    repair rather than an escalation.
    """
    assert repairable_group(facts=_REPAIRABLE) == "gates-client"


def test_no_other_shape_repairs() -> None:
    """Each refusal, with its reason, as one fact moved off the repair above.

    A READABLE credential needs no repair. A path with no owning group is no
    credential at all — an absent file, or one the group database cannot resolve
    — so there is no group to re-run under. A user the group database does not
    list is on an INELIGIBLE host, and `sg` would refuse them anyway. And a
    process that ALREADY carries the group yet still cannot read the file is not
    missing a group: the mode denies group read, so re-executing changes nothing
    and would loop.
    """
    for fact, value in (
        ("readable", True),
        ("owning_group", None),
        ("user_is_a_member", False),
        ("process_carries_it", True),
    ):
        refused = dataclasses.replace(_REPAIRABLE, **{fact: value})
        assert repairable_group(facts=refused) is None, fact


def test_the_facts_name_the_group_that_owns_the_credential_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probes, against a real file — measured, not restated.

    The expected group is read back through the group database rather than
    hard-coded, because this suite's own host decides it: the fixture is created
    with the running process's primary group, whichever that is. A user IS a
    member of their own primary group and a process DOES carry it, so the two
    membership facts are sound on any host that can run this suite.
    """
    credential = _a_credential(root=tmp_path)
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    owner = grp.getgrgid(credential.stat().st_gid)

    facts = gate_group_facts()

    assert facts.readable is True
    assert facts.owning_group == owner.gr_name
    assert facts.user_is_a_member is True
    assert facts.process_carries_it is True
    assert repairable_group(facts=facts) is None


def test_an_absent_credential_has_no_owning_group(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory-sandbox case: nothing to own, so nothing to re-run under."""
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path / "absent.kubeconfig"))

    facts = gate_group_facts()

    assert facts == GateGroupFacts(
        readable=False,
        owning_group=None,
        user_is_a_member=False,
        process_carries_it=False,
    )


def test_a_directory_at_the_credential_path_has_no_owning_group(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory is readable and is not a credential — the same reading the probe takes.

    Left unguarded this is the one shape that could invent a repair out of
    nothing: a directory's group resolves, the pushing user may well be in it,
    and the read still fails because a directory is not a kubeconfig.
    """
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path))

    assert gate_group_facts().owning_group is None


def test_a_gid_the_group_database_cannot_resolve_names_no_owning_group(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An owner gid with no group entry — a credential copied off another host."""

    def _unresolvable(_gid: int) -> grp.struct_group:
        raise KeyError(_gid)

    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(_a_credential(root=tmp_path)))
    monkeypatch.setattr(grp, "getgrgid", _unresolvable)

    assert gate_group_facts().owning_group is None


def test_a_uid_the_password_database_cannot_resolve_is_no_members_of_anything(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user with no passwd entry cannot be shown to be a member, so nothing repairs."""

    def _unresolvable(_uid: int) -> pwd.struct_passwd:
        raise KeyError(_uid)

    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(_a_credential(root=tmp_path)))
    monkeypatch.setattr(pwd, "getpwuid", _unresolvable)

    assert gate_group_facts().user_is_a_member is False


def test_the_reexec_argv_runs_this_gate_through_the_absolute_sg_path() -> None:
    """`/usr/bin/sg`, spelled absolutely, because a bare `sg` is a different program.

    On the VPS `sg` resolves to `ast-grep`, which would take the gate's argv as
    a code-search pattern and answer something — so the spelling is load-bearing
    rather than stylistic.
    """
    argv = gates_group_reexec_argv(group="gates-client")

    assert argv[:3] == ["/usr/bin/sg", "gates-client", "-c"]
    assert SG == "/usr/bin/sg"
    assert argv[3] == f"{sys.executable} -m {GATE_MODULE} run"
    assert GATE_MODULE == "livespec_dev_tooling.gate_remote_delegate"


def test_a_first_run_carries_no_sentinel_and_a_re_executed_one_names_its_group(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sentinel carries the GROUP, not a flag.

    The child is a fresh process, so the environment is the only thing that can
    tell it that it IS the re-executed run; and when it still cannot read the
    credential the diagnostic has to name the group that was tried, which a
    boolean cannot.
    """
    monkeypatch.delenv(GATES_GROUP_REEXEC_ENV, raising=False)
    assert reexecuted_gates_group() is None

    monkeypatch.setenv(GATES_GROUP_REEXEC_ENV, "")
    assert reexecuted_gates_group() is None

    monkeypatch.setenv(GATES_GROUP_REEXEC_ENV, "gates-client")
    assert reexecuted_gates_group() == "gates-client"


def _sg_at(monkeypatch: pytest.MonkeyPatch, *, resolved: str | None) -> None:
    """Make `shutil.which` answer for `/usr/bin/sg` the way the host under test would.

    Patching `shutil.which` rather than shadowing PATH, for the reason
    `test_gate_remote_invocation` records: a shim directory only works if it is
    the WHOLE path, and a fixture a real binary can defeat cannot fail.
    """

    def _answer(_program: str) -> str | None:
        return resolved

    monkeypatch.setattr(shutil, "which", _answer)


def test_the_reexecution_hands_the_child_the_sentinel_and_answers_its_exit_status(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child's exit status IS the answer: its verdict is the one that counts."""
    _sg_at(monkeypatch, resolved=SG)
    seen: dict[str, object] = {}

    def _fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        seen["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=7)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    assert run_under_gates_group(group="gates-client") == 7
    assert seen["argv"] == gates_group_reexec_argv(group="gates-client")
    handed = seen["env"]
    assert isinstance(handed, dict)
    assert handed[GATES_GROUP_REEXEC_ENV] == "gates-client"


def test_an_absent_sg_is_a_reexecution_that_never_started(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host with no `sg` answers NOTHING, never a fabricated exit code."""
    _sg_at(monkeypatch, resolved=None)

    assert run_under_gates_group(group="gates-client") is None


def test_a_spawn_that_raises_is_a_reexecution_that_never_started(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `OSError` out of the spawn must not propagate through a git hook."""
    _sg_at(monkeypatch, resolved=SG)

    def _explode(_argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", _explode)

    assert run_under_gates_group(group="gates-client") is None


def test_the_repair_group_is_named_only_for_a_first_run_of_an_opted_in_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two gates before the host is ever read, and both are about silence.

    A repository that has NOT opted in must not be told anything about this
    host's groups — that is the path every push takes today. And a run that is
    ALREADY the re-executed child must never re-execute again: `sg` succeeded
    and the read still failed, so the group was not the problem and looping
    would only hide it.
    """
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path / "absent.kubeconfig"))
    monkeypatch.delenv(GATES_GROUP_REEXEC_ENV, raising=False)

    assert group_repair_group(opted_in=False) is None
    assert group_repair_group(opted_in=True) is None

    monkeypatch.setenv(GATES_GROUP_REEXEC_ENV, "gates-client")
    assert group_repair_group(opted_in=True) is None


def test_the_process_group_list_counts_the_real_group_id_too(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`os.getgroups()` MAY omit the caller's own group id, and POSIX permits that.

    Read alone it would report a process as NOT carrying the group that owns a
    file it created — which is the repair's own trigger, so the gate would
    re-execute under a group it already has and loop. The real group id is
    unioned in for exactly that reason.
    """
    credential = _a_credential(root=tmp_path)
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    monkeypatch.setattr(os, "getgroups", list)

    assert gate_group_facts().process_carries_it is True
