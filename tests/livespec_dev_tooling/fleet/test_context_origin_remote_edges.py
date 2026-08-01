"""Green-leg edges of the origin-remote resolvers and the CLI precondition.

A sibling rather than more cases in `test_context.py` because that file is the
Red-recorded one for this pair and is CHECKSUM-BOUND across the Red→Green
amend — appending to it would break byte-identity and force a fresh Red. The
naming follows the existing `test_context_invocation_railway_edges.py`
precedent.

`merged_branch_sweep.main()` is `# pragma: no cover`, so `stderr_reported_owner`
has no caller a test reaches; it is exercised DIRECTLY here. An extracted helper
whose only production caller is un-covered is exactly where a stderr lane
silently stops emitting.

Both taps are asserted to RETURN THE CONTAINER, not a collapsed `str | None`.
The first draft of that module returned the sentinel and the armed offender
count caught it — three offenders manufactured by an extraction meant to help.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet import _origin_remote
from livespec_dev_tooling.fleet._cli_owner import reported_owner, stderr_reported_owner
from livespec_dev_tooling.fleet._context import OriginRemoteUnresolved, owner_or_origin

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


class _Recorder:
    """A structlog-shaped sink carrying ONLY the method the subject calls.

    `check-per-file-coverage` counts TEST files at the same 100% bar, so a fake
    with `warning`/`info` methods nothing invokes is dead lines — and a fake
    richer than the contract also hides which method the subject actually uses.
    """

    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **fields: object) -> None:
        self.errors.append((event, fields))


def _git_absent(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    raise FileNotFoundError(2, "No such file or directory: 'git'")


def test_owner_or_origin_consults_the_remote_only_when_no_owner_was_given(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both directions of the precedence rule, proved by ONE instrument.

    `--owner ""` names no owner, so truthiness rather than `is not None` is the
    right test — that is the behavior the four copies this helper replaced had,
    and preserving it is why the helper tests it that way.

    ⛔ ONE recording resolver serves both halves DELIBERATELY. Asserting the
    short-circuit with a fake that raises if called leaves that fake's body
    unexecuted, which `check-per-file-coverage` counts as dead lines in the test
    file — the same "a fake carrying what the subject never calls" trap this
    repo has paid for twice. A call log states it positively and the same fake
    is genuinely invoked by the fall-through half.
    """
    calls: list[object] = []

    def recording(*, cwd: object = None) -> object:
        calls.append(cwd)
        return IOFailure(OriginRemoteUnresolved(reason="git-not-run", detail="probe"))

    monkeypatch.setattr(_origin_remote, "resolve_owner", recording)

    assert unsafe_perform_io(owner_or_origin(argument="acme").unwrap()) == "acme"
    assert not calls, "an explicit --owner must not consult the remote at all"

    for argument in (None, ""):
        resolved = owner_or_origin(argument=argument)
        assert isinstance(resolved, IOFailure)
        assert unsafe_perform_io(resolved.failure()).reason == "git-not-run"
    assert calls == [None, None], "both falsy spellings must fall through to the remote"


def test_resolved_owner_reports_which_read_failed_then_returns_none(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structlog lane's precondition: `None` means ALREADY REPORTED, not unknown.

    The discrimination the conversion bought is consumed HERE, at the log line —
    the only place it was ever needed — so collapsing to `None` afterwards loses
    nothing. What must not regress is the log carrying `reason`: without it this
    is the old sentinel with extra steps.
    """
    monkeypatch.setattr(subprocess, "run", _git_absent)
    log = _Recorder()

    resolved = reported_owner(argument=None, log=log)  # pyright: ignore[reportArgumentType]

    assert isinstance(resolved, IOFailure)
    assert [fields["reason"] for _event, fields in log.errors] == ["git-not-run"]


def test_resolved_owner_returns_the_argument_without_logging(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _git_absent)
    log = _Recorder()

    resolved = reported_owner(argument="acme", log=log)  # pyright: ignore[reportArgumentType]

    assert unsafe_perform_io(resolved.unwrap()) == "acme"
    assert log.errors == []


def test_owner_or_stderr_names_the_cause_on_stderr_and_returns_none(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plain-stderr lane must name the cause too, not just fail.

    `merged_branch_sweep` writes stderr rather than structlog JSON by design, so
    it renders the SAME failure through a different sink. Before this unit its
    message was "owner unresolvable: pass --owner or run inside a github.com
    clone" for all three causes — including the one where `git` never ran, which
    that advice does not address.
    """
    monkeypatch.setattr(subprocess, "run", _git_absent)

    assert isinstance(stderr_reported_owner(argument=None), IOFailure)

    assert "git-not-run" in capsys.readouterr().err


def test_owner_or_stderr_returns_the_resolved_owner_silently(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def github_remote(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="git@github.com:acme/widget.git\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", github_remote)

    assert unsafe_perform_io(stderr_reported_owner(argument=None).unwrap()) == "acme"

    assert capsys.readouterr().err == ""
