"""Green-leg edges for the detailed commit-refuse body-mismatch digest."""

from __future__ import annotations

from livespec_dev_tooling.check_failure_digest import _body_mismatch_digest_fields

__all__: list[str] = []


def test_detailed_body_mismatch_digest_requires_an_object_and_all_three_text_fields() -> None:
    """Malformed or incomplete records stay on the ordinary digest path."""
    assert _body_mismatch_digest_fields(line="[]") is None
    assert (
        _body_mismatch_digest_fields(
            line=(
                '{"status": "fail", "failure_mode": "body_mismatch", '
                '"path": "/hooks/pre-push", "installed_sha256": "a"}'
            )
        )
        is None
    )
