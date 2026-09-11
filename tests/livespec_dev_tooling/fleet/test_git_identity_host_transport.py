"""Regression tests for remote probe transport and stale worktree rows."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._git_identity_audit_model import probe_args
from livespec_dev_tooling.fleet._git_identity_host_git import ProbeConfig, repositories

__all__: list[str] = []


def test_remote_probe_is_one_shell_quoted_command() -> None:
    args = probe_args(host="hp-xubuntu")

    assert args[:7] == (
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "cwoolley@hp-xubuntu",
        "--",
    )
    assert len(args) == 8
    assert "'Chad Woolley'" in args[-1]
    assert "'[\"/home/cwoolley/workspace\"]'" in args[-1]


class _StaleWorktreeRunner:
    def __call__(
        self,
        *,
        args: tuple[str, ...],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del env
        if args[1:3] == ("rev-parse", "--path-format=absolute"):
            return subprocess.CompletedProcess(args, 0, f"{cwd}/.git\n", "")
        if args[1:4] == ("remote", "get-url", "origin"):
            return subprocess.CompletedProcess(
                args, 0, "git@github.com:thewoolleyman/livespec.git\n", ""
            )
        if args[1:4] == ("worktree", "list", "--porcelain"):
            return subprocess.CompletedProcess(args, 0, "worktree /missing/worktree\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_stale_registered_worktree_is_blind_not_a_crash_or_pass(tmp_path: Path) -> None:
    candidate = tmp_path / "livespec"
    candidate.mkdir()
    config = ProbeConfig(
        host="vps",
        user="ubuntu",
        owner="thewoolleyman",
        expected_name="Chad Woolley",
        expected_email="thewoolleyman@gmail.com",
        roots=(str(tmp_path),),
    )

    owned, excluded, blind = repositories(
        config=config,
        runner=_StaleWorktreeRunner(),
        candidates=[candidate],
    )

    assert excluded == []
    assert owned[0]["worktrees"] == []
    assert blind == ["worktree-missing:/missing/worktree"]
