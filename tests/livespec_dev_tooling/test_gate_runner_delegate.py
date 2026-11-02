"""Integration tests for the detached gate runner's host-local venue paths."""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "gate_runner_delegate.py"
_RUNNER = Path("dev-tooling") / "gate-run.sh"
_RUN_TIMEOUT_S = 15.0


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
            ("just", "check-"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="bare-check-dash-recipe",
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


def _run(
    *, args: list[str], cwd: Path, env: dict[str, str], timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
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
    waited = _run(
        args=["bash", str(_RUNNER), "wait", run_id], cwd=root, env=env, timeout=_RUN_TIMEOUT_S
    )
    assert waited.returncode == 0, waited.stdout + waited.stderr
    return run_dir


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
