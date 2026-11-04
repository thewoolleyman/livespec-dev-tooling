"""Integration tests for the detached gate runner's host-local venue paths."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "gate_runner_delegate.py"
_RUNNER = Path("dev-tooling") / "gate-run.sh"
_RUN_TIMEOUT_S = 15.0
_POLL_INTERVAL_S = 0.05


@pytest.mark.parametrize(
    ("command", "force_local", "delegated", "credential_readable", "venue", "reason"),
    [
        pytest.param(
            ("just", "check"), True, True, True, "host_local", "--local", id="explicit-local"
        ),
        pytest.param(
            ("just", "check"),
            False,
            False,
            True,
            "host_local",
            "undelegated repository",
            id="undelegated-repository",
        ),
        pytest.param(
            ("just", "check"),
            False,
            True,
            False,
            "host_local",
            "ineligible host",
            id="ineligible-host",
        ),
        pytest.param(
            ("just", "unit"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="non-full-suite",
        ),
        pytest.param(
            ("just", "check-"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="bare-check-dash-is-not-a-member",
        ),
        pytest.param(
            ("git", "commit", "-m", "keep-hooks"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="commit-keeps-hooks-local",
        ),
        pytest.param(
            ("git", "push"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="push-keeps-hooks-local",
        ),
        pytest.param(
            ("just", "check"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="just-check",
        ),
        pytest.param(
            ("mise", "exec", "--", "just", "check-types"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="mise-just-check-member",
        ),
        pytest.param(
            ("uv", "run", "pytest", "tests"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="uv-pytest",
        ),
    ],
)
def test_gate_runner_venue_selection(
    *,
    command: tuple[str, ...],
    force_local: bool,
    delegated: bool,
    credential_readable: bool,
    venue: str,
    reason: str,
) -> None:
    """The complete selector contract distinguishes local runs from Job candidates."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")

    selected = module.select_venue(
        command=command,
        force_local=force_local,
        delegated=delegated,
        credential_readable=credential_readable,
    )

    assert selected.venue == venue
    assert selected.reason == reason


def _environment(*, project_root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    inherited = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(project_root) if not inherited else f"{project_root}{os.pathsep}{inherited}"
    )
    return environment


def _run(*, args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _init_repo(*, tmp_path: Path, delegated: bool = True) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    root.mkdir()
    environment = _environment(project_root=Path(__file__).parents[2])
    _ = _run(args=["git", "init", "--quiet", "--initial-branch=main"], cwd=root, env=environment)
    _ = _run(args=["git", "config", "user.name", "Test User"], cwd=root, env=environment)
    _ = _run(args=["git", "config", "user.email", "test@example.com"], cwd=root, env=environment)
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\ndelegated_gate = {str(delegated).lower()}\n",
        encoding="utf-8",
    )
    runner = root / _RUNNER
    _ = runner.parent.mkdir()
    _ = runner.write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")
    _ = runner.chmod(0o755)
    _ = (runner.parent / "worktree-lib.sh").write_text("# installed\n", encoding="utf-8")
    return root, environment


def _start(*, root: Path, env: dict[str, str], args: list[str]) -> Path:
    launched = _run(args=["bash", str(_RUNNER), "start", *args], cwd=root, env=env)
    assert launched.returncode == 0, launched.stderr
    run_id = launched.stdout.strip()
    run_dir = root / "tmp" / "gate-runs" / run_id
    finished = any(
        (run_dir / "exit_code").is_file() or time.sleep(_POLL_INTERVAL_S)
        for _ in range(int(_RUN_TIMEOUT_S / _POLL_INTERVAL_S))
    )
    assert finished, f"gate run {run_id} did not finish"
    return run_dir


def _worktree_with_uncommitted_content(*, tmp_path: Path) -> tuple[Path, dict[str, str], str]:
    """Return a committed fixture whose worktree now differs from its index."""
    root, environment = _init_repo(tmp_path=tmp_path)
    _ = (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _ = _run(args=["git", "add", "tracked.txt"], cwd=root, env=environment)
    _ = _run(args=["git", "commit", "--quiet", "-m", "base"], cwd=root, env=environment)
    index_tree = _run(args=["git", "write-tree"], cwd=root, env=environment).stdout.strip()
    _ = (root / "tracked.txt").write_text("uncommitted\n", encoding="utf-8")
    return root, environment, index_tree


def test_gate_start_records_and_executes_every_host_local_path(*, tmp_path: Path) -> None:
    """Explicit, undelegated and non-suite commands stay local and record why."""
    root, environment = _init_repo(tmp_path=tmp_path)
    fake_bin = tmp_path / "bin"
    _ = fake_bin.mkdir()
    just_log = tmp_path / "just.log"
    just = fake_bin / "just"
    _ = just.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{just_log}"\n', encoding="utf-8")
    _ = just.chmod(0o755)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

    explicit = _start(root=root, env=environment, args=["--local", "--", "just", "check"])
    non_suite = _start(root=root, env=environment, args=["--", "just", "unit"])
    assert (explicit / "venue").read_text(encoding="utf-8") == "host_local\n"
    assert (explicit / "venue_reason").read_text(encoding="utf-8") == "--local\n"
    assert (non_suite / "venue").read_text(encoding="utf-8") == "host_local\n"
    assert (non_suite / "venue_reason").read_text(
        encoding="utf-8"
    ) == "command outside full-suite set\n"
    assert just_log.read_text(encoding="utf-8").splitlines() == ["check", "unit"]

    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = false\n", encoding="utf-8"
    )
    undelegated = _start(root=root, env=environment, args=["--", "just", "check"])
    assert (undelegated / "venue").read_text(encoding="utf-8") == "host_local\n"
    assert (undelegated / "venue_reason").read_text(encoding="utf-8") == "undelegated repository\n"


def test_gate_start_uses_the_project_python_when_no_venv_is_activated(*, tmp_path: Path) -> None:
    """The pack selects a venue even when bare ``python3`` lacks the package."""
    root, environment = _init_repo(tmp_path=tmp_path)
    fake_bin = tmp_path / "bin"
    _ = fake_bin.mkdir()
    uv_log = tmp_path / "uv.log"
    python3 = fake_bin / "python3"
    _ = python3.write_text("#!/bin/sh\nexit 83\n", encoding="utf-8")
    _ = python3.chmod(0o755)
    uv = fake_bin / "uv"
    _ = uv.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" > "{uv_log}"\n'
        'test "$1" = run && shift\n'
        'test "$1" = --no-sync && shift\n'
        'test "$1" = python && shift\n'
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    _ = uv.chmod(0o755)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

    run_dir = _start(root=root, env=environment, args=["--", "true"])

    assert (run_dir / "venue").read_text(encoding="utf-8") == "host_local\n"
    assert uv_log.read_text(encoding="utf-8") == (
        "run --no-sync python -m livespec_dev_tooling.gate_runner_delegate -- true\n"
    )


def test_selector_cli_strips_gate_starts_command_separator(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A full suite launched by gate-start reaches the delegated venue selector."""
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    selected: dict[str, object] = {}

    def choose(**kwargs: object) -> object:
        selected.update(kwargs)
        return module.GateVenue(venue="cluster_job", reason="eligible full-suite command")

    monkeypatch.setattr(module, "select_for_repository", choose)
    monkeypatch.setattr(module.sys, "argv", ["gate-runner-venue", "--", "just", "check"])

    assert module.main() == 0
    assert selected["command"] == ("just", "check")
    assert capsys.readouterr().out == "cluster_job\neligible full-suite command\n"


def test_gate_start_keeps_commit_and_push_hooks_on_the_launching_host(*, tmp_path: Path) -> None:
    """Commit and push remain local so their own hook delegation can run."""
    root, environment = _init_repo(tmp_path=tmp_path)
    hook_log = tmp_path / "hooks.log"
    hooks = root / ".git" / "hooks"
    for hook_name in ("pre-commit", "pre-push"):
        hook = hooks / hook_name
        _ = hook.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "{hook_name}" >> "{hook_log}"\n', encoding="utf-8"
        )
        _ = hook.chmod(0o755)
    remote = tmp_path / "remote.git"
    _ = _run(args=["git", "init", "--bare", "--quiet", str(remote)], cwd=root, env=environment)
    _ = _run(args=["git", "remote", "add", "origin", str(remote)], cwd=root, env=environment)

    committed = _start(
        root=root,
        env=environment,
        args=["--", "git", "commit", "--allow-empty", "-m", "local hook"],
    )
    pushed = _start(
        root=root,
        env=environment,
        args=["--", "git", "push", "origin", "HEAD:refs/heads/main"],
    )
    for run_dir in (committed, pushed):
        assert (run_dir / "venue").read_text(encoding="utf-8") == "host_local\n"
        assert (run_dir / "venue_reason").read_text(encoding="utf-8") == (
            "command outside full-suite set\n"
        )
    assert hook_log.read_text(encoding="utf-8").splitlines() == ["pre-commit", "pre-push"]


@pytest.mark.parametrize(
    ("remote_exit", "expected_wait_exit", "expected_state"),
    [
        pytest.param(0, 0, "PASSED", id="job-verdict-streams-into-the-run-record"),
        pytest.param(
            75,
            75,
            "DIED_WITHOUT_VERDICT",
            id="lost-job-is-died-without-verdict-without-local-retry",
        ),
    ],
)
def test_gate_start_runs_the_cluster_client_over_the_worktree_tree(
    *, tmp_path: Path, remote_exit: int, expected_wait_exit: int, expected_state: str
) -> None:
    """The shell runner reaches its cluster child and preserves its remote verdict."""
    root, environment, original_index_tree = _worktree_with_uncommitted_content(tmp_path=tmp_path)
    fake_package = tmp_path / "fake-package" / "livespec_dev_tooling"
    _ = fake_package.mkdir(parents=True)
    _ = (fake_package / "__init__.py").write_text("", encoding="utf-8")
    _ = (fake_package / "gate_runner_delegate.py").write_text(
        textwrap.dedent(
            f"""\
            import pathlib
            import sys

            if sys.argv[1:2] != ["run"]:
                print("cluster_job")
                print("eligible full-suite command")
                raise SystemExit(0)

            run_dir = pathlib.Path(sys.argv[sys.argv.index("--run-dir") + 1])
            (run_dir / "tree_hash").write_text("worktree-tree\\n", encoding="utf-8")
            (run_dir / "job_name").write_text("gate-worktree-job\\n", encoding="utf-8")
            print("remote job output")
            raise SystemExit({remote_exit})
            """
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    _ = fake_bin.mkdir()
    local_just_log = tmp_path / "local-just.log"
    _ = (fake_bin / "uv").write_text('#!/bin/sh\nshift 3\nexec python3 "$@"\n', encoding="utf-8")
    _ = (fake_bin / "just").write_text(
        f'#!/bin/sh\nprintf "local:%s\\n" "$*" >> "{local_just_log}"\n', encoding="utf-8"
    )
    for executable in (fake_bin / "uv", fake_bin / "just"):
        _ = executable.chmod(0o755)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["PYTHONPATH"] = f"{fake_package.parent}{os.pathsep}{environment['PYTHONPATH']}"

    run_dir = _start(root=root, env=environment, args=["--", "just", "check"])
    waited = _run(args=["bash", str(_RUNNER), "wait", run_dir.name], cwd=root, env=environment)

    assert waited.returncode == expected_wait_exit
    assert f"state             : {expected_state}" in waited.stdout
    if expected_state == "DIED_WITHOUT_VERDICT":
        assert "FAILED" not in waited.stdout
    assert (run_dir / "venue").read_text(encoding="utf-8") == "cluster_job\n"
    assert (run_dir / "tree_hash").read_text(encoding="utf-8") == "worktree-tree\n"
    assert (run_dir / "job_name").read_text(encoding="utf-8") == "gate-worktree-job\n"
    assert "remote job output" in (run_dir / "output.log").read_text(encoding="utf-8")
    assert (
        _run(args=["git", "write-tree"], cwd=root, env=environment).stdout.strip()
        == original_index_tree
    )
    assert not local_just_log.exists()


def test_gate_start_runs_the_cluster_child_in_the_project_environment(*, tmp_path: Path) -> None:
    """The detached cluster child uses the project interpreter, not bare ``python3``."""
    root, environment, _ = _worktree_with_uncommitted_content(tmp_path=tmp_path)
    fake_bin = tmp_path / "bin"
    _ = fake_bin.mkdir()
    uv_log = tmp_path / "uv.log"
    _ = (fake_bin / "python3").write_text("#!/bin/sh\nexit 83\n", encoding="utf-8")
    _ = (fake_bin / "uv").write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{uv_log}"\n'
        "shift 3\n"
        'if test "$3" = run; then echo "remote job output"; exit 0; fi\n'
        'echo cluster_job; echo "eligible full-suite command"\n',
        encoding="utf-8",
    )
    for executable in (fake_bin / "python3", fake_bin / "uv"):
        _ = executable.chmod(0o755)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

    run_dir = _start(root=root, env=environment, args=["--", "just", "check"])

    assert (run_dir / "venue").read_text(encoding="utf-8") == "cluster_job\n"
    assert (run_dir / "exit_code").read_text(encoding="utf-8").strip() == "0"
    assert "remote job output" in (run_dir / "output.log").read_text(encoding="utf-8")
    assert any(
        line.startswith("run --no-sync python -m livespec_dev_tooling.gate_runner_delegate run ")
        for line in uv_log.read_text(encoding="utf-8").splitlines()
    )


def test_a_cluster_gate_uses_the_worktree_tree_and_records_its_job(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delegated full suite publishes uncommitted content without changing the index."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    assert hasattr(module, "run_cluster_gate")
    root, environment, original_index_tree = _worktree_with_uncommitted_content(tmp_path=tmp_path)

    captured: dict[str, object] = {}
    request = GateRunRequest(
        repo_root=root,
        mirror_url="mirror",
        manifest="manifest",
        gate_ref="refs/gates/worktree",
    )

    def build(**kwargs: object) -> object:
        captured.update(kwargs)
        return Success(request)

    def gate(**kwargs: object) -> GateVerdict:
        captured["request"] = kwargs["request"]
        return GateVerdict(
            state=GATE_PASSED,
            detail="the gate passed",
            token_written=False,
            job_name="gate-worktree-1",
        )

    monkeypatch.setattr(module, "gate_remote_request", build)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "run_gated_push", gate)

    outcome = module.run_cluster_gate(repo_root=root, command=("just", "check"))

    assert outcome.exit_status == 0
    assert outcome.job_name == "gate-worktree-1"
    assert outcome.tree_hash != original_index_tree
    assert (
        _run(args=["git", "write-tree"], cwd=root, env=environment).stdout.strip()
        == original_index_tree
    )
    pushed = captured["request"]
    assert pushed.source_ref != "HEAD"
    assert pushed.tree_hash == outcome.tree_hash
    assert pushed.capture_output is False
    assert captured["check_suite"] == ("check",)


def test_a_cluster_just_check_uses_the_declared_bootstrap_before_the_aggregate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate-start full suite keeps the consumer's declared preparation steps."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    root, _ = _init_repo(tmp_path=tmp_path)
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        "delegated_gate = true\n"
        'gate_check_suite = ["install-pack", "install-hooks", "check"]\n',
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    request = GateRunRequest(
        repo_root=root, mirror_url="mirror", manifest="manifest", gate_ref="ref"
    )
    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: ("tree", "commit"))
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module, "gate_remote_request", lambda **kwargs: captured.update(kwargs) or Success(request)
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(state=GATE_PASSED, detail="green", token_written=False),
    )

    assert module.run_cluster_gate(repo_root=root, command=("just", "check")).exit_status == 0

    assert captured["check_suite"] == ("install-pack", "install-hooks", "check")


def _passing_cluster_gate(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """Wire a delegated gate whose Job passes and return the module under test."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    request = GateRunRequest(
        repo_root=root, mirror_url="mirror", manifest="manifest", gate_ref="ref"
    )
    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: ("tree", "commit"))
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "gate_remote_request", lambda **_kwargs: Success(request))
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(state=GATE_PASSED, detail="green", token_written=False),
    )
    return module


def test_a_refused_host_authority_member_after_a_passing_job_exits_1(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evaluated host-authority refusal is a failed verdict, never a lost one."""
    from livespec_dev_tooling._gate_host_authority import HostAuthorityRun

    root, _ = _init_repo(tmp_path=tmp_path)
    module = _passing_cluster_gate(root=root, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        module,
        "run_host_authority_members",
        lambda **_kwargs: (
            HostAuthorityRun(
                member="check-fleet-conformance-admin",
                tree_hash="tree",
                returncode=1,
                detail="owner unresolvable",
            ),
        ),
    )

    outcome = module.run_cluster_gate(repo_root=root, command=("just", "check"))

    assert outcome.exit_status == 1
    assert "check-fleet-conformance-admin" in outcome.detail


def test_a_cluster_pytest_gate_does_not_run_host_authority_members(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Host authority members belong to dispatched just recipes, not to pytest gates."""
    root, _ = _init_repo(tmp_path=tmp_path)
    module = _passing_cluster_gate(root=root, monkeypatch=monkeypatch)
    invoked: list[object] = []
    monkeypatch.setattr(
        module, "run_host_authority_members", lambda **kwargs: invoked.append(kwargs) or ()
    )

    outcome = module.run_cluster_gate(repo_root=root, command=("pytest", "tests"))

    assert outcome.exit_status == 0
    assert invoked == []


def test_a_cluster_gate_without_a_verdict_exits_75_without_a_local_retry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost Job remains a no-verdict result; the launching host never re-runs it."""
    from returns.result import Failure

    from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    assert hasattr(module, "ClusterGateResult")
    root, _ = _init_repo(tmp_path=tmp_path)
    invoked: list[object] = []

    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: ("tree", "commit"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Failure(
            GateStepFailed(step="submit", argv=(), returncode=None, detail="lost")
        ),
    )
    monkeypatch.setattr(module, "run_gated_push", lambda **kwargs: invoked.append(kwargs))

    outcome = module.run_cluster_gate(repo_root=root, command=("just", "check"))

    assert outcome.exit_status == 75
    assert outcome.job_name == ""
    assert invoked == []


def test_cluster_runner_cli_records_tree_and_job_for_gate_status(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The detached shell child persists the cluster evidence in its run record."""
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    run_dir = tmp_path / "run"
    _ = run_dir.mkdir()
    monkeypatch.setattr(
        module,
        "run_cluster_gate",
        lambda **_kwargs: module.ClusterGateResult(
            exit_status=75, tree_hash="tree", job_name="job"
        ),
    )
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["gate-runner-venue", "run", "--run-dir", str(run_dir), "--", "just", "check"],
    )

    assert module.main() == 75
    assert (run_dir / "tree_hash").read_text(encoding="utf-8") == "tree\n"
    assert (run_dir / "job_name").read_text(encoding="utf-8") == "job\n"


def _command_result(*, returncode: int = 0, stdout: str = "") -> object:
    """Build one successful command-seam answer for a temporary-index branch."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_invocation import GateCommandResult

    return Success(GateCommandResult(returncode=returncode, stdout=stdout, stderr=""))


@pytest.mark.parametrize(
    "responses",
    [
        pytest.param(("not-run",), id="index-command-does-not-run"),
        pytest.param(("", "", ""), id="tree-is-empty"),
        pytest.param(("", "", "tree", "not-run"), id="commit-does-not-run"),
        pytest.param(("", "", "tree", ""), id="commit-is-empty"),
    ],
)
def test_temporary_index_failures_are_no_verdicts_and_restore_the_callers_index(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    responses: tuple[str, ...],
) -> None:
    """Every temporary-index failure leaves the caller's index selection intact."""
    from returns.result import Failure

    from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    assert hasattr(module, "run_cluster_gate")
    answers = iter(responses)

    def run(**_kwargs: object) -> object:
        answer = next(answers)
        if answer == "not-run":
            return Failure(GateCommandNotRun(argv=("git",), detail="missing"))
        return _command_result(stdout=answer)

    monkeypatch.setattr(module, "default_gate_command_runner", run)
    monkeypatch.setenv("GIT_INDEX_FILE", "callers-index")

    assert module.run_cluster_gate(repo_root=tmp_path, command=("just", "check")).exit_status == 75
    assert os.environ["GIT_INDEX_FILE"] == "callers-index"


@pytest.mark.parametrize(
    ("command", "expected_pytest", "expected_suite"),
    [
        pytest.param(("pytest", "tests/unit"), ("pytest", "tests/unit"), (), id="pytest"),
        pytest.param(
            ("uv", "run", "pytest", "tests/unit"),
            ("pytest", "tests/unit"),
            (),
            id="uv-pytest",
        ),
    ],
)
def test_cluster_gate_translates_pytest_commands_and_a_missing_tree_to_no_verdict(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
    expected_pytest: tuple[str, ...],
    expected_suite: tuple[str, ...],
) -> None:
    """Pytest spellings preserve their arguments, while an unreadable tree is never local."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_FAILED, GateVerdict

    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    assert hasattr(module, "run_cluster_gate")
    captured: dict[str, object] = {}
    request = GateRunRequest(
        repo_root=tmp_path, mirror_url="mirror", manifest="manifest", gate_ref="ref"
    )
    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: ("tree", "commit"))
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module, "gate_remote_request", lambda **kwargs: captured.update(kwargs) or Success(request)
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(state=GATE_FAILED, detail="red", token_written=False),
    )

    outcome = module.run_cluster_gate(repo_root=tmp_path, command=command)

    assert outcome.exit_status == 1
    assert captured["pytest_argv"] == expected_pytest
    assert captured["check_suite"] == expected_suite
    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: None)
    assert module.run_cluster_gate(repo_root=tmp_path, command=command).exit_status == 75


def test_cluster_runner_cli_omits_absent_evidence_and_streams_its_detail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lost cluster response creates no invented evidence but preserves its explanation."""
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    run_dir = tmp_path / "run"
    _ = run_dir.mkdir()
    monkeypatch.setattr(
        module,
        "run_cluster_gate",
        lambda **_kwargs: module.ClusterGateResult(
            exit_status=75, tree_hash="", job_name="", detail="lost"
        ),
    )
    monkeypatch.setattr(module.sys, "argv", ["gate-runner-venue", "run", "--run-dir", str(run_dir)])

    assert module.main() == 75
    assert not (run_dir / "tree_hash").exists()
    assert not (run_dir / "job_name").exists()
    assert capsys.readouterr().err == "lost\n"
