"""Process-environment and CLI half of the standalone host identity probe."""

import json
import os
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._git_identity_host_canary import canaries
from livespec_dev_tooling.fleet._git_identity_host_git import (
    JsonObject,
    ProbeConfig,
    Runner,
    default_runner,
    discover,
    global_config,
    repositories,
)

__all__: list[str] = []
AUTHOR_KEYS = (
    b"GIT_AUTHOR_NAME",
    b"GIT_AUTHOR_EMAIL",
    b"LIVESPEC_GIT_AUTHOR_NAME",
    b"LIVESPEC_GIT_AUTHOR_EMAIL",
)
LONG_LIVED = (
    "tmux",
    "codex",
    "claude",
    "fabro",
    "overseer",
    "dispatcher",
    "runner",
    "agent",
    "bash",
    "zsh",
    "sshd",
)


def author_values(  # pragma: no cover - follow-up Red cycle
    *, raw: bytes
) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        key, separator, value = entry.partition(b"=")
        if separator and key in AUTHOR_KEYS:
            values[key.decode()] = value.decode(errors="replace")
    return values


def process_environment(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig
) -> JsonObject:
    entries: list[JsonObject] = []
    unreadable: list[int] = []
    pids = sorted(
        (item for item in Path("/proc").iterdir() if item.name.isdigit()),
        key=lambda item: int(item.name),
    )
    for proc in pids:
        try:
            raw = (proc / "environ").read_bytes()
            comm = (proc / "comm").read_text(encoding="utf-8", errors="replace").strip()
            command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            unreadable.append(int(proc.name))
            continue
        values = author_values(raw=raw)
        relevant = any(marker in f"{comm} {command}".lower() for marker in LONG_LIVED)
        entries.append(
            {
                "pid": int(proc.name),
                "comm": comm,
                "relevant": relevant,
                "author_environment": values,
            }
        )
    violations: list[JsonObject] = []
    for entry in entries:
        untyped_values = entry["author_environment"]
        if not isinstance(untyped_values, dict):
            continue
        values = cast("dict[str, object]", untyped_values)
        for key, value in values.items():
            expected = config.expected_name if key.endswith("_NAME") else config.expected_email
            if value != expected:
                violations.append({"pid": entry["pid"], "variable": key})
    return {
        "total": len(entries) + len(unreadable),
        "audited": len(entries),
        "unreadable": unreadable,
        "blind": len(unreadable),
        "processes": entries,
        "violations": violations,
    }


def tmux_environment(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner
) -> JsonObject:
    answer = runner(args=("sudo", "-u", config.user, "tmux", "show-environment", "-g"))
    if answer.returncode != 0 and "no server running" in answer.stderr.lower():
        return {
            "scope": "default-user-socket-supplemental",
            "servers": 0,
            "blind": 0,
            "violations": [],
        }
    if answer.returncode != 0:
        return {
            "scope": "default-user-socket-supplemental",
            "status": "unavailable",
            "servers": 0,
            "blind": 0,
            "violations": [],
        }
    values: dict[str, str] = {}
    for line in answer.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL"}:
            values[key] = value
    violations: list[JsonObject] = []
    for key, value in values.items():
        expected = config.expected_name if key == "GIT_AUTHOR_NAME" else config.expected_email
        if value != expected:
            violations.append({"variable": key})
    return {
        "scope": "default-user-socket-supplemental",
        "servers": 1,
        "blind": 0,
        "author_environment": values,
        "violations": violations,
    }


def build_report(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner
) -> JsonObject:
    candidates: list[Path] = []
    roots: list[JsonObject] = []
    blind: list[str] = []
    for root in config.roots:
        found, status, errors = discover(root=root)
        candidates.extend(found)
        roots.append(status)
        blind.extend(errors)
    global_result, global_errors = global_config(config=config, runner=runner)
    blind.extend(global_errors)
    owned, excluded, repository_errors = repositories(
        config=config, runner=runner, candidates=candidates
    )
    blind.extend(repository_errors)
    return {
        "schema_version": 1,
        "host": config.host,
        "global_config": global_result,
        "roots": roots,
        "owned_repositories": owned,
        "excluded_repositories": excluded,
        "process_author_environment": process_environment(config=config),
        "tmux_author_environment": tmux_environment(config=config, runner=runner),
        "commit_canaries": canaries(config=config, runner=runner),
        "failures": [] if global_result.get("passed") is True else ["global-config"],
        "blind": blind,
    }


def main() -> int:  # pragma: no cover - follow-up Red cycle
    host, owner, expected_name, expected_email, roots_json = sys.argv[1:]
    parsed_roots = json.loads(roots_json)
    if not isinstance(parsed_roots, list):
        return 2
    roots = cast("list[object]", parsed_roots)
    config = ProbeConfig(
        host=host,
        user=os.environ["USER"],
        owner=owner,
        expected_name=expected_name,
        expected_email=expected_email,
        roots=tuple(str(item) for item in roots),
    )
    _ = sys.stdout.write(
        json.dumps(build_report(config=config, runner=default_runner), sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - remote script boundary
    sys.exit(main())
