"""The release fan-out waits for the sandbox image before it dispatches.

`SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", subsection "`reusable-release-dispatch.yml`" (v087): when
`source_repo` is livespec-dev-tooling, the fan-out MUST NOT fire any
`sibling-released` dispatch until ghcr.io serves a manifest for each of the
release's six semver-tagged livespec-fabro-sandbox layers; it MUST poll for at
most 90 minutes; and when any is still absent at that bound the run MUST fail
with an annotation naming each missing tag and dispatch to no sibling. A release
of any other `source_repo` MUST NOT wait.

WHY A BUMP TO AN UNSERVED TAG IS WORSE THAN A LATE BUMP, measured 2026-10-22:
v1.125.0 published at 10:38:18Z, consumer bump PRs opened at 10:43Z, and
`python-rust-agent-v1.125.0` was not served until 11:19Z. Console PR #1266's
`check-arch` took a 404 for that tag and needed a rerun; orchestrator PR #3507
MERGED at 10:52:20Z, putting a sandbox tag on that repo's master that ghcr did
not serve for another 27 minutes, so any factory dispatch in the window would
have pulled a missing image. The bump "succeeded" in both cases — which is why
the wait has to happen BEFORE the dispatch rather than being caught after it.

Every effect here is an INJECTED SEAM — the registry probe, the sleep and the
clock — so these tests reach no network and spend no wall time proving a
90-minute bound.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import cast

import pytest
from returns.result import Failure, Success

__all__: list[str] = []


_DEV_TOOLING = "livespec-dev-tooling"
_TAG = "v1.125.0"
_LAYERS = (
    "base",
    "python",
    "python-agent",
    "python-rust",
    "python-rust-agent",
    "python-rust-fuzz",
)


def _module() -> object:
    """The readiness module, asserted present before it is imported.

    Asserted rather than imported at module scope: a top-level import of a
    module that does not exist yet dies at COLLECTION, which proves only
    unimportability. This fails on a genuine assertion instead.
    """
    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "sandbox_image_readiness.py"
    )
    assert module_path.is_file(), f"the sandbox-image readiness module is absent: {module_path}"
    return importlib.import_module("livespec_dev_tooling.fleet.sandbox_image_readiness")


class _Clock:
    """A monotonic clock the test advances, so the 90-minute bound costs nothing."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class _Probe:
    """A registry probe answering a scripted sequence of missing-tag sets."""

    def __init__(self, *, answers: list[tuple[str, ...]]) -> None:
        self.answers = answers
        self.calls = 0

    def __call__(self, *, image: str, tags: tuple[str, ...]) -> tuple[str, ...]:
        del image, tags
        self.calls += 1
        index = min(self.calls - 1, len(self.answers) - 1)
        return self.answers[index]


def _expected_tags(*, version: str) -> tuple[str, ...]:
    return tuple(f"{layer}-v{version}" for layer in _LAYERS)


def test_the_six_layered_tags_are_named_for_the_release() -> None:
    module = _module()
    tags = cast("tuple[str, ...]", module.sandbox_image_tags(tag=_TAG))
    assert tags == _expected_tags(version="1.125.0")


def test_a_bare_version_names_the_same_six_tags() -> None:
    # The fan-out is handed the release TAG, and a release tag may or may not
    # carry the `v`. Both must name the tags the image build actually pushes
    # (`<layer>-v<X.Y.Z>`); `base-vv1.125.0` names nothing that will ever exist.
    module = _module()
    assert module.sandbox_image_tags(tag="1.125.0") == _expected_tags(version="1.125.0")


def test_the_wait_returns_at_once_when_every_tag_is_already_served() -> None:
    module = _module()
    clock = _Clock()
    probe = _Probe(answers=[()])
    slept: list[float] = []

    result = module.await_sandbox_tags(
        tag=_TAG, probe=probe, sleep=slept.append, now=clock, bound_seconds=5400.0
    )

    assert isinstance(result, Success), result
    assert result.unwrap() == _expected_tags(version="1.125.0")
    assert probe.calls == 1
    assert slept == [], "a served image must cost the fan-out no delay at all"


def test_the_wait_polls_until_the_last_tag_appears() -> None:
    module = _module()
    clock = _Clock()
    probe = _Probe(answers=[("python-rust-agent-v1.125.0",), ()])

    def sleep(seconds: float, /) -> None:
        clock.advance(seconds)

    result = module.await_sandbox_tags(
        tag=_TAG, probe=probe, sleep=sleep, now=clock, bound_seconds=5400.0
    )

    assert isinstance(result, Success), result
    assert probe.calls == 2
    assert clock.seconds > 0, "the second probe must come after a real wait"


def test_the_wait_fails_at_the_bound_naming_every_missing_tag() -> None:
    module = _module()
    clock = _Clock()
    missing = ("python-rust-agent-v1.125.0", "python-rust-fuzz-v1.125.0")
    probe = _Probe(answers=[missing])

    def sleep(seconds: float, /) -> None:
        clock.advance(seconds)

    result = module.await_sandbox_tags(
        tag=_TAG, probe=probe, sleep=sleep, now=clock, bound_seconds=5400.0
    )

    assert isinstance(result, Failure), result
    unserved = result.failure()
    assert cast("tuple[str, ...]", unserved.missing) == missing
    assert clock.seconds >= 5400.0, "the bound must be honoured, not merely declared"


def test_the_ratified_bound_is_ninety_minutes() -> None:
    module = _module()
    assert module.POLL_BOUND_SECONDS == 90 * 60


def test_main_dispatches_without_waiting_for_a_release_of_another_source_repo() -> None:
    module = _module()
    probe = _Probe(answers=[("base-v1.125.0",)])

    exit_code = module.main(argv=["--source-repo", "livespec-runtime", "--tag", _TAG], probe=probe)

    assert exit_code == 0
    assert probe.calls == 0, "only a dev-tooling release has sandbox tags to wait for"


def test_main_exits_zero_once_the_dev_tooling_release_image_is_served(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    probe = _Probe(answers=[()])

    exit_code = module.main(argv=["--source-repo", _DEV_TOOLING, "--tag", _TAG], probe=probe)

    assert exit_code == 0
    assert "::error::" not in capsys.readouterr().out


def test_main_fails_with_an_annotation_naming_each_missing_tag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    clock = _Clock()
    probe = _Probe(answers=[("python-rust-fuzz-v1.125.0",)])

    def sleep(seconds: float, /) -> None:
        clock.advance(seconds)

    exit_code = module.main(
        argv=["--source-repo", _DEV_TOOLING, "--tag", _TAG],
        probe=probe,
        sleep=sleep,
        now=clock,
    )

    assert exit_code == 1, "an unserved image must dispatch to no sibling"
    annotation = capsys.readouterr().out
    assert "::error::" in annotation
    assert "python-rust-fuzz-v1.125.0" in annotation


def test_the_registry_probe_reports_only_the_unserved_tags() -> None:
    module = _module()
    seen: list[tuple[str, ...]] = []

    def run(argv: tuple[str, ...], /) -> tuple[int, str]:
        seen.append(argv)
        if any("/token" in word for word in argv):
            return 0, json.dumps({"token": "anon"})
        return (0, "") if any(word.endswith("base-v1.125.0") for word in argv) else (22, "")

    missing = cast(
        "tuple[str, ...]",
        module.ghcr_missing_tags(
            image=module.FABRO_SANDBOX_IMAGE,
            tags=("base-v1.125.0", "python-v1.125.0"),
            run=run,
        ),
    )

    assert missing == ("python-v1.125.0",)
    # The anonymous pull token is fetched once and reused for every tag, so a
    # six-layer probe costs the registry one token call rather than six.
    assert len([argv for argv in seen if any("/token" in word for word in argv)]) == 1
    assert any("Bearer anon" in word for argv in seen for word in argv)


def test_an_unanswerable_pull_token_reports_every_tag_as_unserved() -> None:
    # A can't-READ of the registry is NOT evidence the image is there: the only
    # fail-closed reading is "not served yet", which keeps the fan-out waiting
    # and, at the bound, fails naming the tags rather than dispatching bumps to
    # a tag nobody has seen.
    module = _module()

    def refuse(argv: tuple[str, ...], /) -> tuple[int, str]:
        del argv
        return 7, ""

    tags = ("base-v1.125.0", "python-v1.125.0")
    assert module.ghcr_missing_tags(image=module.FABRO_SANDBOX_IMAGE, tags=tags, run=refuse) == tags


def test_a_pull_token_response_without_a_token_reports_every_tag_as_unserved() -> None:
    module = _module()

    def tokenless(argv: tuple[str, ...], /) -> tuple[int, str]:
        del argv
        return 0, json.dumps({"errors": ["nope"]})

    tags = ("base-v1.125.0",)
    assert (
        module.ghcr_missing_tags(image=module.FABRO_SANDBOX_IMAGE, tags=tags, run=tokenless) == tags
    )


def test_an_unparseable_pull_token_response_reports_every_tag_as_unserved() -> None:
    module = _module()

    def garbage(argv: tuple[str, ...], /) -> tuple[int, str]:
        del argv
        return 0, "<html>502</html>"

    tags = ("base-v1.125.0",)
    assert (
        module.ghcr_missing_tags(image=module.FABRO_SANDBOX_IMAGE, tags=tags, run=garbage) == tags
    )


def test_the_default_command_runner_reports_the_process_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The ONE place this module spawns anything, covered without spawning: the
    # readiness probe must survive a registry that answers slowly or not at
    # all, so the runner returns the exit status rather than raising on it.
    module = _module()

    class _Completed:
        returncode = 28
        stdout = "timed out"

    def fake_run(argv: list[str], **kwargs: object) -> _Completed:
        del argv, kwargs
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)  # pyright: ignore[reportAttributeAccessIssue]

    assert module.run_curl(("curl", "--silent", "https://ghcr.io/v2/")) == (28, "timed out")
