"""Cheap release-ref checks and command timing for Claude plugin reconciliation.

Every startup checks moving refs; cached timestamps never certify currency.
Uncertainty leaves the ordinary CLI reconciliation in charge. Artifact and
registry verification remain mandatory in ``ensure``, even when no CLI runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    PluginCommandOutcome,
    PluginCommandRunner,
    plugin_command_answer,
    subprocess_runner,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed

__all__: list[str] = ["_logged_runner", "_startup_currency"]
_REF_ROW_WIDTH = 2


class _ResolveRef(Protocol):
    """Resolve one declared marketplace source to its current commit, or None."""

    def __call__(self, *, source: dict[str, object]) -> str | None: ...


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _remote_commit(*, source: dict[str, object]) -> str | None:
    """Resolve an exact declared GitHub ref, or withhold proof of currency."""
    repo, ref = source.get("repo"), source.get("ref")
    if not isinstance(repo, str) or not isinstance(ref, str) or not ref:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or any(
        part in {".", ".."} for part in repo.split("/")
    ):
        return None
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        return ref.lower()
    try:
        result = subprocess.run(
            [
                "git",
                "ls-remote",
                f"https://github.com/{repo}.git",
                f"refs/heads/{ref}",
                f"refs/tags/{ref}",
                f"refs/tags/{ref}^{{}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    refs = {
        fields[1]: fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == _REF_ROW_WIDTH
        and re.fullmatch(r"[0-9a-f]{40}", fields[0])
    }
    return (
        refs.get(f"refs/heads/{ref}")
        or refs.get(f"refs/tags/{ref}^{{}}")
        or refs.get(f"refs/tags/{ref}")
    )


def _registered_source(*, entry: object, known: object) -> bool:
    declared, installed = _mapping(value=entry), _mapping(value=known)
    source = _mapping(value=declared.get("source"))
    location = installed.get("installLocation")
    return (
        source.get("source") == "github"
        and isinstance(source.get("repo"), str)
        and isinstance(source.get("ref"), str)
        and installed.get("source") == source
        and isinstance(location, str)
        and Path(location).is_dir()
    )


def _startup_currency(
    *,
    settings_text: str,
    registry_text: str | None,
    marketplaces_text: str | None,
    project_root: str,
    resolve_ref: _ResolveRef = _remote_commit,
) -> tuple[frozenset[str], frozenset[str]]:
    """Plugins and registrations whose unchanged state permits skipping CLI calls."""
    try:
        settings = _mapping(value=json.loads(settings_text))
        registry = _mapping(value=json.loads(registry_text or "null"))
        known = _mapping(value=json.loads(marketplaces_text or "null"))
    except json.JSONDecodeError:
        return frozenset(), frozenset()
    marketplaces = _mapping(value=settings.get("extraKnownMarketplaces"))
    registered = {
        name: _mapping(value=_mapping(value=entry).get("source"))
        for name, entry in marketplaces.items()
        if _registered_source(entry=entry, known=known.get(name))
    }
    # These are four small, network-bound ref lookups on the current fleet,
    # rather than twelve Claude processes. Each child has its own deadline.
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {name: pool.submit(resolve_ref, source=src) for name, src in registered.items()}
        commits = {name: future.result() for name, future in pending.items()}
    plugins = _mapping(value=registry.get("plugins"))
    enabled = settings.get("enabledPlugins")
    names = (
        cast("list[object]", enabled)
        if isinstance(enabled, list)
        else [name for name, flag in _mapping(value=enabled).items() if flag is True]
    )
    current: set[str] = set()
    for name in names:
        if not isinstance(name, str):
            continue
        commit = commits.get(name.rsplit("@", maxsplit=1)[-1])
        records = plugins.get(name)
        if (
            commit
            and isinstance(records, list)
            and any(
                _mapping(value=record).get("projectPath") == project_root
                and _mapping(value=record).get("scope") == "project"
                and _mapping(value=record).get("gitCommitSha") == commit
                for record in cast("list[object]", records)
            )
        ):
            current.add(name)
    return frozenset(current), frozenset(
        f'{source["repo"]}@{source["ref"]}' for source in registered.values()
    )


def _command_log(*, event: str, args: tuple[str, ...], **fields: object) -> None:
    """Append nonsecret argv/outcome metadata, never child streams or environment."""
    root = Path.home() / ".local/state/livespec-dev-tooling"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "event": event,
        "argv": args,
        **fields,
    }
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(root / "plugin-commands.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fchmod(fd, 0o600)
            _ = os.write(fd, (json.dumps(record) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        _ = sys.stderr.write("ensure_plugins: command timing log unavailable\n")


def _logged_runner(
    *, args: tuple[str, ...], runner: PluginCommandRunner = subprocess_runner
) -> PluginCommandOutcome:
    start = time.monotonic()
    _command_log(event="command-start", args=args)
    outcome = runner(args=args)
    answer = plugin_command_answer(outcome=outcome)
    _command_log(
        event="command-end",
        args=args,
        elapsed_seconds=time.monotonic() - start,
        returncode=None if isinstance(answer, InvocationNotPerformed) else answer.returncode,
        invoked=not isinstance(answer, InvocationNotPerformed),
    )
    return outcome
