"""Every expedited-incident Git call rides one helper, one timeout and one failure reason.

livespec-dev-tooling-gwzviw: six private wrappers each chose their own timeout
(30 s, none, 15 s, 120 s, none) and their own failure shape (a raised
CalledProcessError, a raw TimeoutExpired, an unguarded OSError, a returncode the
caller had to read). One refusal now names a failed incident Git call.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_git as module
from livespec_dev_tooling.incident_git import IncidentGitError, git_text, run_git

__all__: list[str] = []

_PACKAGE = Path(module.__file__).resolve().parent
_INCIDENT_MODULES = (
    "incident_hook_process.py",
    "_incident_focused_scope.py",
    "_incident_inverse_git.py",
    "_incident_original_run_ports.py",
    "checks/_red_green_replay_incident.py",
)


def _repository(*, tmp_path: Path) -> Path:
    for args in (["init", "-q"], ["commit", "--allow-empty", "-qm", "fixture"]):
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=f@example.com", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
    return tmp_path


def test_the_one_timeout_is_a_positive_bound_every_call_carries(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, b"out", b"")

    monkeypatch.setattr(subprocess, "run", run)
    done = run_git(repo=tmp_path, args=["write-tree"], env={"A": "b"}, data=b"in")
    assert done.stdout == b"out"
    assert seen["argv"] == ["git", "write-tree"]
    assert seen["cwd"] == tmp_path
    assert seen["env"] == {"A": "b"}
    assert seen["input"] == b"in"
    assert seen["timeout"] == module.INCIDENT_GIT_TIMEOUT_SECONDS > 0


def test_text_is_decoded_and_stripped(*, tmp_path: Path) -> None:
    repo = _repository(tmp_path=tmp_path)
    head = run_git(repo=repo, args=["rev-parse", "HEAD"]).stdout.decode().strip()
    assert git_text(repo=repo, args=["rev-parse", "HEAD"]) == head
    assert len(head) in {40, 64}


def test_a_nonzero_exit_names_the_command_and_its_stderr(*, tmp_path: Path) -> None:
    repo = _repository(tmp_path=tmp_path)
    with pytest.raises(IncidentGitError) as refused:
        run_git(repo=repo, args=["rev-parse", "--verify", "no-such-ref"])
    assert str(refused.value).startswith("incident git rev-parse exited ")
    assert refused.value.returncode != 0
    assert refused.value.cmd[:2] == ("git", "rev-parse")
    assert refused.value.stderr


def test_an_expected_nonzero_exit_is_returned_when_the_caller_asked_not_to_check(
    *, tmp_path: Path
) -> None:
    repo = _repository(tmp_path=tmp_path)
    head = git_text(repo=repo, args=["rev-parse", "HEAD"])
    done = run_git(repo=repo, args=["merge-base", "--is-ancestor", "0" * 40, head], check=False)
    assert done.returncode != 0


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (
            subprocess.TimeoutExpired(["git", "fetch"], 1),
            f"incident git fetch exceeded its {module.INCIDENT_GIT_TIMEOUT_SECONDS} s ceiling",
        ),
        (FileNotFoundError("no git"), "incident git fetch could not run: no git"),
    ],
)
@pytest.mark.parametrize("check", [True, False])
def test_a_timeout_or_a_missing_program_is_the_same_named_error_whether_checked_or_not(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception, reason: str, check: bool
) -> None:
    def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        _ = argv
        raise failure

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(IncidentGitError) as refused:
        run_git(repo=tmp_path, args=["fetch", "origin"], check=check)
    assert str(refused.value) == reason
    assert refused.value.returncode is None


def _git_argv_sites(*, tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.List)
        and node.elts
        and isinstance(node.elts[0], ast.Constant)
        and node.elts[0].value == "git"
    ]


@pytest.mark.parametrize("name", _INCIDENT_MODULES)
def test_no_incident_module_spells_its_own_git_command(*, name: str) -> None:
    tree = ast.parse((_PACKAGE / name).read_text(encoding="utf-8"))
    assert _git_argv_sites(tree=tree) == []


def test_the_helper_is_the_only_incident_module_that_spells_a_git_command() -> None:
    tree = ast.parse((_PACKAGE / "incident_git.py").read_text(encoding="utf-8"))
    assert len(_git_argv_sites(tree=tree)) == 1
