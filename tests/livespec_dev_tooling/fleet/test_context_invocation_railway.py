"""The `gh` seam's failure track — `livespec-dev-tooling-8o8e` row 30.

The third and last of the three subprocess seams, and the one whose
sentinel travelled furthest. `default_gh_runner` answered "the invocation
never happened" with `GhResult(returncode=127, stderr="gh CLI not on
PATH")` — a success-shaped record indistinguishable from a real `gh` that
genuinely exited 127 — and `subprocess.run` raised straight through the
seam, killing the whole nine-member sweep partway through one member
rather than failing that member.

`_context.py` also had NO `_VENDOR_DIR` preamble. It reached `returns`
only because its line-28 import of `_snapshot` ran that module's preamble
first — the latent form of the bare import that broke the fleet's release
fan-out for seven hours. This conversion puts a real `returns` import in
the module, so the ordering dependency stops being latent; the preamble
lands in the same edit.

`test_a_gh_that_ran_...` pins the asymmetry the success track depends on:
a `gh` that RAN carries its exit code as DATA, whatever it is. GitHub
answers 404 and 422 as ordinary API outcomes and rows read them as such,
so reading every non-zero exit as a failure would break more than it
fixed.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._context import FleetContext, GhResult, default_gh_runner
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = []


def test_absent_gh_is_a_failure_value_not_a_fabricated_127(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing `gh` lands on the FAILURE track, carrying argv."""

    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    result = default_gh_runner(args=["api", "repos/acme/x"])
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert isinstance(failure, InvocationNotPerformed)
    assert failure.kind == BINARY_ABSENT
    assert failure.argv == ("gh", "api", "repos/acme/x")


def test_a_gh_that_ran_and_exited_nonzero_is_a_success_carrying_its_code(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub answering 404 is an ANSWER; the seam does not adjudicate it."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="404\n")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_gh_runner(args=["api", "repos/acme/x"])
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()) == GhResult(returncode=1, stdout="", stderr="404\n")


def test_an_unspawnable_gh_is_a_failure_value_rather_than_a_raise(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This raise used to kill the whole nine-member sweep partway through a member."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    def fake_run(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_gh_runner(args=["api", "repos/acme/x"])
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert failure.kind == SPAWN_FAILED
    assert "Permission denied" in failure.detail


def _never_ran(
    *, args: list[str], stdin: str | None = None
) -> IOResult[GhResult, InvocationNotPerformed]:
    """A `GhRunner` reporting every invocation as never performed."""
    del stdin
    return IOFailure(
        InvocationNotPerformed(argv=("gh", *args), kind=BINARY_ABSENT, detail="gh CLI not on PATH")
    )


def test_a_gh_that_never_ran_is_recorded_as_its_own_read_failure_kind() -> None:
    """`api_object` still answers None, and the CAUSE names the real one.

    Before this conversion the fabricated 127 flowed into
    `classify_gh_failure(stderr="gh CLI not on PATH")`, which reads a
    TRANSPORT diagnostic out of a string the seam invented — so the
    preserved cause described a `gh` that had spoken. The kind now says
    the invocation never happened.
    """
    ctx = FleetContext(owner="acme", run_gh=_never_ran)
    assert ctx.api_object(path="repos/acme/x") is None
    assert len(ctx.read_failures) == 1
    assert ctx.read_failures[0].kind == BINARY_ABSENT


def test_file_text_of_a_gh_that_never_ran_is_not_an_absent_file() -> None:
    """A file this run never managed to ask about is not a file that is absent."""
    ctx = FleetContext(owner="acme", run_gh=_never_ran)
    assert ctx.file_text(repo="x", path="README.md") is None
    kinds = [failure.kind for failure in ctx.read_failures]
    assert BINARY_ABSENT in kinds
