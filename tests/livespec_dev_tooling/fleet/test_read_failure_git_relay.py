"""Regression coverage for Git's relayed GitHub HTTP failures."""

from __future__ import annotations

from livespec_dev_tooling.fleet._read_failure import classify_gh_failure

__all__: list[str] = []


def test_every_relayed_http_5xx_is_a_server_error() -> None:
    """Git's URL error form preserves a retryable GitHub server response."""
    for stderr in (
        "gh: Bad Gateway (HTTP 502)",
        "HTTP 503: Service Unavailable",
        "fatal: unable to access https://github.com/example/repo: "
        "The requested URL returned error: 502",
    ):
        assert classify_gh_failure(stderr=stderr) == "server_error", stderr
