"""The range gate refuses a commit whose recorded Red test is absent or its checksum is wrong.

Measured: a commit carried `TDD-Red-Test` and `TDD-Red-Test-File-Checksum`
trailers naming a test file that its own tree did not hold (or held with other
bytes), so the recorded checksum matched nothing, and it merged. The rule: on
that commit's OWN tree the named path must exist and its sha256 must equal the
trailer, in the `sha256:<hex>` form the Red hook writes.
Every fixture is a real git repository.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling.checks import _red_green_replay_checksum as module
from livespec_dev_tooling.checks import red_green_replay

_TEST_PATH = "tests/test_x.py"
_IMPL = "def value() -> int:\n    return 2\n"
_TEST = "from livespec.foo import value\n\n\ndef test_value() -> None:\n    assert value() == 2\n"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["livespec"]\n'
    'source_tree_prefixes = ["livespec/"]\n'
)


def _git(*, repo: Path, args: list[str]) -> str:
    env_free = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env_free
    )
    return done.stdout.strip()


def _init(*, repo: Path) -> None:
    _git(repo=repo, args=["init", "-q"])
    _git(repo=repo, args=["config", "user.email", "t@example.com"])
    _git(repo=repo, args=["config", "user.name", "T"])
    _git(repo=repo, args=["config", "commit.gpgsign", "false"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "chore: base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])


def _commit(*, repo: Path, files: dict[str, str], message: str) -> str:
    for relative, text in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _digest(*, text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pair(*, test_path: str = _TEST_PATH, checksum: str) -> str:
    return (
        "feat: a pair\n\n"
        f"TDD-Red-Test: {test_path}\n"
        f"TDD-Red-Test-File-Checksum: {checksum}\n"
        "TDD-Green-Verified-At: 2026-11-10T00:00:00Z\n"
    )


def _run(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["red_green_replay"])
    code = red_green_replay.main()
    return code, capsys.readouterr().err


def test_a_commit_whose_recorded_test_is_absent_from_its_tree_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(repo=tmp_path)
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL},
        message=_pair(checksum=_digest(text=_TEST)),
    )

    code, err = _run(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 1
    assert sha in err
    assert _TEST_PATH in err
    assert "absent" in err


def test_a_commit_whose_recorded_checksum_differs_from_its_tree_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(repo=tmp_path)
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL, _TEST_PATH: _TEST},
        message=_pair(checksum=_digest(text="something else\n")),
    )

    code, err = _run(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 1
    assert sha in err
    assert _TEST_PATH in err
    assert "checksum" in err


def test_a_commit_whose_recorded_test_is_in_its_tree_but_not_its_diff_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The measured shape: another item's trailers, whose test already sat on master."""
    _init(repo=tmp_path)
    _commit(repo=tmp_path, files={"livespec/foo.py": "", _TEST_PATH: _TEST}, message="chore: t\n")
    _git(repo=tmp_path, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL},
        message=_pair(checksum=_digest(text=_TEST)),
    )

    code, err = _run(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 1
    assert sha in err
    assert _TEST_PATH in err
    assert "diff" in err


def test_a_commit_whose_recorded_checksum_matches_its_tree_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(repo=tmp_path)
    _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL, _TEST_PATH: _TEST},
        message=_pair(checksum=_digest(text=_TEST)),
    )

    code, err = _run(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (code, module.CHECK_ID in err) == (0, False)


def test_a_commit_without_red_trailers_is_not_judged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(repo=tmp_path)
    sha = _commit(repo=tmp_path, files={"docs/a.md": "x\n"}, message="docs: a\n")

    code, _err = _run(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 0
    assert module.verify_recorded_checksums(shas=[sha], base_ref="origin/master") == []


def test_a_suite_green_only_commit_is_not_judged(*, tmp_path: Path) -> None:
    _init(repo=tmp_path)
    message = "refactor: x\n\nTDD-Suite-Green-Captured-At: 2026-11-10T00:00:00Z\n"
    sha = _commit(repo=tmp_path, files={"livespec/foo.py": _IMPL}, message=message)

    assert module.verify_recorded_checksums(shas=[sha], base_ref="origin/master") == []


def test_an_incident_admitted_commit_keeps_its_exemption(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(repo=tmp_path)
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL},
        message=_pair(checksum=_digest(text=_TEST)),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "admitted_by_recorded_incident", lambda **_kw: True)

    assert module.verify_recorded_checksums(shas=[sha], base_ref="origin/master") == []


def test_a_forge_authored_revert_keeps_its_exemption(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(repo=tmp_path)
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _IMPL},
        message=_pair(checksum=_digest(text=_TEST)),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "is_forge_authored_revert", lambda **_kw: IOSuccess(True))  # noqa: FBT003

    assert module.verify_recorded_checksums(shas=[sha], base_ref="origin/master") == []
