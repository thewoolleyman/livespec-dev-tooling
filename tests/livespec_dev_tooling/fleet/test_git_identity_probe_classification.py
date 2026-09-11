"""Classification tests for supplemental and unowned probe observations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._git_identity_host_git import ProbeConfig, repositories
from livespec_dev_tooling.fleet._git_identity_host_probe import tmux_environment

__all__: list[str] = []


class _TmuxAbsentRunner:
    def __call__(
        self,
        *,
        args: tuple[str, ...],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env
        return subprocess.CompletedProcess(args, 1, "", "sudo: 'tmux': command not found\n")


class _NoOriginRunner:
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
            return subprocess.CompletedProcess(args, 2, "", "error: No such remote 'origin'\n")
        return subprocess.CompletedProcess(args, 0, "true\n", "")


def _config(*, root: Path) -> ProbeConfig:
    return ProbeConfig(
        host="vps",
        user="ubuntu",
        owner="thewoolleyman",
        expected_name="Chad Woolley",
        expected_email="thewoolleyman@gmail.com",
        roots=(str(root),),
    )


def test_unavailable_default_tmux_socket_is_non_authoritative_supplement() -> None:
    report = tmux_environment(config=_config(root=Path("/tmp")), runner=_TmuxAbsentRunner())

    assert report == {
        "scope": "default-user-socket-supplemental",
        "status": "unavailable",
        "servers": 0,
        "blind": 0,
        "violations": [],
    }


def test_repository_without_origin_is_explicitly_excluded_not_blind(tmp_path: Path) -> None:
    candidate = tmp_path / "local-only"
    candidate.mkdir()

    owned, excluded, blind = repositories(
        config=_config(root=tmp_path),
        runner=_NoOriginRunner(),
        candidates=[candidate],
    )

    assert owned == []
    assert excluded == [{"path": str(candidate), "origin": None, "reason": "no-origin"}]
    assert blind == []
