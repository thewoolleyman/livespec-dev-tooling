"""Tests for GitHub read-failure cause preservation through `FleetContext`.

`default_gh_runner` captures `returncode`, `stdout` and `stderr`, but
`api_object()` and `file_text()` discarded all of it and returned `None`.
Every downstream consumer could therefore report only "unavailable", making
403 / 404 / 429 / 5xx / transport / malformed-payload indistinguishable — and
a malformed manifest indistinguishable from a failure to fetch one.

That collapse is not cosmetic. `livespec-dev-tooling-z4qi` is a red master
caused by ONE transient credential rejection surfacing as NINE blind
obligation rows, and it cannot be fixed intelligently until a retry policy
can tell a retryable rejection from a non-retryable 404. This module pins the
cause surviving the call.

Scope note, deliberately narrow per the item: causes are RECORDED, nothing
retries and no severity changes. Return values are untouched, so fail-closed
and "can't-read is not absent" semantics are bit-identical.
"""

from __future__ import annotations

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    GhResult,
    GhRunner,
)

__all__: list[str] = []


def _always(*, result: GhResult) -> GhRunner:
    """A `GhRunner` returning the same canned result for every call."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:  # noqa: ARG001
        return result

    return lift_gh(run)


def _ctx(*, result: GhResult) -> FleetContext:
    return FleetContext(owner="thewoolleyman", run_gh=_always(result=result))


def test_forbidden_read_is_recorded_with_its_cause() -> None:
    """A 403 is recorded as `forbidden`, not collapsed to "unavailable"."""
    ctx = _ctx(
        result=GhResult(returncode=1, stdout="", stderr="gh: Resource not accessible (HTTP 403)")
    )

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    assert len(ctx.read_failures) == 1
    failure = ctx.read_failures[0]
    assert failure.kind == "forbidden", f"got {failure.kind!r}"
    assert failure.returncode == 1
    assert "repos/thewoolleyman/livespec" in failure.path


def test_not_found_is_distinguishable_from_forbidden() -> None:
    """404 carries real information — the thing is absent — and 403 does not."""
    ctx = _ctx(result=GhResult(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)"))

    assert ctx.api_object(path="repos/thewoolleyman/nope") is None
    assert ctx.read_failures[0].kind == "not_found"


def test_rate_limited_is_its_own_kind() -> None:
    """429 is retryable in a way 403 and 404 are not."""
    ctx = _ctx(
        result=GhResult(returncode=1, stdout="", stderr="gh: API rate limit exceeded (HTTP 429)")
    )

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    assert ctx.read_failures[0].kind == "rate_limited"


def test_server_error_is_its_own_kind() -> None:
    """A 5xx is the server's fault and is the other retryable class."""
    ctx = _ctx(result=GhResult(returncode=1, stdout="", stderr="gh: Bad gateway (HTTP 502)"))

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    assert ctx.read_failures[0].kind == "server_error"


def test_transport_failure_is_distinguishable_from_an_http_status() -> None:
    """`gh` absent or the network down is neither an HTTP status nor a 404."""
    ctx = _ctx(result=GhResult(returncode=127, stdout="", stderr="gh CLI not on PATH"))

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    assert ctx.read_failures[0].kind == "transport"


def test_malformed_payload_is_distinguishable_from_a_failed_fetch() -> None:
    """A 200 carrying non-JSON is a DIFFERENT failure from never reaching the API."""
    ctx = _ctx(result=GhResult(returncode=0, stdout="{not json", stderr=""))

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    assert ctx.read_failures[0].kind == "malformed_payload"


def test_contents_read_records_the_contents_operation() -> None:
    """A file read and a metadata read are different operations, and say so."""
    ctx = _ctx(result=GhResult(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)"))

    assert ctx.file_text(repo="livespec", path="AGENTS.md") is None
    operations = {failure.operation for failure in ctx.read_failures}
    assert "contents" in operations, f"got {operations!r}"


def test_repository_metadata_read_records_its_own_operation() -> None:
    """`canonical_ref` reads repo metadata; that is a third distinguishable operation."""
    ctx = _ctx(result=GhResult(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)"))

    _ = ctx.canonical_ref(repo="livespec")
    operations = {failure.operation for failure in ctx.read_failures}
    assert "repo_metadata" in operations, f"got {operations!r}"


def test_a_token_in_stderr_is_redacted() -> None:
    """Diagnostics must never carry a credential, however the API leaks it.

    The whole point of preserving stderr is that it reaches logs and CI
    output, so redaction is a correctness requirement of this change rather
    than a nicety.
    """
    ctx = _ctx(
        result=GhResult(
            returncode=1,
            stdout="",
            stderr="gh: bad credentials for ghs_AbCdEf0123456789AbCdEf0123456789 (HTTP 401)",
        )
    )

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is None
    detail = ctx.read_failures[0].detail
    assert "ghs_AbCdEf0123456789AbCdEf0123456789" not in detail, f"token leaked: {detail!r}"
    assert "REDACTED" in detail, f"redaction should be visible, not silent: {detail!r}"


def test_a_successful_read_records_nothing() -> None:
    """The happy path is unchanged and leaves no diagnostic residue."""
    ctx = _ctx(result=GhResult(returncode=0, stdout='{"default_branch": "master"}', stderr=""))

    assert ctx.api_object(path="repos/thewoolleyman/livespec") is not None
    assert ctx.read_failures == []
