"""Consumer-tier: the `## Delegated pre-push gate` contract and its three scenarios.

The registered coverage for the delegated pre-push gate section of this
repository's `SPECIFICATION/contracts.md` and the three
`SPECIFICATION/scenarios.md` scenarios that exercise it: an opted-in push from
an INELIGIBLE host gating locally, an opted-in push from an ELIGIBLE host
completing on a green cluster verdict, and an opted-in push being REFUSED when
no verdict arrives.

NOTHING HERE REACHES A CLUSTER, A MIRROR OR A HOST. The gate client's only door
to the world is its `GateCommandRunner` seam, so a canned runner IS the cluster;
the opt-in is read out of a `pyproject.toml` written into `tmp_path`; host
eligibility is read from a stand-in credential file under `tmp_path` via the
same `GATES_KUBECONFIG` override the shipped wrapper honours.

EACH SCENARIO IS PROVEN IN TWO ARMS, BECAUSE THE SEAM BETWEEN THEM IS AN EXIT
CODE. A push runs `check-pre-push.sh`, which asks the shipped module one
question and branches on its exit status and nothing else. So the DECISION arm
drives `gate_remote_delegate.main()` in-process (which exit code, and what it
prints), and the RECIPE arm drives the real `check-pre-push.sh` against stub
`uv` and `just` executables that record what was invoked (which branch that exit
code takes). Splitting them is what keeps the suite off a Python subprocess,
which `check-tests-no-subprocess-spawn` forbids for good reason — a spawned
child under `pytest --cov` self-instruments and races the parallel dispatcher.

WHY THE RECIPE ARM ASSERTS ON INVOCATIONS RATHER THAN ON OUTPUT. "The local
`just check` fall-through MUST run" and "a gate Job MUST NOT be submitted" are
claims about what the script RUNS. A fall-through that had quietly started
delegating would still print something reassuring; only the invocation list can
tell the two apart.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV, GATES_WRAPPER
from livespec_dev_tooling.gate_remote_delegate import (
    GATE_CHECK_SUITE_FALL_THROUGH,
    delegated_gate_enabled,
    delegated_gate_selected,
    main,
    run_delegated_gate,
)
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GATE_PASSED

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_PUSH = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"

# The empty tree's hash — a real git object name, and the one every canned
# `rev-parse HEAD^{tree}` below answers with.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
# The Job-name PREFIX the manifest asks the cluster to build on, and the name the
# API server builds. A gate Job is named by the API server rather than by the
# pushing host (livespec-dev-tooling-44fglo), so a tree whose previous gate Job
# still exists can be gated again — the client reads the assigned name back off
# its own submit, which is what the canned cluster below answers it with.
_JOB_PREFIX = f"gate-widget-{_TREE[:12]}"
_JOB = f"{_JOB_PREFIX}-x7k2q"
_MANIFEST = f"apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: {_JOB_PREFIX}-\n"

# The namespace the gate Job runs in, per the contract section.
_NAMESPACE = "gates"

# A Job that has reported no condition yet — what a real poll gets while Kueue is
# still admitting the gate — and then the one condition that means the gated
# aggregate exited zero inside the pod.
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})

# `kubectl`'s own wording when the API server cannot be reached at all. The
# scenario's Given, verbatim enough that a reader recognises it in a log.
_UNREACHABLE = "Unable to connect to the server: dial tcp 10.0.0.1:6443: i/o timeout"


def _opt_in(*, repo_root: Path) -> None:
    """Write the one `pyproject.toml` shape that switches delegation on."""
    _ = (repo_root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )


def _an_eligible_host(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the credential at a readable stand-in — never a real credential.

    Eligibility is made true by PRESENCE here rather than by a permission bit
    because this suite runs as root in the factory sandbox, where a mode-0000
    fixture is still readable: a bit-based fixture would answer one way under
    root and the other under a login user.
    """
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    return credential


def _an_ineligible_host(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A host holding no gates credential — a factory sandbox, or a fresh laptop."""
    absent = tmp_path / "absent.kubeconfig"
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(absent))
    return absent


# --- the canned cluster ----------------------------------------------------


class _CannedCluster:
    """Every command one delegated push issues, answered without a world.

    `unreachable` makes every CLUSTER command fail the way an unreachable API
    server does, while the local `git` and renderer steps still succeed — which
    is the scenario's Given: the host is fine, the cluster is not.
    """

    def __init__(self, *, unreachable: bool = False) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._unreachable = unreachable
        self._polls = 0

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        self.argvs.append(tuple(argv))
        if argv[0] == GATES_WRAPPER:
            return self._cluster(polling="get" in argv, submitting="create" in argv)
        if "rev-parse" in argv:
            return Success(GateCommandResult(returncode=0, stdout=f"{_TREE}\n", stderr=""))
        if argv[0] == str(_RENDERER):
            return Success(GateCommandResult(returncode=0, stdout=_MANIFEST, stderr=""))
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    def _cluster(self, *, polling: bool, submitting: bool) -> GateCommandOutcome:
        """One cluster command: refused outright, or answered on the poll sequence.

        THE UNREACHABLE DECISION IS MADE ONCE HERE, for every cluster command the
        run issues, submit included — a second copy of it beside the submit is a
        second place a lost cluster could be forgotten.

        The SUBMIT answers as `kubectl create --output name` does: the created Job
        NAMES ITSELF BACK, which is the only way the run learns which Job is its
        own, since the manifest carries `generateName` and the name does not
        exist until the API server assigns it (livespec-dev-tooling-44fglo).

        Only a POLL advances the sequence. Counting every cluster command would
        let the submit consume the not-admitted-yet answer, and the first poll
        would then read a terminal condition — quietly removing the wait this
        scenario's "only after that Job reports a green verdict" is about.
        """
        if self._unreachable:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=_UNREACHABLE))
        if submitting:
            return Success(GateCommandResult(returncode=0, stdout=f"job.batch/{_JOB}\n", stderr=""))
        if not polling:
            return Success(GateCommandResult(returncode=0, stdout="", stderr=""))
        self._polls += 1
        # Not admitted yet, then complete — no gate is terminal on its first poll,
        # and this is the only way the run's wait is exercised at all.
        return Success(
            GateCommandResult(
                returncode=0,
                stdout=_JOB_ADMITTING if self._polls == 1 else _JOB_COMPLETE,
                stderr="",
            )
        )

    def issued(self, *, needle: str) -> list[tuple[str, ...]]:
        """Every command whose argv carries `needle`."""
        return [argv for argv in self.argvs if needle in argv]


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


# --- the recipe, against stub `uv` and `just` ------------------------------

_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *green_token*)                       exit "${GREEN_TOKEN_EXIT}" ;;
    *"gate_remote_delegate enabled")     exit "${SWITCH_EXIT}" ;;
    *"gate_remote_delegate run")         exit "${GATE_RUN_EXIT}" ;;
esac
exit 0
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
exit 0
"""


def _run_pre_push(
    *, tmp_path: Path, switch_exit: str, gate_run_exit: str = "0"
) -> tuple[int, list[str]]:
    """Run the real `check-pre-push.sh` against stub `uv` and `just`.

    `switch_exit` is the shipped module's own answer — 0 when this push
    delegates, non-zero when it gates locally — so the two arms of each scenario
    meet exactly where the recipe does.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(parents=True)
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    log = tmp_path / "invocations.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            # A tree that has not gone green locally, which is the Given of all
            # three scenarios: "a tree that has no green token".
            "GREEN_TOKEN_EXIT": "1",
            "SWITCH_EXIT": switch_exit,
            "GATE_RUN_EXIT": gate_run_exit,
        }
    )
    completed = subprocess.run(
        ["bash", str(_PRE_PUSH)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, invoked


# --- the contract section --------------------------------------------------


def test_delegation_is_selected_by_the_opt_in_and_the_host_together(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The contract's "Opt-in" and "Host eligibility" bullets, as one decision.

    FOUR of the five shapes here answer NO, and that asymmetry is the contract's:
    only the literal boolean `true` opts in, and even then only where the pushing
    user can read the gates credential. Every other shape — an absent key, a
    `false`, a value of another type, an opted-in repository on a host holding no
    credential — leaves the repository gating locally, which is the direction in
    which a mistake is merely expensive rather than an ungated push.

    This repository's OWN opt-in is asserted last, because it is the live
    consequence of the two bullets rather than a fixture: livespec-dev-tooling
    declares `delegated_gate = true` and therefore delegates from the VPS and
    gates locally everywhere else, this suite's own host included.
    """
    _ = _an_eligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()

    assert delegated_gate_selected(repo_root=repo) is False
    for body, expected in (
        ('[tool.livespec_dev_tooling]\nsource_trees = ["widget"]\n', False),
        ("[tool.livespec_dev_tooling]\ndelegated_gate = false\n", False),
        ('[tool.livespec_dev_tooling]\ndelegated_gate = "yes"\n', False),
        ("[tool.livespec_dev_tooling]\ndelegated_gate = true\n", True),
    ):
        _ = (repo / "pyproject.toml").write_text(body, encoding="utf-8")
        assert delegated_gate_selected(repo_root=repo) is expected

    _ = _an_ineligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert delegated_gate_enabled(repo_root=repo) is True
    assert delegated_gate_selected(repo_root=repo) is False

    assert delegated_gate_enabled(repo_root=_REPO_ROOT) is True


# --- scenario: an ineligible host gates locally ---------------------------


def test_an_opted_in_push_from_a_host_without_the_credential_gates_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: an opted-in push from a host that cannot read the gates kubeconfig.

    The DECISION arm: the probe answers non-zero — which IS the fall-through —
    and prints that this push gated locally. The line is not decoration: an
    opted-in repository that quietly gates somewhere other than where it was
    configured to is the one outcome an operator cannot tell apart afterwards,
    since a locally-gated push and a cluster-gated one look identical once they
    have completed.

    The RECIPE arm: that exit code runs `just hook_gate=1 check` — the full local
    aggregate, unchanged — and submits NOTHING to the gates namespace.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _opt_in(repo_root=repo)
    _ = _an_ineligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    decided = main()
    printed = capsys.readouterr().err

    assert decided == 1
    assert "gating locally" in printed

    code, invoked = _run_pre_push(tmp_path=tmp_path / "push", switch_exit=str(decided))

    assert code == 0
    assert "just hook_gate=1 check" in invoked
    assert not [line for line in invoked if "gate_remote_delegate run" in line]


def test_the_gate_pods_own_check_pre_push_gates_locally_instead_of_delegating_again(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The host-eligibility rule read from INSIDE a gate pod — the recursion that cannot start.

    The shared default a consumer declaring no `gate_check_suite` gets ends in
    `just check-pre-push` (freeze-driver ruling R100, 2026-10-17), and
    `check-pre-push` is the very recipe that consults this module's switch. So
    the default now runs the delegation question again, one level down, inside
    the Job the first answer produced — and if it answered the same way there,
    a gate pod would submit a gate Job, whose pod would submit another.

    THE POD IS AN INELIGIBLE HOST, AND THAT IS THE WHOLE GUARD. Delegation
    needs two facts, not one: the repository's `delegated_gate = true`, which
    travels with the code and is therefore just as true inside the pod, AND a
    READABLE gates kubeconfig, which is a property of the host. The gate pod is
    handed no gates credential — it holds `GH_TOKEN` and nothing else — so the
    second fact is false there and `enabled` answers non-zero, which IS the
    local fall-through. Asserted as the pair, because the opt-in alone answering
    yes is exactly what makes the credential half load-bearing.

    This is the same mechanism the ineligible-host scenario above exercises from
    a laptop, asserted of the one caller that reaches it through a delegation
    that has ALREADY happened — and joined to the default suite, so a default
    that stopped ending in `check-pre-push` fails here rather than leaving an
    unexercised claim behind.

    `git push --no-verify` is not what stops the recursion either, and it is
    worth saying which layer does: the client's own mirror pushes run hookless
    (`gate_remote_client._mirror_push`), while THIS is the layer that stops the
    pod's aggregate from reaching the client at all.
    """
    pod_workspace = tmp_path / "workspace"
    pod_workspace.mkdir()
    _opt_in(repo_root=pod_workspace)
    absent = _an_ineligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert absent.is_file() is False, "the fixture pod was handed a gates credential"
    assert GATE_CHECK_SUITE_FALL_THROUGH[-1] == "check-pre-push"
    assert delegated_gate_enabled(repo_root=pod_workspace) is True
    assert delegated_gate_selected(repo_root=pod_workspace) is False

    monkeypatch.chdir(pod_workspace)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    decided = main()
    printed = capsys.readouterr().err

    assert decided == 1
    assert "gating locally" in printed

    code, invoked = _run_pre_push(tmp_path=tmp_path / "pod-run", switch_exit=str(decided))

    assert code == 0
    assert "just hook_gate=1 check" in invoked
    assert not [line for line in invoked if "gate_remote_delegate run" in line]


# --- scenario: an eligible host completes on a green verdict --------------


def test_an_opted_in_push_from_an_eligible_host_completes_on_a_green_cluster_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: an opted-in push from an eligible host completes on a green verdict.

    THREE Thens, and each is asserted where it happens. That a gate Job for the
    committed HEAD tree runs in the `gates` namespace: the submit carries the
    namespace and the manifest rendered for that tree's hash, and it goes through
    the credential wrapper, because a cluster command that authenticates with the
    pushing user's own empty environment reaches no namespace at all. That the
    push completes only AFTER a green verdict: the run polls until the Job
    reports `Complete` rather than reading a verdict off its first answer. That
    the green token is recorded for that tree: the existing `green_token write`
    CLI is invoked, which is what the pre-push gate's own skip path reads.
    """
    repo = tmp_path / "widget"
    repo.mkdir()
    _opt_in(repo_root=repo)
    _ = _an_eligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])
    cluster = _CannedCluster()

    assert main() == 0

    verdict = run_delegated_gate(
        repo_root=repo, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_PASSED
    assert verdict.token_written is True
    assert verdict.refuses_push is False
    submit = cluster.issued(needle="create")
    assert len(submit) == 1
    assert submit[0][:4] == (GATES_WRAPPER, "kubectl", "--namespace", _NAMESPACE)
    assert _TREE in cluster.issued(needle="--tree-hash")[0]
    assert [argv for argv in cluster.argvs if f"HEAD:refs/gates/{_TREE}" in argv]
    # Two polls: the run waited through a Job that had not been admitted yet.
    assert len(cluster.issued(needle="get")) == 2
    assert [
        argv
        for argv in cluster.issued(needle="write")
        if "livespec_dev_tooling.green_token" in argv
    ]

    code, invoked = _run_pre_push(tmp_path=tmp_path / "push", switch_exit="0")

    assert code == 0
    assert [line for line in invoked if "gate_remote_delegate run" in line]
    assert not [line for line in invoked if line.startswith("just ")]


# --- scenario: no verdict refuses the push --------------------------------


def test_an_opted_in_push_is_refused_when_no_verdict_arrives(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: an opted-in push is refused when no verdict arrives.

    An unreachable API server is a gate that decided NOTHING, which is neither a
    pass nor a red tree — so the push is refused and no green token is written.
    The distinction is the one a delegated gate exists to keep: a plumbing fault
    and a red tree want opposite responses from whoever reads the message.

    And the local aggregate MUST NOT run in its place. That is the half a recipe
    could get wrong while looking generous: falling back to a local `just check`
    on a lost cluster would turn "we could not gate this" into "we gated it some
    other way", and the push would complete on a verdict nobody produced. The
    explicit local route exists for that — a green local `just check`, run
    deliberately, records the token — and it is not something a failed delegation
    may take on the operator's behalf.
    """
    repo = tmp_path / "widget"
    repo.mkdir()
    _opt_in(repo_root=repo)
    _ = _an_eligible_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    cluster = _CannedCluster(unreachable=True)

    verdict = run_delegated_gate(
        repo_root=repo, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert not cluster.issued(needle="write")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    code, invoked = _run_pre_push(tmp_path=tmp_path / "push", switch_exit="0", gate_run_exit="1")

    assert code == 1
    assert not [line for line in invoked if line.startswith("just ")]
