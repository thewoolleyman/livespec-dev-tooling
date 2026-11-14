"""The suite never submits a real gate Job unless a test opts in (livespec-dev-tooling-qpgiip).

`tests/conftest.py` carries two autouse fixtures for this. The first keeps every
commit-time replay on its local route. The second fails any test whose
`subprocess.run` would create a real gate Job through the installed gates
credential wrapper. These tests drive both through their real seams.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling import commit_replay_delegate, gate_credential
from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV, GATES_WRAPPER

# Captured at import, before any per-test fixture replaces it.
_UNGUARDED_RUN = subprocess.run

_SUBMISSION = [GATES_WRAPPER, "kubectl", "--namespace", "gates", "create", "--filename", "-"]


def test_a_commit_replay_on_a_credentialed_opted_in_host_stays_local(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readable kubeconfig and the opt-in together still leave a test's replay local."""
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("apiVersion: v1\n", encoding="utf-8")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n", encoding="utf-8"
    )

    host_can_delegate = gate_credential.gates_kubeconfig_readable()
    verdict = commit_replay_delegate.run_replay(repo_root=tmp_path, pytest_argv=["pytest"])

    assert host_can_delegate is True
    assert verdict.local is True
    assert verdict.reason == "gates kubeconfig is not readable"
    assert verdict.job_name is None


def test_a_real_gate_job_submission_fails_the_test_naming_the_command(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installed wrapper carrying `kubectl create` never runs from a test."""
    monkeypatch.setattr(
        "shutil.which",
        lambda name, *_args, **_kwargs: f"/usr/local/bin/{name}",
    )

    with pytest.raises(pytest.fail.Exception, match="reached a real gate Job submission"):
        _ = subprocess.run(_SUBMISSION, input="", check=False)


def test_a_fake_wrapper_under_the_temporary_directory_still_runs(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A test's own stand-in wrapper is not a real submission, so it runs."""
    fake = tmp_path / GATES_WRAPPER
    _ = fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    completed = subprocess.run(_SUBMISSION, input="", check=False)

    assert completed.returncode == 0


def test_an_unmarked_test_runs_under_the_guard() -> None:
    """Every test gets the guarded `subprocess.run` by default."""
    assert subprocess.run is not _UNGUARDED_RUN


@pytest.mark.real_gate_job
def test_a_marked_test_runs_with_the_unguarded_subprocess() -> None:
    """The `real_gate_job` marker is the one opt-in."""
    assert subprocess.run is _UNGUARDED_RUN
