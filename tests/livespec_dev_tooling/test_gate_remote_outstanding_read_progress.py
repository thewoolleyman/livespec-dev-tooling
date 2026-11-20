"""Progress reporting while a delegated gate cluster read is outstanding."""

from __future__ import annotations

from livespec_dev_tooling.gate_remote_wait_commands import terminal_watch_argv

__all__: list[str] = []


def test_an_outstanding_terminal_watch_reports_the_job_name_to_the_operator() -> None:
    """A quiet watch must still leave a once-a-minute, Job-specific progress line."""
    argv = terminal_watch_argv(
        namespace="gates",
        job_name="gate-widget-7f2qd",
        remaining_seconds=999.0,
    )

    assert ':: gate: "$job_name" not finished yet' in argv[3]
