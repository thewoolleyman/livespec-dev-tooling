#!/usr/bin/env python3
"""Build the factory workspace sweep manifest from live Fabro and ledger state.

This program deliberately writes a *new* manifest before every timer pass.  A
workspace can outlive a sandbox-driver record, so directory discovery starts
at the workspace root and enriches each directory from every configured Fabro
instance and provider.  Failure to read either a run or its item's tenant is
represented in the manifest as a keep classification; it is never converted
to a deletion candidate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

_WORKSPACE_NAME = re.compile(r"^petri-(?P<run>[0-9A-Za-z]+)-l[0-9]+$")
_TERMINAL = frozenset({"succeeded", "failed"})


class ManifestConfigurationError(ValueError):
    """The controller configuration cannot safely generate a manifest."""

    @classmethod
    def missing(cls, key: str) -> ManifestConfigurationError:
        return cls(f"factory workspace manifest configuration needs a non-empty {key}")

    @classmethod
    def not_an_object(cls) -> ManifestConfigurationError:
        return cls("factory workspace manifest configuration must be a JSON object")


def mapping(value: object) -> Mapping[str, object] | None:
    """Narrow decoded JSON without trusting its untyped nested values."""
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def sequence(value: object) -> Sequence[object]:
    """Return JSON arrays only; strings and malformed configuration are empty."""
    if isinstance(value, list):
        return cast(list[object], value)
    if isinstance(value, tuple):
        return cast(tuple[object, ...], value)
    return ()


def string_value(config: Mapping[str, object], key: str) -> str:
    """Read one required command/configuration string."""
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestConfigurationError.missing(key)
    return value


def command(argv: Sequence[str], *, home: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a read command.  Missing tools and timeouts are evidence failures."""
    try:
        env = os.environ.copy()
        if home:
            env["HOME"] = home
        return subprocess.run(  # noqa: S603
            list(argv), check=False, text=True, capture_output=True, timeout=300, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(list(argv), 127, "", str(error))


def json_output(done: subprocess.CompletedProcess[str]) -> object | None:
    if done.returncode:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def run_end(run: Mapping[str, object]) -> str | None:
    """Return an ISO end time only for a terminal run with readable timing."""
    status = mapping(run.get("status"))
    if status is None or status.get("kind") not in _TERMINAL:
        return None
    started, wall = run.get("start_time"), run.get("wall_time_ms")
    if not isinstance(started, str) or not isinstance(wall, int | float):
        return None
    try:
        point = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError:
        return None
    if point.tzinfo is None:
        point = point.replace(tzinfo=timezone.utc)
    return (point + timedelta(milliseconds=wall)).isoformat()


def work_item_id(run: Mapping[str, object]) -> str | None:
    """Return the work item stamped on a Fabro run by the dispatcher.

    ``livespec.dispatch.id`` identifies one dispatch attempt, not a ledger
    record.  The controller must address the ledger and archive receipt with
    ``work.item.id``; conflating the two makes every otherwise-known row look
    tenant-unreadable.
    """
    labels = mapping(run.get("labels"))
    value = labels.get("work.item.id") if labels is not None else None
    return str(value) if value else None


def read_runs(*, config: Mapping[str, object]) -> tuple[dict[str, Mapping[str, object]], bool]:
    """Read all servers.  One unavailable server makes its unknown rows keep."""
    result: dict[str, Mapping[str, object]] = {}
    readable = True
    for instance_value in sequence(config.get("instances")):
        instance = mapping(instance_value)
        if instance is None:
            readable = False
            continue
        server, home = instance.get("server"), instance.get("home")
        if not isinstance(server, str):
            readable = False
            continue
        data = json_output(
            command(
                [string_value(config, "fabro_bin"), "ps", "-a", "--json", "--server", server],
                home=str(home) if home else None,
            )
        )
        if not isinstance(data, list):
            readable = False
            continue
        for row_value in cast(list[object], data):
            row = mapping(row_value)
            if row is not None and row.get("run_id"):
                result[str(row["run_id"]).upper()] = row
        # Ask every declared provider too.  Its records need not exist for a
        # directory to be considered: record-less directories are reconciled by
        # the run and ledger evidence above, not silently skipped.
        for provider in sequence(instance.get("providers")):
            if not isinstance(provider, str):
                readable = False
                continue
            records = json_output(
                command(
                    [
                        string_value(config, "lithos_bin"),
                        "--provider",
                        provider,
                        "--output",
                        "json",
                        "sandbox",
                        "list",
                    ],
                    home=str(home) if home else None,
                )
            )
            if not isinstance(records, list):
                readable = False
    return result, readable


def item_class(*, item: str | None, ledger_command: str) -> str:
    if not item:
        return "item-unmapped"
    done = command([*shlex.split(ledger_command), "show", item, "--json"])
    data = mapping(json_output(done))
    if data is None:
        return "tenant-unreadable"
    raw: object = data.get("status")
    if raw is None:
        raw = data.get("state", "")
    state = mapping(raw)
    if state is not None:
        raw = state.get("kind", "")
    normalized = str(raw).lower().replace("_", "-")
    return f"item-{normalized}" if normalized else "tenant-unreadable"


def checkout_state(directory: Path) -> tuple[str, bool, str]:
    head = command(["git", "-c", "safe.directory=*", "-C", str(directory), "rev-parse", "HEAD"])
    if head.returncode:
        return "", True, "checkout-unreadable"
    dirty = command(
        ["git", "-c", "safe.directory=*", "-C", str(directory), "status", "--porcelain"]
    )
    branches = command(
        [
            "git",
            "-c",
            "safe.directory=*",
            "-C",
            str(directory),
            "branch",
            "-r",
            "--contains",
            head.stdout.strip(),
        ]
    )
    is_dirty = dirty.returncode != 0 or bool(dirty.stdout.strip())
    on_origin = branches.returncode == 0 and any(
        line.strip().startswith("origin/") for line in branches.stdout.splitlines()
    )
    return (
        head.stdout.strip(),
        is_dirty,
        "head-on-origin-ref" if on_origin else "head-on-no-origin-ref",
    )


def directory_kb(directory: Path) -> int:
    """Return a conservative size; unreadable contents are not a reason to crash a pass."""
    try:
        return max(
            1, sum(path.stat().st_size for path in directory.rglob("*") if path.is_file()) // 1024
        )
    except OSError:
        return 1


def make_rows(
    *,
    root: Path,
    runs: Mapping[str, Mapping[str, object]],
    runs_readable: bool,
    config: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for directory in sorted(root.iterdir() if root.is_dir() else (), key=lambda path: path.name):
        if not directory.is_dir() or directory.is_symlink():
            continue
        match = _WORKSPACE_NAME.match(directory.name)
        run = runs.get(match["run"].upper()) if match else None
        item = work_item_id(run) if run else None
        ended = run_end(run) if run else None
        head, dirty, evidence = checkout_state(directory)
        if not runs_readable:
            cls = "run-end-unreadable"
        elif run is None:
            # A record-less sandbox is still a directory we must account for;
            # without its associated run/item mapping it cannot be proved safe.
            cls = "item-unmapped"
        elif ended is None:
            cls = "run-no-end-time"
        else:
            cls = item_class(item=item, ledger_command=string_value(config, "ledger_command"))
        action = "archive" if dirty or evidence != "head-on-origin-ref" else "delete"
        rows.append(
            {
                "manifest_version": 2,
                "dir": directory.name,
                "kb": directory_kb(directory),
                "cls": cls,
                "head": head,
                "dirty": dirty,
                "evidence": evidence,
                "item": item,
                "run_ended_at": ended,
                "action": action,
                "archive_record_command": string_value(config, "archive_record_command"),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = mapping(json.loads(Path(args.config).read_text(encoding="utf-8")))
    if config is None:
        raise ManifestConfigurationError.not_an_object()
    root, manifest = Path(string_value(config, "root")), Path(string_value(config, "manifest"))
    runs, readable = read_runs(config=config)
    rows = make_rows(root=root, runs=runs, runs_readable=readable, config=config)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=manifest.parent, delete=False
    ) as handle:
        json.dump(rows, handle, sort_keys=True)
        _ = handle.write("\n")
        temporary = Path(handle.name)
    _ = temporary.replace(manifest)
    _ = sys.stdout.write(
        json.dumps(
            {"event": "factory-workspace-manifest", "rows": len(rows), "runs_readable": readable},
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
