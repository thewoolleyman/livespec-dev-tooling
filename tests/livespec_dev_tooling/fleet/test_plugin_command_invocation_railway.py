"""The plugin command seam's failure track — `livespec-dev-tooling-6e83`.

`subprocess_runner` used to answer "the invocation never happened" with a
FABRICATED `PluginCommandResult(returncode=127)` — a success-shaped record
indistinguishable from a plugin command that genuinely exited 127. That is the
same sentinel `_local_context.default_command_runner` shed in
`livespec-dev-tooling-8o8e` row 33, left behind here because the two seams
shared their type NAMES rather than their type. Removing the name collision
closed the shadowing hazard; this closes the disagreement underneath it. BOTH
seams are runners over one operating-system fact — a child process either
started or it did not — so both answer with the ONE failure track
`_invocation_failure` exists to carry.

The success track is unchanged in meaning: a command that RAN carries its exit
code as DATA, whatever that code is. `test_a_plugin_command_that_ran_...` and
`test_run_from_settings_keeps_a_refusing_command_...` pin that asymmetry from
both ends, because collapsing it the other way — reading every non-zero exit
as a failure — is the tightening error this fleet has already committed once.

THE `ensure` TEST IS THE POINT OF THE CONVERSION, not decoration. The
fabricated 127 did not stay inside the seam: `_run_commands` read it as an
ANSWER and reported `command failed with exit 127`, which tells an operator
that `claude` ran and refused. It had not run at all — it was not installed —
and the two call for opposite operator responses.

The runner annotations here spell `IOResult[PluginCommandResult,
InvocationNotPerformed]` out rather than importing the seam's alias, matching
`test_local_command_invocation_railway`'s canned failing runner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet.ensure_plugins import (
    PluginCommandResult,
    ensure,
    run_from_settings,
    subprocess_runner,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []

_SETTINGS = json.dumps(
    {
        "extraKnownMarketplaces": {
            "alpha": {"source": {"source": "github", "repo": "acme/alpha", "ref": "release"}}
        },
        "enabledPlugins": {"one@alpha": True},
    }
)


def _never_ran(*, args: tuple[str, ...]) -> IOResult[PluginCommandResult, InvocationNotPerformed]:
    """A runner reporting EVERY invocation as never performed.

    Unconditional on purpose: both callers below stop at their FIRST command,
    so a fall-through to a canned success would be an arm no test can reach.
    """
    return IOFailure(
        InvocationNotPerformed(argv=args, kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH")
    )


def test_a_plugin_command_that_ran_is_a_success_carrying_its_exit_code() -> None:
    outcome = subprocess_runner(args=("false",))
    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()).returncode != 0


def test_an_absent_plugin_binary_is_a_failure_not_a_fabricated_127(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patching `which` rather than emptying PATH: a real binary must not defeat it."""
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    outcome = subprocess_runner(args=("claude", "plugin", "install", "one@alpha"))
    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert failure.kind == BINARY_ABSENT
    assert failure.argv == ("claude", "plugin", "install", "one@alpha")


def test_an_unspawnable_plugin_binary_is_a_failure(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Previously reported as the same fabricated 127: the OS refused to start it."""

    def fake_run(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    outcome = subprocess_runner(args=("claude", "plugin", "install", "one@alpha"))
    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert failure.kind == SPAWN_FAILED
    assert "Permission denied" in failure.detail


def test_ensure_reports_a_command_that_never_ran_rather_than_an_exit_code() -> None:
    findings = ensure(
        settings_text=_SETTINGS,
        project_root="/repo",
        runner=_never_ran,
        read_registry=lambda: None,
    )
    assert any(BINARY_ABSENT in finding and "claude" in finding for finding in findings)
    assert not any("exit 127" in finding for finding in findings)


def test_run_from_settings_puts_an_unperformed_invocation_on_the_failure_track(
    *, tmp_path: Path
) -> None:
    settings = tmp_path / "settings.json"
    _ = settings.write_text(_SETTINGS, encoding="utf-8")
    outcome = run_from_settings(settings_path=settings, runner=_never_ran)
    assert isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.failure()).kind == BINARY_ABSENT


def test_run_from_settings_keeps_a_refusing_command_on_the_success_track(*, tmp_path: Path) -> None:
    """A plugin command that RAN and exited non-zero is an answer, not a failure."""
    settings = tmp_path / "settings.json"
    _ = settings.write_text(_SETTINGS, encoding="utf-8")

    def refuses(*, args: tuple[str, ...]) -> IOResult[PluginCommandResult, InvocationNotPerformed]:
        del args
        return IOSuccess(PluginCommandResult(returncode=17))

    outcome = run_from_settings(settings_path=settings, runner=refuses)
    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()) == 17
