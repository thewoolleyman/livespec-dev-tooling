"""Consumer-tier: the two `SPECIFICATION/scenarios.md` sandbox-image readiness scenarios
for a livespec-dev-tooling release fan-out.

    Given a livespec-dev-tooling release T whose livespec-fabro-sandbox semver
    tags are not yet served by ghcr.io
    When the release fan-out runs
    Then it MUST send no sibling-released dispatch while any of T's tags is absent
    And it MUST dispatch to every unexcluded sibling once all of T's tags are served

    Given a livespec-dev-tooling release T whose livespec-fabro-sandbox tags are
    not all served after the 90-minute bound
    When the release fan-out reaches that bound
    Then the run MUST fail with an annotation naming each missing tag
    And it MUST send no sibling-released dispatch

Measured 2026-10-22 (coordinator R612): v1.125.0 published at 10:38:18Z and the
consumer bump PRs opened at 10:43Z, but ghcr.io did not serve
`python-rust-agent-v1.125.0` until 11:08Z to 11:19Z. One consumer's `check-arch`
took a 404 and needed a rerun; livespec-orchestrator-beads-fabro's bump PR
MERGED at 10:52:20Z, putting a sandbox tag on its master that ghcr would not
serve for another 27 minutes — so any factory dispatch from that repo in the
window would have pulled an image that did not exist. A bump to a tag that does
not exist is not a usable bump.

WHAT THE GATE IS, AND WHERE "no dispatch" IS OBSERVABLE. The shipped surface is
a readiness GATE with a bounded poll: it clears (exit `0`) only once ghcr.io
serves every layered tag a bump to T writes, and it fails (exit non-zero, with
an `::error::` annotation naming each missing tag) at the ratified bound. The
fan-out wires it as a REQUIRED PREDECESSOR of the dispatch matrix, so "sends no
dispatch" is the ordinary meaning of a failed `needs:` job — the workflow half
is the item's host-captured assertion, proved on a real release. What is
provable here, and is proved below, is everything the gate itself decides: that
it does not clear while a tag is absent, that it does clear once every tag is
served, that its failure names every missing tag, and that a release of any
other source repo does not wait at all.

The ghcr probe and the clock are injected, so these tests reach no registry and
sleep for no seconds; the module's own mirrored test covers the default probe.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_NAME = "livespec_dev_tooling.fleet.sandbox_image_readiness"
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "fleet" / "sandbox_image_readiness.py"

_RELEASE_TAG = "v1.125.0"
_DEV_TOOLING = "livespec-dev-tooling"
# The six layered tags `fabro-sandbox-image.yml` publishes per release, which
# are exactly the tags a bump to T rewrites a consumer's pins to.
_EXPECTED_TAGS = (
    f"base-{_RELEASE_TAG}",
    f"python-{_RELEASE_TAG}",
    f"python-agent-{_RELEASE_TAG}",
    f"python-rust-{_RELEASE_TAG}",
    f"python-rust-agent-{_RELEASE_TAG}",
    f"python-rust-fuzz-{_RELEASE_TAG}",
)
# The one the registry served 27 minutes late on 2026-10-22.
_LATE_TAG = f"python-rust-agent-{_RELEASE_TAG}"


def _readiness() -> ModuleType:
    """The shipped gate module, imported inside the test body on purpose.

    A module-level import would make the first run of this file a COLLECTION
    error, which proves only that a module is missing — never that the gate
    does not yet hold the fan-out back.
    """
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _Registry:
    """A ghcr double that starts serving the late tag after `late_after` rounds."""

    late_after: int
    rounds: int = 0
    served: list[str] = field(default_factory=list)

    def probe(self, *, tag: str) -> bool:
        if tag == _EXPECTED_TAGS[0]:
            self.rounds += 1
        self.served.append(tag)
        return tag != _LATE_TAG or self.rounds > self.late_after


@dataclass(kw_only=True)
class _Clock:
    """A monotonic clock that advances only when the gate sleeps."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _clock(*, module: ModuleType) -> object:
    state = _Clock()
    return module.Clock(monotonic=state.monotonic, sleep=state.sleep), state


def test_the_shipped_gate_module_exists_and_names_every_layered_tag_a_bump_writes() -> None:
    """The tag set IS the obligation: a tag it omits is one nothing waits for."""
    assert _MODULE_PATH.is_file(), (
        "the release fan-out needs a shipped sandbox-image readiness gate; without one "
        f"nothing holds a dispatch back while ghcr is still building ({_MODULE_PATH})"
    )
    module = _readiness()

    assert module.sandbox_image_tags(tag=_RELEASE_TAG) == _EXPECTED_TAGS, (
        "every layered tag a bump to T writes must be waited for, including the "
        "python-rust-agent layer ghcr served 27 minutes late on 2026-10-22; got "
        f"{module.sandbox_image_tags(tag=_RELEASE_TAG)!r}"
    )


def test_the_gate_does_not_clear_while_any_sandbox_tag_is_absent() -> None:
    """One absent tag holds the whole fan-out: a partial image is not a usable bump."""
    module = _readiness()
    registry = _Registry(late_after=10**6)
    clock, state = _clock(module=module)

    missing = module.await_sandbox_image(
        tag=_RELEASE_TAG, probe=registry.probe, clock=clock, poll_seconds=60
    )

    assert missing == (_LATE_TAG,), (
        "the gate must not clear while a tag is absent, and must report exactly which "
        f"tag held it; got {missing!r}"
    )
    assert state.slept, (
        "the gate must POLL rather than answer once — a single read at release time is "
        "the very race this exists to close"
    )
    assert state.now >= module.WAIT_BOUND_SECONDS, (
        "it must keep waiting until the ratified bound rather than giving up on the "
        f"first absent read; waited {state.now!r}s of {module.WAIT_BOUND_SECONDS!r}s"
    )


def test_the_gate_clears_once_every_sandbox_tag_is_served() -> None:
    """And it clears on its own, so the dispatch is delayed rather than lost."""
    module = _readiness()
    registry = _Registry(late_after=3)
    clock, state = _clock(module=module)

    missing = module.await_sandbox_image(
        tag=_RELEASE_TAG, probe=registry.probe, clock=clock, poll_seconds=60
    )

    assert missing == (), (
        f"once ghcr serves every tag the gate must clear and let the fan-out dispatch to "
        f"every unexcluded sibling; got {missing!r}"
    )
    assert registry.rounds > 1, (
        "this fixture only serves the late tag after several rounds, so a gate that "
        "cleared here without re-reading would be passing by accident"
    )


def test_the_run_fails_at_the_bound_with_an_annotation_naming_each_missing_tag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A withheld dispatch that says nothing is indistinguishable from a healthy run."""
    module = _readiness()
    registry = _Registry(late_after=10**6)
    clock, _ = _clock(module=module)

    exit_code = module.main(
        argv=["--source-repo", _DEV_TOOLING, "--tag", _RELEASE_TAG],
        probe=registry.probe,
        clock=clock,
    )

    assert exit_code != 0, (
        "the run MUST fail at the bound — exiting 0 would release every dispatch to a "
        f"tag ghcr does not serve; got {exit_code!r}"
    )
    annotations = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::error::")
    ]
    assert annotations, "the failure MUST surface as a workflow annotation, not a silent exit"
    assert any(_LATE_TAG in line for line in annotations), (
        f"the annotation MUST name each missing tag so an operator knows which layer the "
        f"image build has not finished; got {annotations!r}"
    )


def test_a_release_of_any_other_source_repo_does_not_wait() -> None:
    """The wait is scoped to the repo that publishes the image; nobody else pays for it."""
    module = _readiness()
    registry = _Registry(late_after=10**6)
    clock, state = _clock(module=module)

    exit_code = module.main(
        argv=["--source-repo", "livespec-runtime", "--tag", _RELEASE_TAG],
        probe=registry.probe,
        clock=clock,
    )

    assert exit_code == 0, f"a non-dev-tooling release must fan out unheld; got {exit_code!r}"
    assert registry.served == [], (
        f"it must not even probe the registry: no other repo's release writes a "
        f"livespec-fabro-sandbox tag; got {registry.served!r}"
    )
    assert state.slept == [], f"and it must not wait at all; got {state.slept!r}"


def test_the_bound_is_the_ratified_ninety_minutes_and_carries_no_lever() -> None:
    """A settable bound is a severity lever wearing a different name."""
    module = _readiness()

    assert (
        module.WAIT_BOUND_SECONDS == 90 * 60
    ), f"the contract bounds the wait at 90 minutes; got {module.WAIT_BOUND_SECONDS!r}"
    with pytest.raises(SystemExit):
        _ = module.main(
            argv=["--source-repo", _DEV_TOOLING, "--tag", _RELEASE_TAG, "--bound-seconds", "1"]
        )
