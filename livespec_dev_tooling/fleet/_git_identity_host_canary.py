"""Temporary positive and negative Git commit canaries for one host."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from livespec_dev_tooling.fleet._git_identity_host_git import JsonObject, ProbeConfig, Runner

__all__: list[str] = []


def canaries(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner
) -> JsonObject:
    author_vars = {
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    }
    clean_env = {key: value for key, value in os.environ.items() if key not in author_vars}
    with tempfile.TemporaryDirectory(prefix="git-identity-audit-") as directory:
        root = Path(directory)
        _ = runner(args=("git", "init", "-q"), cwd=root, env=clean_env)
        positive = runner(
            args=("git", "commit", "--allow-empty", "-qm", "identity canary"),
            cwd=root,
            env=clean_env,
        )
        shown = runner(
            args=("git", "show", "-s", "--format=%an%x00%ae", "HEAD"),
            cwd=root,
            env=clean_env,
        )
        isolated_home = root / "isolated"
        isolated_home.mkdir()
        isolated = dict(clean_env, HOME=str(isolated_home), GIT_CONFIG_NOSYSTEM="1")
        missing = runner(
            args=(
                "git",
                "-c",
                "user.useConfigOnly=true",
                "commit",
                "--allow-empty",
                "-qm",
                "missing",
            ),
            cwd=root,
            env=isolated,
        )
        invalid = runner(
            args=(
                "git",
                "-c",
                "user.useConfigOnly=true",
                "-c",
                "user.name=",
                "-c",
                "user.email=",
                "commit",
                "--allow-empty",
                "-qm",
                "invalid",
            ),
            cwd=root,
            env=isolated,
        )
    parts = shown.stdout.rstrip("\n").split("\0") if shown.returncode == 0 else []
    complete = len(parts) == len(("name", "email"))
    return {
        "positive": {
            "passed": positive.returncode == 0
            and parts == [config.expected_name, config.expected_email],
            "author_name": parts[0] if complete else None,
            "author_email": parts[1] if complete else None,
        },
        "missing_identity": {"passed": missing.returncode != 0},
        "invalid_identity": {"passed": invalid.returncode != 0},
    }
