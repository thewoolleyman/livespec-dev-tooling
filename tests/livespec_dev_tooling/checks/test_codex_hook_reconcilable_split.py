"""Module decomposition and graceful-skip coverage for the Codex hook check."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import codex_hook_reconcilable

__all__: list[str] = []

_CHECKS_DIR = Path(codex_hook_reconcilable.__file__).resolve().parent


def _init_repo(*, root: Path) -> None:
    """Initialize and stage the fixture tree."""
    for args in (("init", "--quiet"), ("add", ".")):
        completed = subprocess.run(("git", *args), cwd=root, capture_output=True, check=False)
        assert completed.returncode == 0


def _write(*, path: Path, value: object) -> None:
    """Write a JSON fixture under a repository."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value), encoding="utf-8")


def _events(*, capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """Decode the structured stderr events."""
    return [json.loads(line) for line in capsys.readouterr().err.splitlines()]


def test_hook_validation_lives_in_cohesive_private_siblings() -> None:
    """Hook-file validation and shared helpers moved out of the discovery module."""
    payload_path = _CHECKS_DIR / "_codex_hook_payload.py"
    support_path = _CHECKS_DIR / "_codex_hook_support.py"
    assert payload_path.is_file()
    assert support_path.is_file()
    payload = importlib.import_module("livespec_dev_tooling.checks._codex_hook_payload")
    support = importlib.import_module("livespec_dev_tooling.checks._codex_hook_support")
    assert callable(payload.check_hooks_file)
    for name in ("emit_failure", "read_json", "relative_path", "payload_contains"):
        assert callable(getattr(support, name))
    for old in ("_check_hooks_file", "_check_group", "_check_command", "_HookContext", "_fail"):
        assert not hasattr(codex_hook_reconcilable, old)


def test_skips_outside_a_git_working_tree(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A directory that is no Git working tree is a graceful skip, not a failure."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 0
    events = _events(capsys=capsys)
    assert events[0]["check_id"] == "codex_hook_reconcilable"
    assert "not inside a Git working tree" in str(events[0]["message"])


def test_skips_when_git_cannot_start(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing `git` executable is a graceful skip with a warning."""

    def _no_git(argv: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", _no_git)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 0
    events = _events(capsys=capsys)
    assert events[0]["level"] == "warning"
    assert "git is unavailable" in str(events[0]["message"])


def _patch_second_call(*, monkeypatch: pytest.MonkeyPatch, root: Path, failure: str) -> None:
    """Let `git rev-parse` succeed and make `git ls-files` fail as `failure`."""

    def _fake(argv: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[1] == "rev-parse":
            return subprocess.CompletedProcess(argv, 0, f"{root}\n", "")
        if failure == "oserror":
            raise FileNotFoundError(argv[0])
        return subprocess.CompletedProcess(argv, 128, "", "fatal")

    monkeypatch.setattr(subprocess, "run", _fake)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [("oserror", "git is unavailable"), ("status", "could not list tracked files")],
)
def test_skips_when_tracked_files_cannot_be_listed(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    reason: str,
) -> None:
    """A failing `git ls-files` is a graceful skip naming why."""
    _patch_second_call(monkeypatch=monkeypatch, root=tmp_path, failure=failure)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 0
    assert reason in str(_events(capsys=capsys)[0]["message"])


def test_rejects_unparseable_manifest(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A manifest that is not JSON fails, naming the manifest."""
    manifest = tmp_path / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text("{not json", encoding="utf-8")
    _init_repo(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 4
    finding = _events(capsys=capsys)[0]
    assert finding["failure_mode"] == "unparseable_manifest"
    assert finding["manifest"] == ".codex-plugin/plugin.json"


def test_rejects_non_object_manifest(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A manifest that parses but is not an object fails as malformed."""
    _write(path=tmp_path / ".codex-plugin" / "plugin.json", value=["hooks"])
    _init_repo(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 4
    assert _events(capsys=capsys)[0]["failure_mode"] == "malformed_manifest"


def test_rejects_matcher_group_that_is_not_an_object(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A matcher group that is not an object fails as a malformed hooks file."""
    _write(path=tmp_path / ".codex-plugin" / "plugin.json", value={})
    _write(path=tmp_path / "hooks" / "hooks.json", value={"hooks": {"Stop": ["bad"]}})
    _init_repo(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 4
    finding = _events(capsys=capsys)[0]
    assert finding["failure_mode"] == "malformed_hooks_file"
    assert finding["path"] == "hooks/hooks.json"


def test_ignores_entries_without_a_string_command(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An entry whose `command` is absent or not a string is not a command."""
    _write(path=tmp_path / ".codex-plugin" / "plugin.json", value={})
    _write(
        path=tmp_path / "hooks" / "hooks.json",
        value={"hooks": {"Stop": [{"hooks": [{"type": "prompt"}, {"command": 5}]}]}},
    )
    _init_repo(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert codex_hook_reconcilable.main() == 0
    assert _events(capsys=capsys)[0]["commands_checked"] == 0
