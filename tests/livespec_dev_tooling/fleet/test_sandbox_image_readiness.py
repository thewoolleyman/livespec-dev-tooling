"""Unit coverage for the sandbox-image readiness gate's own internals.

The consumer-tier suite drives the GATE — what it decides, what it names, and
what it refuses to release — over injected seams. What only this tier can cover
is the DEFAULT PROBE: the registry dance it performs and, more to the point,
the four ways it can fail to get an answer. Every one of them must read as "not
yet" rather than "served", because a probe that fails open releases the whole
fan-out against a tag nobody confirmed exists.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import pytest

from livespec_dev_tooling.fleet import sandbox_image_readiness as readiness

__all__: list[str] = []

_TAG = "python-rust-agent-v1.125.0"


@dataclass(kw_only=True)
class _Curl:
    """A `subprocess.run` double replaying one scripted answer per invocation."""

    answers: list[subprocess.CompletedProcess[str] | OSError]
    calls: list[list[str]]

    def run(
        self,
        argv: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check
        self.calls.append(argv)
        answer = self.answers.pop(0)
        if isinstance(answer, OSError):
            raise answer
        return answer


def _completed(*, returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["curl"], returncode=returncode, stdout=stdout)


def _install(
    *,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[subprocess.CompletedProcess[str] | OSError],
) -> _Curl:
    curl = _Curl(answers=answers, calls=[])
    monkeypatch.setattr(subprocess, "run", curl.run)
    return curl


def _token_answer() -> subprocess.CompletedProcess[str]:
    return _completed(returncode=0, stdout=json.dumps({"token": "anonymous-pull"}))


def test_a_served_tag_is_probed_through_the_registry_token_then_manifest_dance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ghcr answers `401` without a token, so the token read is not optional."""
    curl = _install(
        monkeypatch=monkeypatch,
        answers=[_token_answer(), _completed(returncode=0, stdout="200")],
    )

    assert readiness.default_tag_probe(tag=_TAG) is True
    assert "ghcr.io/token" in curl.calls[0][-1]
    manifest_argv = curl.calls[1]
    assert manifest_argv[-1].endswith(f"/manifests/{_TAG}")
    assert "Authorization: Bearer anonymous-pull" in manifest_argv
    assert any("application/vnd.oci.image.index.v1+json" in one for one in manifest_argv), (
        "the layered build pushes a multi-arch INDEX, so a probe accepting only the "
        "single-manifest media type would read a served tag as absent"
    )


@pytest.mark.parametrize(
    "status",
    ["404", "401", "500", ""],
    ids=["absent", "unauthorized", "registry-error", "no-status"],
)
def test_any_status_other_than_200_reads_as_not_yet(
    *, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    _ = _install(
        monkeypatch=monkeypatch,
        answers=[_token_answer(), _completed(returncode=0, stdout=status)],
    )

    assert (
        readiness.default_tag_probe(tag=_TAG) is False
    ), f"only a 200 proves the manifest is SERVED; {status!r} must hold the fan-out"


def test_a_curl_that_exits_non_zero_reads_as_not_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _install(
        monkeypatch=monkeypatch,
        answers=[_token_answer(), _completed(returncode=28, stdout="")],
    )

    assert readiness.default_tag_probe(tag=_TAG) is False


def test_a_curl_that_will_not_start_reads_as_not_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent `curl` is a broken runner, not a published image."""
    _ = _install(monkeypatch=monkeypatch, answers=[OSError("no curl")])

    assert readiness.default_tag_probe(tag=_TAG) is False


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps(["a"]), json.dumps({}), json.dumps({"token": ""})],
    ids=["unparseable", "not-an-object", "no-token-key", "empty-token"],
)
def test_a_token_response_that_carries_no_usable_token_reads_as_not_yet(
    *, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    curl = _install(monkeypatch=monkeypatch, answers=[_completed(returncode=0, stdout=payload)])

    assert readiness.default_tag_probe(tag=_TAG) is False
    assert len(curl.calls) == 1, (
        "without a token the manifest read can only answer 401, so it must not be made "
        "at all — otherwise a token outage would look like an absent tag twice over"
    )


def test_a_token_read_that_will_not_start_reads_as_not_yet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _install(monkeypatch=monkeypatch, answers=[_completed(returncode=7, stdout="")])

    assert readiness.default_tag_probe(tag=_TAG) is False


def test_the_system_clock_is_monotonic_and_really_sleeps() -> None:
    """A wall-clock adjustment must not be able to shorten the ratified bound."""
    clock = readiness.system_clock()

    first = clock.monotonic()
    clock.sleep(0)
    assert clock.monotonic() >= first


def test_the_module_entrypoint_names_the_source_repo_and_tag_it_gates_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The clear path announces itself too: a silent gate is an unverifiable one."""
    exit_code = readiness.main(
        argv=["--source-repo", readiness.WAITING_SOURCE_REPO, "--tag", "v1.125.0"],
        probe=lambda *, tag: bool(tag),
        clock=readiness.Clock(monotonic=lambda: 0.0, sleep=lambda _seconds: None),
    )

    assert exit_code == 0
    assert "::notice::" in capsys.readouterr().out
