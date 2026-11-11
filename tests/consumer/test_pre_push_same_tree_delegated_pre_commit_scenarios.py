"""Consumer-tier: a push accepts a same-tree delegated pre-commit verdict (v186).

The seven ratified scenarios of `SPECIFICATION/scenarios.md` (v186) for the
`SPECIFICATION/contracts.md` rules that let the delegated pre-push gate accept a
same-tree delegated pre-commit verdict, that keep a local pre-commit pass from
standing in for it, and that have the delegated pre-commit aggregate record the
evidence it reads (livespec-dev-tooling-73ocxb).

THE CLAIM SPANS FIVE ARTIFACTS THAT CANNOT SEE EACH OTHER: the gate Job's pod
script, which reports the members it ran; the delegated pre-commit seam
(`pre_commit_delegate`), which records pre-push evidence from that report; the
green-token module, which accepts or refuses it at push time; and the two hook
scripts, `check-pre-push.sh` and `check.sh`, which route a push and decide what
it runs. Each is driven here as a consumer meets it:

- the hook scripts are the COMMITTED scripts, run under bash against stub `uv`
  and `just` executables that record what they were asked to run, so the
  routing is observed rather than read off the source;
- the pre-commit seam and the green-token module run IN-PROCESS against a
  throwaway git repository that sets the delegated keys, with only the cluster
  (`run_gated_push`, `gate_remote_request`) and the credential probe stubbed;
- the gate Job's pod script is RENDERED by the real renderer from a fixture
  consumer and run against a stub `just` that prints the aggregate's report.

Nothing here reaches a cluster, a mirror or the network.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts" / "just"
_CHECK_SH = _SCRIPTS / "check.sh"
_PRE_PUSH = _SCRIPTS / "check-pre-push.sh"
_PRE_COMMIT = _SCRIPTS / "check-pre-commit.sh"
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"

_JOB = "gate-widget-pre-commit-7f2qd"
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# The scenario's check set. `check-alpha` is tree-pure and NOT named by the
# pre-commit Job; `check-red-green-replay` is world-reading and not named either;
# `check-beta` is tree-pure and named; `check-world` is world-reading and named;
# `check-approval` reads an authorization held outside the tree and is named.
# `check-fleet-conformance-admin` is the one member every hook path omits.
_ALPHA = "check-alpha"
_REPLAY = "check-red-green-replay"
_BETA = "check-beta"
_WORLD = "check-world"
_APPROVAL = "check-approval"
_HOOK_OMITTED = "check-fleet-conformance-admin"
_MEMBERS = (_ALPHA, _APPROVAL, _BETA, _HOOK_OMITTED, _REPLAY, _WORLD)
_WORLD_READING = f"{_REPLAY} {_WORLD} {_HOOK_OMITTED}"
_COVERED = (_APPROVAL, _BETA, _WORLD)

_GIT_SCRUB_PREFIXES = ("GIT_", "COVERAGE_", "COV_CORE_")

_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *parallel_check_dispatcher*)
        printf 'dispatch-env pre_commit_hook=%s evidence_job=%s\\n' \\
            "${LIVESPEC_PRE_COMMIT_HOOK:-}" "${LIVESPEC_PRE_PUSH_EVIDENCE_JOB:-}" >> "${STUB_LOG}"
        exit "${DISPATCH_EXIT:-0}"
        ;;
    *"green_token world-reading"*)
        for arg in "$@"; do
            case " ${WORLD_READING_MEMBERS:-} " in
                *" ${arg} "*) printf '%s\\n' "${arg}" ;;
            esac
        done
        exit 0
        ;;
    *"check_authority members")
        for member in ${AUTHORITY_MEMBERS:-}; do printf '%s\\n' "${member}"; done
        exit 0
        ;;
    *"green_token undeclared"*)        exit 0 ;;
    *"green_token check")              exit "${GREEN_TOKEN_EXIT:-1}" ;;
    *"green_token pre-push-evidence")
        [ -n "${EVIDENCE:-}" ] || exit 1
        printf '%b' "${EVIDENCE}"
        exit 0
        ;;
    *"gate_remote_delegate enabled")   exit "${SWITCH_EXIT:-1}" ;;
    *"pre_commit_delegate run")        exit "${DELEGATE_EXIT:-75}" ;;
esac
exit 0
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
printf 'just-env pre_commit_hook=%s evidence_job=%s evidence_tree=%s evidence_members=%s\\n' \\
    "${LIVESPEC_PRE_COMMIT_HOOK:-}" "${LIVESPEC_PRE_PUSH_EVIDENCE_JOB:-}" \\
    "${LIVESPEC_PRE_PUSH_EVIDENCE_TREE:-}" "${LIVESPEC_PRE_PUSH_EVIDENCE_MEMBERS:-}" >> "${STUB_LOG}"
exit "${JUST_EXIT:-0}"
"""


class _Run(NamedTuple):
    """One stub-driven script run: its exit code, its output, and what it invoked."""

    code: int
    output: str
    invoked: list[str]


def _scrubbed_env() -> dict[str, str]:
    """This process's environment without the git-hook and coverage variables."""
    return {k: v for k, v in os.environ.items() if not k.startswith(_GIT_SCRUB_PREFIXES)}


def _scrub_process(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub this process too, for the in-process seams that spawn their own git."""
    for key in [name for name in os.environ if name.startswith(_GIT_SCRUB_PREFIXES)]:
        monkeypatch.delenv(key, raising=False)


def _git(*, repo: Path, args: tuple[str, ...]) -> str:
    """Run one git command in `repo` and return its stripped stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return completed.stdout.strip()


def _a_repository(*, repo: Path, keys: str) -> Path:
    """A throwaway git repository whose `[tool.livespec_dev_tooling]` body is `keys`."""
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{keys}", encoding="utf-8"
    )
    _ = (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@test.test"),
        ("config", "user.name", "Test User"),
        ("add", "."),
        ("commit", "-q", "-m", "chore: baseline"),
    ):
        _ = _git(repo=repo, args=args)
    return repo


_BOTH_KEYS = "delegated_gate = true\ndelegated_pre_commit = true\n"
_GATE_KEY_ONLY = "delegated_gate = true\n"


def _stage(*, repo: Path, files: dict[str, str]) -> str:
    """Write and stage `files`, returning the staged tree `git write-tree` names."""
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
        _ = _git(repo=repo, args=("add", relative))
    return _git(repo=repo, args=("write-tree",))


def _run_script(
    *, root: Path, script: Path, args: tuple[str, ...], overrides: dict[str, str], stdin: str
) -> _Run:
    """Run a committed gate script from `root` against the stub `uv` and `just`."""
    stub_dir = root.parent / f"{root.name}-bin"
    stub_dir.mkdir(exist_ok=True)
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    log = root.parent / f"{root.name}-invocations.log"
    env = _scrubbed_env()
    for marker in (
        "LIVESPEC_PRE_COMMIT_HOOK",
        "LIVESPEC_PRE_PUSH_EVIDENCE_JOB",
        "LIVESPEC_PRE_PUSH_EVIDENCE_TREE",
        "LIVESPEC_PRE_PUSH_EVIDENCE_MEMBERS",
        "LIVESPEC_GATE_CONTEXT",
    ):
        _ = env.pop(marker, None)
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            "WORLD_READING_MEMBERS": _WORLD_READING,
            "AUTHORITY_MEMBERS": _APPROVAL,
            "skip": "",
            "red_staged": "",
            "hook_gate": "",
            "token_match": "",
        }
    )
    env.update(overrides)
    completed = subprocess.run(
        ["bash", str(script), *args],
        cwd=str(root),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return _Run(
        code=completed.returncode, output=completed.stdout + completed.stderr, invoked=invoked
    )


def _carrying(*, run: _Run, needle: str) -> list[str]:
    """Every recorded line of `run` that carries `needle`."""
    return [line for line in run.invoked if needle in line]


def _run_pre_push(*, root: Path, overrides: dict[str, str]) -> _Run:
    """Run the real `check-pre-push.sh` for one ordinary (non-deletion) ref update."""
    live = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
    return _run_script(
        root=root,
        script=_PRE_PUSH,
        args=(),
        overrides=overrides,
        stdin=f"refs/heads/feature {live} refs/heads/feature {'0' * 40}\n",
    )


def _run_aggregate(*, root: Path, overrides: dict[str, str]) -> _Run:
    """Run the real `check.sh` over the scenario's check set."""
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "check-targets.txt").write_text(
        "".join(f"{member}\n" for member in _MEMBERS), encoding="utf-8"
    )
    return _run_script(root=root, script=_CHECK_SH, args=_MEMBERS, overrides=overrides, stdin="")


def _accepted_evidence_env(*, tree: str, members: tuple[str, ...]) -> dict[str, str]:
    """The environment `check-pre-push.sh` hands `check.sh` on the accepting path."""
    return {
        "hook_gate": "1",
        "LIVESPEC_PRE_PUSH_EVIDENCE_JOB": _JOB,
        "LIVESPEC_PRE_PUSH_EVIDENCE_TREE": tree,
        "LIVESPEC_PRE_PUSH_EVIDENCE_MEMBERS": " ".join(members),
    }


def _skip_argument(*, run: _Run) -> list[str]:
    """The `--skip` list the one dispatcher invocation of `run` was given."""
    dispatched = [
        line
        for line in _carrying(run=run, needle="parallel_check_dispatcher")
        if line.startswith("uv ")
    ]
    assert len(dispatched) == 1, f"exactly one dispatch is expected; invoked={run.invoked}"
    return dispatched[0].split(" --skip ", 1)[1].split(" -- ", 1)[0].split()


# --- the in-process seams --------------------------------------------------


def _modules() -> tuple[ModuleType, ModuleType]:
    """The committed pre-commit seam and green-token module, imported at call time."""
    return (
        importlib.import_module("livespec_dev_tooling.pre_commit_delegate"),
        importlib.import_module("livespec_dev_tooling.green_token"),
    )


def _a_delegated_pre_commit(
    *,
    repo: Path,
    tree: str,
    report: tuple[tuple[str, str], ...] | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    while_waiting: object = None,
) -> int:
    """Run the real pre-commit seam whose gate Job passed `tree` and reported `report`.

    Only the cluster is stubbed: the credential probe, the request assembly, the
    Job run itself and the host-side authority members. The staged-tree read, the
    staged commit, the full-aggregate classification, the host's cleanliness and
    the evidence writes are the committed code against the real repository.
    `while_waiting`, when given, runs while the Job "runs", which is how a test
    changes the host before the verdict arrives.
    """
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    delegate, _green_token = _modules()
    _scrub_process(monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(delegate, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(delegate, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        delegate,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=repo, mirror_url="mirror", manifest="manifest", gate_ref="refs/gates/t"
            )
        ),
    )

    def the_job(**_kwargs: object) -> object:
        if callable(while_waiting):
            _ = while_waiting()
        return GateVerdict(
            state=GATE_PASSED,
            detail="the gate passed",
            token_written=False,
            job_name=_JOB,
            tree_hash=tree,
            output_checksum="sha256:" + "0" * 64,
            member_verdicts=report,
        )

    monkeypatch.setattr(delegate, "run_gated_push", the_job)
    monkeypatch.setattr(delegate, "run_host_authority_members", lambda **_kwargs: ())
    monkeypatch.setattr(sys, "argv", ["pre_commit_delegate", "run"])
    status = delegate.main()
    _ = capsys.readouterr()
    return status


def _pre_push_evidence(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str]]:
    """Ask the real green-token module whether a qualifying verdict exists for this push."""
    _delegate, green_token = _modules()
    _scrub_process(monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["green-token", "pre-push-evidence"])
    status = green_token.main()
    return status, capsys.readouterr().out.splitlines()


def _green_token(
    *,
    repo: Path,
    argv: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> int:
    """Run one real green-token subcommand in `repo` and return its exit status."""
    _delegate, green_token = _modules()
    _scrub_process(monkeypatch=monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["green-token", *argv])
    status = green_token.main()
    _ = capsys.readouterr()
    return status


_FULL_REPORT = (
    (_ALPHA, "failed"),
    (_APPROVAL, "passed"),
    (_BETA, "passed"),
    (_WORLD, "passed"),
)


# --- Scenario: a push of a tree whose delegated pre-commit aggregate passed ---


def test_a_full_delegated_pre_commit_pass_records_evidence_the_push_of_that_tree_accepts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The evidence half: Job `J` passed staged tree `T`, and a clean push of `T` accepts it.

    The report names `check-alpha` as failed, so only the members it names as
    run AND passed are carried: a member the Job did not pass is not covered.
    """
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    tree = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})

    status = _a_delegated_pre_commit(
        repo=repo, tree=tree, report=_FULL_REPORT, monkeypatch=monkeypatch, capsys=capsys
    )
    assert status == 0
    _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget"))

    accepted, lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)

    assert accepted == 0, (
        "a clean worktree whose HEAD tree is the tree a delegated pre-commit Job passed must "
        "accept that Job's verdict"
    )
    assert lines == [_JOB, tree, *_COVERED], (
        "the accepted evidence must name the gate Job in a field of its own, the tree, and "
        f"exactly the members the Job reported as run and passed; lines={lines}"
    )


def test_an_accepting_push_submits_no_gate_job_and_names_the_job_and_tree(
    *, tmp_path: Path
) -> None:
    """The routing half: no gate Job, no full fall-through, and `J` and `T` are printed."""
    tree = "a" * 40
    evidence = "\\n".join((_JOB, tree, *_COVERED)) + "\\n"
    root = tmp_path / "push"
    root.mkdir()

    run = _run_pre_push(root=root, overrides={"EVIDENCE": evidence, "SWITCH_EXIT": "0"})

    assert run.code == 0, f"output={run.output!r} invoked={run.invoked}"
    assert not _carrying(run=run, needle="gate_remote_delegate"), (
        f"an accepted delegated pre-commit verdict must not submit a gate Job; "
        f"invoked={run.invoked}"
    )
    narrowed = _carrying(run=run, needle="just-env")
    assert narrowed == [
        f"just-env pre_commit_hook= evidence_job={_JOB} evidence_tree={tree} "
        f"evidence_members={' '.join(_COVERED)} "
    ], f"the aggregate must be handed the accepted verdict; invoked={run.invoked}"
    assert _carrying(run=run, needle="just hook_gate=1 check")
    assert _JOB in run.output
    assert tree in run.output


def test_an_accepting_push_runs_only_the_members_the_pre_commit_job_did_not_cover(
    *, tmp_path: Path
) -> None:
    """The aggregate half: skip only what `J` covered, run the rest, and say so."""
    tree = "a" * 40
    run = _run_aggregate(
        root=tmp_path / "agg", overrides=_accepted_evidence_env(tree=tree, members=_COVERED)
    )

    assert run.code == 0, f"output={run.output!r} invoked={run.invoked}"
    skipped = _skip_argument(run=run)
    assert _BETA in skipped, f"a tree-pure member `J` passed must not run again; skip={skipped}"
    for member in (_ALPHA, _REPLAY, _WORLD, _APPROVAL):
        assert member not in skipped, (
            f"{member} must run on the pushing host: it is not covered by `J`, or it reads "
            f"state or an authorization outside the tree; skip={skipped}"
        )
        assert f"running member {member}" in run.output, f"output={run.output!r}"
    assert _JOB in run.output
    assert tree in run.output
    assert "skipped 1 member" in run.output, f"output={run.output!r}"
    assert not _carrying(run=run, needle="green_token write"), (
        f"a run that executed part of the check set must not write the green token; "
        f"invoked={run.invoked}"
    )
    assert (
        "dispatch-env pre_commit_hook= evidence_job=" in run.invoked
    ), f"the markers must not leak into the members the aggregate runs; invoked={run.invoked}"


# --- Scenario: a pre-commit aggregate that ran on the committing host -------


def test_the_pre_commit_hooks_local_aggregate_carries_its_marker(*, tmp_path: Path) -> None:
    """The local `just check` the pre-commit hook runs is marked as the hook's own."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    _ = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})

    run = _run_script(
        root=repo, script=_PRE_COMMIT, args=(), overrides={"DELEGATE_EXIT": "75"}, stdin=""
    )

    assert run.code == 0, f"output={run.output!r} invoked={run.invoked}"
    assert _carrying(run=run, needle="just hook_gate=1 check")
    assert _carrying(run=run, needle="just-env pre_commit_hook=1 "), (
        f"the pre-commit hook's local aggregate must carry the marker only it sets; "
        f"invoked={run.invoked}"
    )


def test_under_the_marker_the_aggregate_asks_for_no_pre_push_stand_in(*, tmp_path: Path) -> None:
    """`check.sh` hands the marker to the token writer and keeps it from its members."""
    run = _run_aggregate(
        root=tmp_path / "agg", overrides={"hook_gate": "1", "LIVESPEC_PRE_COMMIT_HOOK": "1"}
    )

    assert run.code == 0, f"output={run.output!r} invoked={run.invoked}"
    writes = _carrying(run=run, needle="green_token write")
    assert writes == [
        "uv run python -m livespec_dev_tooling.green_token write --pre-commit-hook"
    ], f"invoked={run.invoked}"
    assert (
        "dispatch-env pre_commit_hook= evidence_job=" in run.invoked
    ), f"no member may inherit the pre-commit hook's marker; invoked={run.invoked}"


def test_a_local_pre_commit_pass_in_a_both_keys_repository_never_stands_in_for_the_push(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No green token, no pre-push evidence, and the push submits a gate Job for `T`."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    _ = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})
    _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget"))

    wrote = _green_token(
        repo=repo, argv=("write", "--pre-commit-hook"), monkeypatch=monkeypatch, capsys=capsys
    )
    token = Path(_git(repo=repo, args=("rev-parse", "--absolute-git-dir"))) / (
        "livespec-green-token.json"
    )
    assert wrote == 0
    assert not token.exists(), "the pre-commit hook's local aggregate must write no green token"

    local_evidence = _green_token(
        repo=repo,
        argv=("write-pre-commit", "pre-commit-aggregate:local", "sha256:" + "1" * 64),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert local_evidence == 0
    assert (
        _green_token(repo=repo, argv=("check",), monkeypatch=monkeypatch, capsys=capsys) == 1
    ), "the same-tree evidence a local aggregate writes must not stand in for the pre-push gate"
    accepted, _lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert accepted == 1

    run = _run_pre_push(root=tmp_path, overrides={"GREEN_TOKEN_EXIT": "1", "SWITCH_EXIT": "0"})
    assert _carrying(run=run, needle="gate_remote_delegate run"), f"invoked={run.invoked}"
    assert "accepted the delegated pre-commit verdict" not in run.output


# --- Scenario: a delegated pre-commit pass on a dirty or changed tree -------


@pytest.mark.parametrize("disturbance", ["unstaged", "untracked", "index-moved"])
def test_a_delegated_pre_commit_pass_on_a_dirty_or_changed_tree_records_no_evidence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    disturbance: str,
) -> None:
    """When the verdict arrives the host no longer holds exactly `T`, clean: no evidence."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    tree = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})

    def disturb() -> None:
        if disturbance == "unstaged":
            _ = (repo / "README.md").write_text("edited\n", encoding="utf-8")
        elif disturbance == "untracked":
            _ = (repo / "stray.txt").write_text("stray\n", encoding="utf-8")
        else:
            _ = _stage(repo=repo, files={"other.py": "OTHER = 2\n"})

    status = _a_delegated_pre_commit(
        repo=repo,
        tree=tree,
        report=_FULL_REPORT,
        monkeypatch=monkeypatch,
        capsys=capsys,
        while_waiting=disturb,
    )
    assert status == 0
    evidence = Path(_git(repo=repo, args=("rev-parse", "--absolute-git-dir"))) / (
        "livespec-pre-push-evidence.json"
    )
    assert not evidence.exists(), f"no pre-push evidence may be recorded after {disturbance}"


# --- Scenario: a delegated pre-commit pass does not stand in for a differing push


@pytest.mark.parametrize("difference", ["head-tree", "uncommitted"])
def test_a_delegated_pre_commit_pass_does_not_stand_in_when_the_tree_or_worktree_differs(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    difference: str,
) -> None:
    """Recorded evidence for `T` is refused when HEAD is not `T` or the worktree is dirty."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    tree = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})
    assert (
        _a_delegated_pre_commit(
            repo=repo, tree=tree, report=_FULL_REPORT, monkeypatch=monkeypatch, capsys=capsys
        )
        == 0
    )
    _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget"))
    accepted_first, _lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert accepted_first == 0, "the control: the evidence qualifies before the difference"

    if difference == "head-tree":
        _ = _stage(repo=repo, files={"widget.py": "VALUE = 2\n"})
        _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget two"))
    else:
        _ = (repo / "widget.py").write_text("VALUE = 3\n", encoding="utf-8")

    accepted, lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)

    assert accepted == 1
    assert lines == []
    run = _run_pre_push(root=tmp_path, overrides={"SWITCH_EXIT": "0"})
    assert _carrying(run=run, needle="gate_remote_delegate run"), f"invoked={run.invoked}"
    assert _JOB not in run.output


# --- Scenario: a doc-only or Red-leg delegated pre-commit run ---------------


@pytest.mark.parametrize(
    "staged",
    [{"docs/notes.md": "notes\n"}, {"tests/test_widget.py": "def test_widget() -> None: ...\n"}],
    ids=["doc-only", "red-leg"],
)
def test_a_doc_only_or_red_leg_delegated_pre_commit_run_records_no_pre_push_evidence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    staged: dict[str, str],
) -> None:
    """A green subset run, with a member report and a clean host, still records nothing."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    tree = _stage(repo=repo, files=staged)

    status = _a_delegated_pre_commit(
        repo=repo, tree=tree, report=_FULL_REPORT, monkeypatch=monkeypatch, capsys=capsys
    )
    assert status == 0
    _ = _git(repo=repo, args=("commit", "-q", "-m", "chore: subset"))

    accepted, _lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert accepted == 1, "a doc-only or Red-leg subset must never stand in for the pre-push gate"


def test_a_job_that_reported_no_member_list_records_no_pre_push_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Evidence is recorded only for a Job that reported its member list."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_BOTH_KEYS)
    tree = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})

    assert (
        _a_delegated_pre_commit(
            repo=repo, tree=tree, report=None, monkeypatch=monkeypatch, capsys=capsys
        )
        == 0
    )
    _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget"))
    accepted, _lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)

    assert accepted == 1


# --- Scenario: a member outside the delegated pre-commit run's scope ---------


def test_a_member_outside_the_pre_commit_jobs_scope_still_runs_and_refuses_the_push(
    *, tmp_path: Path
) -> None:
    """`check-red-green-replay`, not named by `J`, runs on the pushing host and refuses."""
    tree = "a" * 40
    run = _run_aggregate(
        root=tmp_path / "agg",
        overrides={**_accepted_evidence_env(tree=tree, members=_COVERED), "DISPATCH_EXIT": "1"},
    )

    assert _REPLAY not in _skip_argument(run=run)
    assert f"running member {_REPLAY}" in run.output, f"output={run.output!r}"
    assert run.code != 0, "a member the push runs that fails must refuse the push"

    pushed = _run_pre_push(
        root=tmp_path,
        overrides={"EVIDENCE": f"{_JOB}\\n{tree}\\n{_BETA}\\n", "JUST_EXIT": "1"},
    )
    assert pushed.code != 0, f"output={pushed.output!r} invoked={pushed.invoked}"


# --- Scenario: a repository that does not set both delegated keys -----------


def test_a_repository_without_both_delegated_keys_keeps_pre_commit_token_reuse(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The marker changes nothing here: the token is written and the push memoizes on it."""
    repo = _a_repository(repo=tmp_path / "repo", keys=_GATE_KEY_ONLY)
    _ = _stage(repo=repo, files={"widget.py": "VALUE = 1\n"})
    _ = _git(repo=repo, args=("commit", "-q", "-m", "feat: widget"))

    wrote = _green_token(
        repo=repo, argv=("write", "--pre-commit-hook"), monkeypatch=monkeypatch, capsys=capsys
    )
    assert wrote == 0
    assert _green_token(repo=repo, argv=("check",), monkeypatch=monkeypatch, capsys=capsys) == 0, (
        "outside a both-keys repository the pre-commit hook's local aggregate still records "
        "the green token the pre-push gate reuses"
    )
    _ = _green_token(
        repo=repo,
        argv=("write-pre-commit", "pre-commit-aggregate:local", "sha256:" + "1" * 64),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert _green_token(repo=repo, argv=("check",), monkeypatch=monkeypatch, capsys=capsys) == 0
    accepted, _lines = _pre_push_evidence(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert accepted == 1, "only a both-keys repository has a pre-push evidence reader"

    run = _run_pre_push(root=tmp_path, overrides={"GREEN_TOKEN_EXIT": "0", "SWITCH_EXIT": "0"})
    assert _carrying(run=run, needle="just hook_gate=1 token_match=1 check")
    assert not _carrying(run=run, needle="gate_remote_delegate")
    assert "accepted the delegated pre-commit verdict" not in run.output


# --- the gate Job's member report (Evidence for the pre-push gate) ----------

_POD_JUST_STUB = """#!/usr/bin/env bash
[ "${1:-}" = "--show" ] && exit 0
if [ "${1:-}" = "check-pre-push" ]; then
    printf '::: just check-nested [ok, wall: 1.0s]\\n'
    printf 'LIVESPEC_CHECK_MEMBERS {"check-fixture": "passed"}\\n'
    printf '\\n--- parallel check summary ---\\n'
    printf '%s\\r\\n' "LIVESPEC_CHECK_MEMBERS ${FINAL_REPORT}"
    exit "${AGGREGATE_EXIT:-0}"
fi
exit 0
"""


def _gate_pod_script(*, consumer: Path) -> tuple[str, dict[str, str]]:
    """Render the real gate Job for `consumer` and return its gate script and literal env."""
    workflow = consumer / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "jobs:\n  one:\n    runs-on: self-hosted\n    container:\n"
        "      image: ghcr.io/example/sandbox:python-v1.11.1\n",
        encoding="utf-8",
    )
    _ = (consumer / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    rendered = subprocess.run(
        [str(_RENDERER), "--repo-root", str(consumer), "--tree-hash", _EMPTY_TREE],
        cwd=str(consumer),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    job = next(doc for doc in yaml.safe_load_all(rendered.stdout) if doc)
    gate = next(c for c in job["spec"]["template"]["spec"]["containers"] if c["name"] == "gate")
    literal = {entry["name"]: str(entry["value"]) for entry in gate["env"] if "value" in entry}
    return str(gate["args"][-1]), literal


@pytest.mark.parametrize("aggregate_exit", ["0", "1"], ids=["green", "red"])
def test_the_gate_job_prints_one_structured_line_naming_every_member_it_ran(
    *, tmp_path: Path, aggregate_exit: str
) -> None:
    """One `LIVESPEC_GATE_MEMBERS` line, the aggregate's LAST report, which the client reads."""
    from livespec_dev_tooling._gate_member_report import parse_member_report

    script, literal = _gate_pod_script(consumer=tmp_path / "consumer")
    pod = tmp_path / "pod"
    pod.mkdir()
    stub_dir = tmp_path / "pod-bin"
    stub_dir.mkdir()
    stub = stub_dir / "just"
    _ = stub.write_text(_POD_JUST_STUB, encoding="utf-8")
    stub.chmod(0o755)
    _ = (tmp_path / "gate.sh").write_text(script, encoding="utf-8")
    env = _scrubbed_env()
    env.update(literal)
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "PYPI_FILES_PROXY": "http://127.0.0.1:9",
            "FINAL_REPORT": '{"check-alpha": "passed", "check-beta": "failed"}',
            "AGGREGATE_EXIT": aggregate_exit,
        }
    )
    _ = env.pop("LIVESPEC_SIBLING_CLONES_ROOT", None)

    completed = subprocess.run(
        ["bash", str(tmp_path / "gate.sh")],
        cwd=str(pod),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert str(completed.returncode) == aggregate_exit, completed.stdout + completed.stderr
    reports = [
        line for line in completed.stdout.splitlines() if line.startswith("LIVESPEC_GATE_MEMBERS ")
    ]
    assert reports == ['LIVESPEC_GATE_MEMBERS {"check-alpha": "passed", "check-beta": "failed"}'], (
        f"the Job must print exactly one structured member line, the aggregate's last report; "
        f"stdout={completed.stdout!r}"
    )
    assert parse_member_report(output=completed.stdout) == (
        ("check-alpha", "passed"),
        ("check-beta", "failed"),
    )
