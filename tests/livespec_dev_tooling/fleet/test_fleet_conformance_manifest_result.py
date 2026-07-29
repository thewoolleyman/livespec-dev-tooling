"""`fetch_manifest` puts its TWO failures on the railway as distinct values.

`fleet_conformance.fetch_manifest` was one of the three genuine
Result-return violations livespec-dev-tooling-9sl0 triaged, and the reason
it is convicted is worth stating precisely because a plausible wrong reason
convicts a function that must NOT be converted. Its network reach is
through an INJECTED seam (`ctx.file_text`), so livespec v179 member 1
clause (c) is NOT what disqualifies it — a clause-(c) reading would also
convict `holds_app_class_credential`, whose environment read cannot fail.
Clause (e) disqualifies an `X | None` return outright, and the failure
track here is genuinely INHABITED: by TWO distinct failures collapsed into
one sentinel.

Those two are "could not fetch it" and "fetched it and it does not parse".
Before the conversion they were the same `None`, distinguished only by a
SIDE EFFECT (`ctx.record_read_failure(kind="malformed_content")`) that a
caller had to go looking for. The module's own comment says making them
distinguishable was the point; this file pins that they now differ as
VALUES.

The success leg asserts the manifest reaches the caller rather than merely
that the call succeeded — asserting the call succeeded is exactly what a
silent-unwrap bug also satisfies.
"""

from __future__ import annotations

from returns.result import Failure, Success
from test_fleet_conformance import make_context, raw

from livespec_dev_tooling.fleet.fleet_conformance import fetch_manifest

__all__: list[str] = []


_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_MANIFEST_SOURCE = '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'


def test_a_fetched_manifest_unwraps_to_the_manifest_itself() -> None:
    """`Success` carries the parsed manifest, not merely a green verdict."""
    result = fetch_manifest(ctx=make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)}))

    assert isinstance(result, Success) and result.unwrap().member_names() == frozenset({"widget"})


def test_unreadable_and_unparseable_are_different_failure_values() -> None:
    """The two inhabitants of the failure track are told apart by the VALUE.

    An empty canned table means the fetch itself does not answer; a table
    that answers with non-JSONC means it answered and the bytes are no
    manifest. Both used to be `None`. Asserting only that each is a
    `Failure` would pass against a conversion that kept them collapsed, so
    the reasons are compared to each other as well as to their expected
    values.
    """
    unreadable = fetch_manifest(ctx=make_context(table={}))
    unparseable = fetch_manifest(
        ctx=make_context(table={_MANIFEST_ARGS: raw(text="not jsonc {{{")})
    )

    assert (
        isinstance(unreadable, Failure)
        and isinstance(unparseable, Failure)
        and unreadable.failure().reason == "unreadable"
        and unparseable.failure().reason == "unparseable"
    )
