"""The shared local pre-commit aggregate evidence entry point."""

from __future__ import annotations

import importlib
import io
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "pre_commit_aggregate.py"
_MODULE = "livespec_dev_tooling.pre_commit_aggregate"


def _module() -> object:
    """Import the new entry point only after its Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def test_entry_point_records_a_passing_clean_same_tree_aggregate(*, tmp_path: Path) -> None:
    """The shared command preserves the aggregate status and certifies its exact index tree."""
    module = _module()
    writes: list[dict[str, object]] = []

    status = module.run_aggregate(
        command=["just", "hook_gate=1", "check"],
        cwd=tmp_path,
        execute=lambda **_kwargs: module.AggregateResult(
            exit_status=0, output=b"aggregate output\n"
        ),
        git_answer=lambda *, argv, **_kwargs: {
            ("git", "write-tree"): (0, "same-tree\n"),
            ("git", "diff", "--quiet"): (0, ""),
            ("git", "ls-files", "--others", "--exclude-standard"): (0, ""),
        }[tuple(argv)],
        record=lambda **kwargs: writes.append(kwargs),
    )

    assert status == 0
    assert len(writes) == 1
    assert writes[0]["cwd"] == tmp_path
    assert writes[0]["tree_hash"] == "same-tree"
    assert str(writes[0]["run_id"]).endswith("same-tree")
    assert str(writes[0]["output_checksum"]).startswith("sha256:")


@pytest.mark.parametrize(
    ("exit_status", "diff", "untracked", "after_tree"),
    [
        (7, 0, "", "same-tree"),
        (0, 1, "", "same-tree"),
        (0, 0, "untracked.py\n", "same-tree"),
        (0, 0, "", "changed-tree"),
    ],
)
def test_entry_point_never_records_failed_or_non_identical_aggregate_evidence(
    *,
    tmp_path: Path,
    exit_status: int,
    diff: int,
    untracked: str,
    after_tree: str,
) -> None:
    """Every failed, dirty, or index-changed aggregate leaves no reusable evidence."""
    module = _module()
    writes: list[dict[str, object]] = []
    trees = iter(("same-tree", after_tree))

    def git_answer(*, argv: list[str], **_kwargs: object) -> tuple[int, str]:
        if tuple(argv) == ("git", "write-tree"):
            return (0, f"{next(trees)}\n")
        if tuple(argv) == ("git", "diff", "--quiet"):
            return (diff, "")
        return (0, untracked)

    status = module.run_aggregate(
        command=["just", "hook_gate=1", "check"],
        cwd=tmp_path,
        execute=lambda **_kwargs: module.AggregateResult(exit_status=exit_status, output=b"output"),
        git_answer=git_answer,
        record=lambda **kwargs: writes.append(kwargs),
    )

    assert status == exit_status
    assert writes == []


def test_cli_passes_the_consumer_aggregate_command_to_the_entry_point(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consumers invoke one command rather than reproducing evidence guards in shell."""
    module = _module()
    called: list[dict[str, object]] = []
    monkeypatch.setattr(module, "run_aggregate", lambda **kwargs: called.append(kwargs) or 7)
    monkeypatch.setattr(sys, "argv", ["pre_commit_aggregate", "--", "just", "hook_gate=1", "check"])

    assert module.main() == 7
    assert called[0]["command"] == ["just", "hook_gate=1", "check"]


def test_entry_point_io_helpers_preserve_output_and_keep_evidence_advisory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real process and evidence helpers forward output but never change the verdict."""
    module = _module()
    stdout = _BinaryStream()
    stderr = _BinaryStream()
    monkeypatch.setattr(module.sys, "stdout", stdout)
    monkeypatch.setattr(module.sys, "stderr", stderr)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: _Completed(returncode=7, stdout=b"out", stderr=b"err"),
    )

    result = module._execute(command=["aggregate"], cwd=tmp_path)  # noqa: SLF001

    assert result == module.AggregateResult(exit_status=7, output=b"outerr")
    assert stdout.buffer.getvalue() == b"out"
    assert stderr.buffer.getvalue() == b"err"
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git", "write-tree"],
            returncode=0,
            stdout="tree\n",
            stderr="",
        ),
    )
    assert module._git_answer(argv=["git", "write-tree"], cwd=tmp_path) == (0, "tree\n")  # noqa: SLF001
    monkeypatch.setattr(module.subprocess, "run", _raise_os_error)
    assert module._git_answer(argv=["git", "write-tree"], cwd=tmp_path) == (1, "")  # noqa: SLF001
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        module, "write_pre_commit_evidence", lambda **kwargs: recorded.append(kwargs)
    )

    module._record(  # noqa: SLF001
        cwd=tmp_path,
        run_id="run",
        output_checksum="sha256:output",
        tree_hash="tree",
    )

    assert recorded[0]["tree_hash"] == "tree"


def test_cli_accepts_a_command_without_separator_and_rejects_an_empty_one(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry point accepts argparse's direct remainder and rejects no aggregate."""
    module = _module()
    monkeypatch.setattr(module, "run_aggregate", lambda **_kwargs: 0)
    monkeypatch.setattr(sys, "argv", ["pre_commit_aggregate", "just", "check"])
    assert module.main() == 0
    monkeypatch.setattr(sys, "argv", ["pre_commit_aggregate"])
    with pytest.raises(SystemExit, match="2"):
        _ = module.main()


def test_own_pre_commit_recipe_uses_the_shared_entry_point() -> None:
    """This repository's local aggregate does not retain an inline evidence implementation."""
    recipe = _REPO_ROOT / "scripts" / "just" / "check-pre-commit.sh"
    text = recipe.read_text(encoding="utf-8")
    assert "livespec_dev_tooling.pre_commit_aggregate" in text
    assert "green_token write-pre-commit" not in text


class _BinaryStream:
    """A stdio stand-in exposing the bytes buffer the entry point writes."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()


class _Completed:
    """The subprocess fields the entry point reads."""

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _raise_os_error(*_args: object, **_kwargs: object) -> object:
    """Raise the unreadable-git condition the entry point fails closed on."""
    raise OSError("git unavailable")
