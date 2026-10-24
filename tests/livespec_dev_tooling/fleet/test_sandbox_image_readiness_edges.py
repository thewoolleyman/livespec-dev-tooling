"""The sandbox-image readiness probe's remaining registry-answer shapes.

A sibling of `test_sandbox_image_readiness.py` on the
`test_dispatch_matrix_filter_edges.py` precedent: the primary suite pins the
contract (the six layered tags, the bounded wait, the annotation naming each
missing tag), and this one covers the answer shapes a registry can give that
are neither a usable token nor a refusal.

Every one of them resolves the same way — no token, so NO tag counts as served
— and the sameness is the point rather than a redundancy: a reading that
answered nothing must never be read as "the image is there", because that is the
one mistake that dispatches bumps onto a tag ghcr.io will 404.
"""

from __future__ import annotations

import json

from livespec_dev_tooling.fleet.sandbox_image_readiness import (
    FABRO_SANDBOX_IMAGE,
    ghcr_missing_tags,
)

__all__: list[str] = []


_TAGS = ("base-v1.125.0", "python-v1.125.0")


def test_a_pull_token_body_that_is_not_an_object_reports_every_tag_as_unserved() -> None:
    # ghcr.io answering 200 with a JSON ARRAY — a shape that parses cleanly and
    # carries no token. Distinct from the unparseable case the primary suite
    # covers: here `json.loads` succeeds, so a reader that only guarded the
    # decode would reach `.get` on a list and die inside the poll loop instead
    # of treating the answer as "not served yet".
    def arrayed(argv: tuple[str, ...], /) -> tuple[int, str]:
        del argv
        return 0, json.dumps(["not", "an", "object"])

    assert ghcr_missing_tags(image=FABRO_SANDBOX_IMAGE, tags=_TAGS, run=arrayed) == _TAGS


def test_an_empty_pull_token_reports_every_tag_as_unserved() -> None:
    # A token field present and EMPTY. An emptiness check beside the type check
    # because `Authorization: Bearer ` is a header the registry rejects for
    # every tag, which would read as a published image that nobody serves.
    def blank(argv: tuple[str, ...], /) -> tuple[int, str]:
        del argv
        return 0, json.dumps({"token": ""})

    assert ghcr_missing_tags(image=FABRO_SANDBOX_IMAGE, tags=_TAGS, run=blank) == _TAGS
