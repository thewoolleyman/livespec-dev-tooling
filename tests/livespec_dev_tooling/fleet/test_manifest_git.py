"""The fleet manifest read leaves the REST budget — `livespec-dev-tooling-7yeveq`.

WHAT WAS MEASURED, because the fix is only legible beside it. On
2026-09-06 master CI of this repository went red THREE times in one
afternoon on `check-fleet-conformance` alone, every time on the SAME
single read — the fleet manifest, fetched from `thewoolleyman/livespec`
through the REST contents API — with `gh: API rate limit exceeded for
installation ID 131208965` (HTTP 403). No code changed between a failing
attempt and a passing one.

TWO FACTS DECIDE THE SHAPE OF THE REMEDY, and both are measurements
rather than inferences:

1. The installation's PRIMARY core budget was 11,074/12,500 remaining at
   18:14:16Z and 12,401/12,500 at 18:21:15Z, yet the job was refused at
   18:16:02Z and 18:17:31Z. This fleet's whole nine-PR release fan-out
   costs ~81 reads on the tarball route `_snapshot` introduced (~5,877
   on the per-file route it replaced), so burning >11,000 requests in
   ~100 s is not reachable by its known traffic. GitHub was refusing on
   a SECONDARY limit rendered with the primary limit's message.
2. The job's own preflight (`.github/actions/github-rate-budget-token`,
   `min-core-remaining` 500) reported "rate budget healthy" 72 s before
   the refusal. A remaining-count floor CANNOT see a secondary limit by
   construction, so no threshold on that preflight is a fix.

⛔ WHY THE GATE IS NOT TAUGHT TO SHRUG. The tempting third option —
teach the master-green gates to treat a rate-limited conformance failure
as non-blocking — is REJECTED, and these tests pin the rejection: a gate
that passes because the check could not run is the vacuous-gate defect
this repository has already paid for three times (`z4qi`, `sh71`,
`x7ml`). `test_both_routes_refused_still_fails_loud_and_names_both_causes`
is that pin. What changes here is the ROUTE, not the verdict: the
manifest is read over the GIT transport, whose quota is not the REST
installation pool, and the contents API is kept only as a fallback for
when git cannot answer.

The manifest is singled out — rather than every read — because it is the
ROOT FACT. Losing it is a PRECONDITION failure (exit 1) that reds master
and stalls the factory through the Dispatcher's admission gate and every
sandbox's `check-master-ci-green`; losing any single member read is one
row's named skip. The remaining REST reads stay behind
`PacedGhRunner`'s bounded, `Retry-After`-honouring retry.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success
from returns.unsafe import unsafe_perform_io
from test_fleet_conformance import make_context, raw

from livespec_dev_tooling.fleet._context import FleetContext, GhOutcome, GhResult, GhRunner
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult, CommandRunner
from livespec_dev_tooling.fleet._manifest_git import (
    GIT_READ_OPERATION,
    GIT_READ_REFUSED,
    default_git_reader,
    git_file_text,
    manifest_text,
)
from livespec_dev_tooling.fleet.fleet_conformance import (
    MANIFEST_PATH,
    MANIFEST_REPO,
    fetch_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

__all__: list[str] = []


_MANIFEST_SOURCE = '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'
_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
# The VERBATIM refusal the fleet App installation answered with on 2026-09-06.
# Quoted rather than paraphrased because its wording is what
# `classify_gh_failure` keys on, and because the whole finding rests on this
# body arriving as an HTTP 403 that a permission denial also uses.
_RATE_LIMITED_STDERR = (
    "gh: API rate limit exceeded for installation ID 131208965. "
    "If you reach out to GitHub Support for help, please include the request ID "
    "8C30:2D9708:BB87665:C05B3F6:6A6FC1FC (HTTP 403)"
)


def _throttled_gh(*, asked: list[tuple[str, ...]]) -> GhRunner:
    """A `GhRunner` refusing every read with the measured throttle body."""

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        del stdin
        asked.append(tuple(args))
        return IOSuccess(GhResult(returncode=1, stdout="", stderr=_RATE_LIMITED_STDERR))

    return run


def _recorded_git(*, answers: list[CommandOutcome], calls: list[tuple[str, ...]]) -> CommandRunner:
    """A git seam replaying `answers` in order, recording every argv it is given."""

    def read(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        calls.append(tuple(args))
        return answers[min(len(calls) - 1, len(answers) - 1)]

    return read


def _ran(*, stdout: str = "", returncode: int = 0, stderr: str = "") -> CommandOutcome:
    """A git invocation that RAN, carrying its exit code as data."""
    return IOSuccess(CommandResult(returncode=returncode, stdout=stdout, stderr=stderr))


def _never_ran(*, kind: str = BINARY_ABSENT) -> CommandOutcome:
    """A git invocation that never happened at all."""
    return IOFailure(InvocationNotPerformed(argv=("git",), kind=kind, detail="no git"))


def test_a_rate_limited_contents_api_no_longer_costs_the_manifest() -> None:
    """THE MEASURED FAILURE, inverted: the 403 arrives and the manifest still resolves.

    The gh seam refuses every read with the verbatim 2026-09-06 body. Before
    this change that refusal WAS the run's verdict — exit 1, master red,
    factory stalled. The assertion is on the parsed manifest rather than on a
    green verdict, because "the call succeeded" is also what a silent-unwrap
    bug satisfies.
    """
    ctx = FleetContext(owner="acme", run_gh=_throttled_gh(asked=[]))
    read = _recorded_git(answers=[_ran(), _ran(stdout=_MANIFEST_SOURCE)], calls=[])

    fetched = fetch_manifest(ctx=ctx, read_git=read)

    assert isinstance(fetched, Success)
    assert fetched.unwrap().member_names() == frozenset({"widget"})


def test_the_git_route_is_asked_first_and_the_contents_api_is_never_reached() -> None:
    """A successful git read spends NO REST request — the point of the change.

    Falling back on success would leave the manifest on the rate-limited pool
    while looking fixed, so the absence of the contents call is asserted
    directly rather than inferred from the verdict.
    """
    asked: list[tuple[str, ...]] = []
    ctx = FleetContext(owner="acme", run_gh=_throttled_gh(asked=asked))
    read = _recorded_git(answers=[_ran(), _ran(stdout=_MANIFEST_SOURCE)], calls=[])

    text = manifest_text(ctx=ctx, read_git=read, repo=MANIFEST_REPO, path=MANIFEST_PATH)

    assert text == _MANIFEST_SOURCE
    assert asked == []
    assert ctx.read_failures == []


def test_the_git_read_pins_the_manifest_repo_and_path_at_the_remote_head() -> None:
    """The argv is the contract with git: a blobless shallow clone, then one blob.

    Pinned verbatim because each flag is load-bearing: `--filter=blob:none`
    plus `--no-checkout` is what keeps a whole-repo download from replacing a
    one-file read, and `HEAD:` is what resolves the default branch WITHOUT the
    `repos/{owner}/{repo}` REST call `canonical_ref` would otherwise spend on
    the very pool this read is leaving.
    """
    calls: list[tuple[str, ...]] = []
    read = _recorded_git(answers=[_ran(), _ran(stdout=_MANIFEST_SOURCE)], calls=calls)

    result = git_file_text(run=read, owner="acme", repo="livespec", path="a/manifest.jsonc")

    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()) == _MANIFEST_SOURCE
    clone, show = calls
    assert clone[0] == "git"
    assert "clone" in clone
    assert "--filter=blob:none" in clone
    assert "--no-checkout" in clone
    assert "https://github.com/acme/livespec.git" in clone
    assert show[-1] == "HEAD:a/manifest.jsonc"


def test_no_credential_value_is_ever_placed_in_the_git_argv() -> None:
    """Secrets reach git through a HELPER, never through the URL or the argv.

    The fleet's standing rule (`fleet/CLAUDE.md`): secret VALUES never appear
    in argv, logs, or outcomes. A `https://x-access-token:<token>@github.com/`
    URL is the obvious way to authenticate a clone and is exactly what that
    rule forbids, so the absence of any credential-shaped element is asserted
    rather than trusted.
    """
    calls: list[tuple[str, ...]] = []
    read = _recorded_git(answers=[_ran(), _ran(stdout=_MANIFEST_SOURCE)], calls=calls)

    _ = git_file_text(run=read, owner="acme", repo="livespec", path=MANIFEST_PATH)

    flattened = " ".join(argument for call in calls for argument in call)
    assert "@github.com" not in flattened
    assert "x-access-token" not in flattened
    assert "credential.helper" in flattened, "the helper is how the token stays out of argv"


def test_a_refused_git_read_falls_back_to_the_contents_api() -> None:
    """Git is the preferred route, not a required one — the fallback is intact.

    A host without git, a network that refuses the clone, or a repository the
    git transport cannot reach must not turn a readable manifest into a red
    master. That would trade one transient red for another.
    """
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})
    read = _recorded_git(answers=[_never_ran()], calls=[])

    fetched = fetch_manifest(ctx=ctx, read_git=read)

    assert isinstance(fetched, Success)
    assert fetched.unwrap().member_names() == frozenset({"widget"})


def test_a_recovered_read_records_no_cause() -> None:
    """A read that SUCCEEDED has no cause to report; saying otherwise erodes the field.

    `read_failure_cause` is what a reader of a GREEN run scans to decide
    whether anything degraded. Recording the git route's refusal on a run
    whose manifest was read anyway would make every git-less host report
    `other-read-failure` on a healthy run, which is how a diagnostic field
    becomes noise a reader learns to skip.

    Scoped to THIS route's operation rather than asserting an empty sink: the
    canned context answers no `repo_metadata` lookup, so `canonical_ref` records
    a cause of its own on the fallback path. That one is pre-existing and true;
    the claim under test is only that the git route adds none.
    """
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})
    refused = _ran(returncode=128, stderr="fatal: repository not found")
    read = _recorded_git(answers=[refused], calls=[])

    fetched = fetch_manifest(ctx=ctx, read_git=read)

    assert isinstance(fetched, Success), "the fallback answered, so the run is not degraded"
    assert GIT_READ_OPERATION not in {failure.operation for failure in ctx.read_failures}


def test_both_routes_refused_still_fails_loud_and_names_both_causes() -> None:
    """⛔ THE NON-VACUITY PIN. An unreadable manifest is STILL a precondition failure.

    This is the test that forecloses the rejected remedy. Nothing here makes
    the check pass when it could not read its root fact; the run fails exactly
    as it did before, and the only change is that the operator now sees WHICH
    route failed and how — the git refusal beside the throttled contents read,
    so a reader is not left to guess whether the new route is even wired.
    """
    ctx = FleetContext(owner="acme", run_gh=_throttled_gh(asked=[]))
    read = _recorded_git(answers=[_ran(returncode=128, stderr="fatal: could not read")], calls=[])

    fetched = fetch_manifest(ctx=ctx, read_git=read)

    assert isinstance(fetched, Failure)
    assert fetched.failure().reason == "unreadable"
    kinds = {failure.kind for failure in ctx.read_failures}
    assert GIT_READ_REFUSED in kinds, "the git route's own refusal must be reported"
    assert "rate_limited" in kinds, "the throttled contents read must still be reported"
    git_causes = [
        failure for failure in ctx.read_failures if failure.operation == GIT_READ_OPERATION
    ]
    assert [failure.path for failure in git_causes] == [f"{MANIFEST_REPO}:{MANIFEST_PATH}"]


def test_a_git_that_never_ran_is_reported_as_such_when_both_routes_fail() -> None:
    """ "git is absent" and "git ran and refused" are different operator problems.

    The seam's shared failure track already keeps them apart; this pins that
    the distinction survives the trip into `read_failures` instead of being
    flattened into one `git_unreadable`.
    """
    ctx = FleetContext(owner="acme", run_gh=_throttled_gh(asked=[]))
    read = _recorded_git(answers=[_never_ran(kind=BINARY_ABSENT)], calls=[])

    _ = fetch_manifest(ctx=ctx, read_git=read)

    assert BINARY_ABSENT in {failure.kind for failure in ctx.read_failures}


def test_a_clone_that_succeeds_but_a_blob_that_does_not_is_still_a_refusal() -> None:
    """The two-step read fails at EITHER step; neither may answer with empty bytes.

    A clone that lands and a `git show` that cannot produce the file is the
    shape that would otherwise return `""` — a manifest that parses to nothing
    and a fleet of zero members, which passes vacuously.
    """
    calls: list[tuple[str, ...]] = []
    answers = [_ran(), _ran(returncode=128, stderr="fatal: no such path")]
    read = _recorded_git(answers=answers, calls=calls)

    result = git_file_text(run=read, owner="acme", repo="livespec", path=MANIFEST_PATH)

    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).kind == GIT_READ_REFUSED
    assert len(calls) == 2, "the blob read must have been attempted"


def test_a_failed_clone_never_attempts_the_blob_read() -> None:
    """No second network call once the first has already said no."""
    calls: list[tuple[str, ...]] = []
    answers = [_ran(returncode=128, stderr="fatal: repository not found")]
    read = _recorded_git(answers=answers, calls=calls)

    result = git_file_text(run=read, owner="acme", repo="livespec", path=MANIFEST_PATH)

    assert isinstance(result, IOFailure)
    assert len(calls) == 1


def test_without_a_git_seam_the_read_is_the_contents_api_exactly_as_before() -> None:
    """The lanes that were never on the master-CI path keep the read they had.

    `fleet_conformance_admin` and `wire_fleet_member` are operator-invoked and
    call `fetch_manifest(ctx=ctx)` with no seam. The default is fail-safe: no
    construction site acquires a subprocess it did not ask for.
    """
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})

    text = manifest_text(ctx=ctx, read_git=None, repo=MANIFEST_REPO, path=MANIFEST_PATH)

    assert text == _MANIFEST_SOURCE


def test_the_default_reader_disables_terminal_credential_prompting(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that HANGS on a credential prompt is worse than the red it replaced.

    `just check` and the CI job both run this read. Git falls back to a
    terminal prompt when no helper answers, and a prompt inside a gate waits
    forever instead of failing — converting a bounded red into an unbounded
    stall. `GIT_TERMINAL_PROMPT=0` is the documented switch, and it has no
    config-file equivalent, which is why this seam exists beside
    `default_command_runner` rather than reusing it.
    """
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> object:
        del argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=["git"], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(subprocess, "run", fake_run)

    outcome = default_git_reader(args=["git", "--version"])

    assert dict(seen["env"])["GIT_TERMINAL_PROMPT"] == "0"
    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()).stdout == "ok"


def test_an_absent_git_is_a_failure_value_not_a_fabricated_exit_code(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing binary lands on the FAILURE track, carrying argv.

    `shutil.which` is patched rather than a shim directory prepended: a
    fixture a real `git` later on PATH can defeat is a fixture that cannot
    fail.
    """
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    outcome = default_git_reader(args=["git", "--version"])

    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert failure.kind == BINARY_ABSENT
    assert failure.argv == ("git", "--version")


def test_a_git_that_cannot_be_spawned_is_a_failure_value(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `OSError` at spawn must not propagate out of the seam and kill the run."""
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise PermissionError("Permission denied")

    monkeypatch.setattr(subprocess, "run", refuse)

    outcome = default_git_reader(args=["git", "--version"])

    assert isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.failure()).kind == SPAWN_FAILED


def test_the_reader_runs_in_the_requested_working_directory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`cwd` is honoured, so the seam satisfies the shared `CommandRunner` shape."""
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> object:
        del argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=["git"], returncode=3, stdout="", stderr="no")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(subprocess, "run", fake_run)

    outcome = default_git_reader(args=["git", "status"], cwd=tmp_path)

    assert seen["cwd"] == str(tmp_path)
    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()).returncode == 3
