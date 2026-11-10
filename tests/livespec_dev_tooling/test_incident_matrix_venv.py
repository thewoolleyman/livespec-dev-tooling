"""The incident decision's environment installs only hash-pinned binary wheels, and fails closed.

Work-item livespec-dev-tooling-hlxbsv, the re-review of
livespec-dev-tooling#3966. The decision step needs PyYAML (the call-site parse)
and typing_extensions (the sanctioned `gh_read` client). A workflow `run:`
block may reach no dev tool directly, so `incident_matrix_venv` creates the
throwaway environment and runs the one pinned install. Each case sits beside a
negative control.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_matrix_venv
from livespec_dev_tooling.incident_matrix_venv import REQUIREMENTS, install_argv, prepare

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[0-9][^ ]*) \\$", re.MULTILINE)
_LOCKED = re.compile(r'^name = "([^"]+)"\nversion = "([^"]+)"$', re.MULTILINE)
_HASH = re.compile(r"^    --hash=sha256:[0-9a-f]{64}(?: \\)?$")


def _completed(*, returncode: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


def test_the_install_is_hash_pinned_and_binary_only():
    argv = install_argv(python=Path("/env/bin/python"))
    assert argv == [
        "/env/bin/python",
        "-m",
        "pip",
        "install",
        "--quiet",
        "--disable-pip-version-check",
        "--require-hashes",
        "--only-binary=:all:",
        "-r",
        str(REQUIREMENTS),
    ]
    assert REQUIREMENTS.name == "incident_matrix_requirements.txt"


def test_every_requirement_is_pinned_to_the_lockfile_release_by_hash():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    pins = {m["name"].lower().replace("_", "-"): m["version"] for m in _PIN.finditer(text)}
    lock = (_REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    locked = dict(_LOCKED.findall(lock))
    body = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert pins == {"pyyaml": locked["pyyaml"], "typing-extensions": locked["typing-extensions"]}
    assert all(_PIN.match(line) or _HASH.match(line) for line in body), body
    # Negative control: a requirement line without a hash continuation is not a pin.
    assert _PIN.search("PyYAML==6.0.3\n") is None


def test_a_prepared_environment_runs_the_pinned_install(tmp_path):
    create = Mock()
    run = Mock(return_value=_completed(returncode=0))
    assert prepare(target=tmp_path / "env", create=create, run=run) == 0
    assert create.call_args.args == (str(tmp_path / "env"),)
    assert create.call_args.kwargs == {"with_pip": True, "clear": True}
    assert run.call_args.args == (install_argv(python=tmp_path / "env" / "bin" / "python"),)
    assert run.call_args.kwargs == {"check": False}


@pytest.mark.parametrize(
    "error", [OSError("no venv"), subprocess.CalledProcessError(1, "ensurepip")]
)
def test_a_failed_creation_fails_closed_and_installs_nothing(tmp_path, error):
    run = Mock(return_value=_completed(returncode=0))
    assert prepare(target=tmp_path, create=Mock(side_effect=error), run=run) == 1
    assert run.call_count == 0


def test_a_failed_install_fails_closed(tmp_path):
    run = Mock(return_value=_completed(returncode=1))
    assert prepare(target=tmp_path, create=Mock(), run=run) == 1
    # Negative control: the same environment with a clean install succeeds.
    assert (
        prepare(target=tmp_path, create=Mock(), run=Mock(return_value=_completed(returncode=0)))
        == 0
    )


def test_main_prepares_the_named_directory(tmp_path, monkeypatch):
    create = Mock()
    run = Mock(return_value=_completed(returncode=0))
    monkeypatch.setattr(incident_matrix_venv.venv, "create", create)
    monkeypatch.setattr(incident_matrix_venv.subprocess, "run", run)
    assert incident_matrix_venv.main(argv=[str(tmp_path / "decision")]) == 0
    assert create.call_args.args == (str(tmp_path / "decision"),)
    assert run.call_args.args[0][0] == str(tmp_path / "decision" / "bin" / "python")
