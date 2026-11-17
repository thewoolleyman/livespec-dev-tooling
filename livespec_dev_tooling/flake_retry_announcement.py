"""Persist and announce the flake-retry plugin's evidence at the end of a session.

Split from `flake_retry.py` to keep that file under the LLOC ceiling. Everything
here takes the session's results as an argument: the plugin's module-level state
stays in `flake_retry.py`, where its tests replace it.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from livespec_dev_tooling.flake_retry_records import records_json
from livespec_dev_tooling.flake_retry_records import summary as records_summary

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from _pytest.terminal import TerminalReporter

    from livespec_dev_tooling.flake_retry_records import RetryResult

__all__: list[str] = [
    "announce",
    "retry_summary",
    "write_retry_records",
]


def write_retry_records(*, repo_root: Path, results: Iterable[RetryResult]) -> Path:
    """Write one JSON line for each retried node id beneath the repository tmp tree."""
    output = repo_root / "tmp" / "flake-retries" / "retries.jsonl"
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(
        records_json(results=results),
        encoding="utf-8",
    )
    return output


def retry_summary(*, results: Iterable[RetryResult]) -> str:
    """Render the loud terminal block required for every retry decision."""
    return records_summary(results=results)


def announce(
    *,
    terminalreporter: TerminalReporter,
    root: Path,
    results: list[RetryResult],
    withheld: str | None = None,
    withheld_by_nodeid: dict[str, str] | None = None,
) -> None:
    """Persist and announce retry evidence without changing pytest's final verdict."""
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    if withheld is not None:
        _ = terminalreporter.write_sep("=", "FLAKE-RETRY-WITHHELD")
        _ = terminalreporter.write_line(f"no failing test is retried this session: {withheld}")
        if annotate:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRY-WITHHELD {withheld}")
    if withheld_by_nodeid:
        _ = terminalreporter.write_sep("=", "FLAKE-RETRY-WITHHELD")
        for nodeid, reason in sorted(withheld_by_nodeid.items()):
            _ = terminalreporter.write_line(f"{nodeid}: {reason}")
            if annotate:
                _ = terminalreporter.write_line(
                    f"::warning::FLAKE-RETRY-WITHHELD {nodeid}: {reason}"
                )
    if not results:
        return
    _ = write_retry_records(repo_root=root, results=results)
    _ = terminalreporter.write_sep("=", "FLAKE-RETRIED")
    for line in retry_summary(results=results).splitlines()[1:]:
        _ = terminalreporter.write_line(line)
    if annotate:
        for result in results:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRIED {result.nodeid}")
