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
                args, 0, "git@github.com:livespec-ai/livespec.git\n", ""
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
        owner="livespec-ai",
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


class _OriginRunner:
    def __init__(self, *, origin: str) -> None:
        self._origin = origin

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
            return subprocess.CompletedProcess(args, 0, f"{self._origin}\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_every_audited_owner_is_owned_and_any_other_owner_is_excluded(tmp_path: Path) -> None:
    config = ProbeConfig(
        host="vps",
        user="ubuntu",
        owner="livespec-ai,thewoolleyman",
        expected_name="Chad Woolley",
        expected_email="thewoolleyman@gmail.com",
        roots=(str(tmp_path),),
    )
    verdicts: dict[str, int] = {}
    for origin in (
        "git@github.com:livespec-ai/livespec.git",
        "git@github.com:thewoolleyman/poweredge-xubuntu-info.git",
        "git@github.com:mi-homelab/homelab.git",
    ):
        candidate = tmp_path / origin.rsplit("/", 1)[-1]
        candidate.mkdir()
        owned, excluded, _blind = repositories(
            config=config, runner=_OriginRunner(origin=origin), candidates=[candidate]
        )
        verdicts[origin] = len(owned) - len(excluded)

    assert verdicts == {
        "git@github.com:livespec-ai/livespec.git": 1,
        "git@github.com:thewoolleyman/poweredge-xubuntu-info.git": 1,
        "git@github.com:mi-homelab/homelab.git": -1,
    }


def test_the_remote_probe_names_both_audited_owners() -> None:
    assert "livespec-ai,thewoolleyman" in probe_args(host="vps")
