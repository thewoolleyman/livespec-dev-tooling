"""Shared pytest fixtures for the livespec-dev-tooling suite.

Hosts an autouse fixture that resets structlog's PROCESS-GLOBAL configuration
after every test, so the suite is order- and worker-independent under
`pytest -n auto --cov` (the `check-per-file-coverage` invocation).

Root cause of the isolation bug this fixes: modules such as
`livespec_dev_tooling/fleet/wire_fleet_member.py` call
`structlog.configure(logger_factory=PrintLoggerFactory(file=sys.stderr))`, which
snapshots `sys.stderr` at configure time into structlog's global config. Under
pytest capture (especially each xdist worker's per-test capture), that stream is
a buffer closed at the test's teardown; a later test on the same worker that
inherits the stale global config then writes to the closed buffer and raises
`ValueError: I/O operation on closed file`. The failure was order-dependent —
the affected fleet tests pass in isolation but fail after a polluting test runs
first. Resetting structlog's defaults at each test's teardown removes the
cross-test leakage.

Also hosts `_gate_outcome_receiver_is_never_the_hosts_own`, which points the
delegated gate's outcome-event endpoint at a closed port for the whole suite —
see that fixture for why a default would export this suite's canned gate runs
into the fleet's real observability surface.

Also hosts `_caller_gate_variables_never_reach_a_test`, which unsets the
caller's gate-shaping `LIVESPEC_*` variables for every test, so a gate run under
a raised stall window cannot turn a default-reading test red.

Also hosts `_signature_verification_is_not_bounded_by_host_load`, which removes
the incident CI signature verifier's production wall-clock bound for the whole
suite — see that fixture for the master run a loaded runner turned red.

Also hosts `z_rendering_git`, the GIT-VERSION double described on that fixture:
a shim that makes any test observe the `%cI` rendering git 2.51 introduced,
whatever git the host happens to carry.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# structlog ships vendored; resolve the bare `import structlog` the same way the
# product modules do (each inserts this dir onto sys.path before importing it).
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.


@pytest.fixture(autouse=True)
def _reset_structlog_global_config() -> Iterator[None]:
    """Reset structlog's process-global config after each test (isolation)."""
    yield
    structlog.reset_defaults()


# Port 1 on loopback: nothing listens there, so every attempt is refused at once
# and `post_span` swallows it, which is the same no-op a host with no collector
# produces. The same closed-port technique `test_otel_step_timer` uses to drive
# the real poster without a receiver.
_CLOSED_RECEIVER = "http://127.0.0.1:1"


@pytest.fixture(autouse=True)
def _signature_verification_is_not_bounded_by_host_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the incident CI signature verifier's production wall-clock bound.

    `incident_ci_jws.verify_ci_signature` runs the system crypto as a subprocess
    bounded by `VERIFY_TIMEOUT_SECONDS` and fails closed on expiry. Fixtures such
    as `trusted` and `correlated` run that real crypto. Under the production
    bound a loaded runner's slow fork is reported as a wrong signature: master
    run 42134512261 failed one fixture setup that took 6.19 seconds while 7707
    other tests, many through the same fixture, passed
    (livespec-dev-tooling-jfp2w5).

    `None` means no bound, so no wall clock decides a test's outcome however
    slow the host is. The expiry branch needs no clock either: tests raise
    `TimeoutExpired` from a replaced `subprocess.run`. A test that wants a
    particular bound sets its own after this fixture runs.
    """
    monkeypatch.setattr("livespec_dev_tooling.incident_ci_jws.VERIFY_TIMEOUT_SECONDS", None)


@pytest.fixture(autouse=True)
def _gate_outcome_receiver_is_never_the_hosts_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the delegated gate's outcome endpoint at a closed port, suite-wide.

    `gate_outcome_telemetry` DEFAULTS to `http://127.0.0.1:4319`, the loopback
    OTLP receiver a host otel-collector serves — the right default for a
    delegating host and the wrong one for a test suite. Eleven tests drive
    `run_delegated_gate` against a canned cluster, so on any host running that
    collector the suite would export its canned tree hashes and Job names into
    the fleet's real observability surface. One of those runs reaches
    `no-verdict`, which is exactly what the delegated-gate trigger alerts on, so
    the suite would fire a production alert every time it ran and the signal
    would stop meaning anything.

    AUTOUSE RATHER THAN PER-CALL-SITE, because the failure mode is OMISSION: a
    test added later that forgets to neutralise the emitter reintroduces the
    whole fault silently, and nothing in its own output would say so. A test
    that wants to assert what one run reported injects a recording `emit` or
    monkeypatches `urlopen`; this fixture only guarantees that NOT doing so
    cannot reach a real receiver.
    """
    monkeypatch.setenv("LIVESPEC_GATE_OTLP_ENDPOINT", _CLOSED_RECEIVER)


# The gate-shaping variables a caller's environment can carry into the suite.
# Each one is read by product code a test exercises: the suite-green stall window
# and timeout ceiling (`_red_green_replay_suite_runner`), the replay's worker
# count and CI lane (`_red_green_replay_suite_argv`), and the same four in the
# pack's `gate-run.sh`.
_CALLER_GATE_VARIABLES = (
    "LIVESPEC_SUITE_GREEN_STALL_SECONDS",
    "LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS",
    "LIVESPEC_TEST_PARALLELISM",
    "LIVESPEC_CI_LANE",
)


@pytest.fixture(autouse=True)
def _caller_gate_variables_never_reach_a_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset the caller's gate-shaping variables for every test.

    A gate run under a raised stall window (`LIVESPEC_SUITE_GREEN_STALL_SECONDS`
    of 3600, say) runs this suite with that variable in its environment. A test
    that reads the default through product code then sees the caller's value
    and fails, so the same tree passes or fails depending on who ran it
    (livespec-dev-tooling-ltwdfq). Patching each test that reads one of them
    did not hold: a suite-green test added in a PR that merged first was left
    reading the caller's window, and failed `assert 3600 == 900`.

    AUTOUSE RATHER THAN PER-CALL-SITE, because the failure mode is OMISSION,
    exactly as for the outcome receiver above. A test that needs one of these
    variables sets it itself after this fixture runs, and a subprocess test that
    copies `os.environ` inherits the cleaned environment.
    """
    for name in _CALLER_GATE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _trusted_origin_is_never_the_hosts_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test start from an untrusted, ordinary incident origin.

    The incident gate entrances force normal mode, before parsing any inherited
    incident flag, in a master-push CI job (`GITHUB_ACTIONS` with
    `GITHUB_EVENT_NAME=push`) and in a factory sandbox (the
    `livespec.sandboxExempt` git marker). This suite runs in exactly those two
    places, so without this fixture a test that asserts an ordinary refusal of an
    incident flag would pass or fail depending on who ran it. A test that drives
    the real origin probe overrides this fixture by name.
    """
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_trusted_origin.factory_sandbox", lambda **_kwargs: False
    )


# Real git does all the work; only the rendering of a full ISO instant's UTC
# offset is rewritten. The anchor on the time-of-day group is what keeps the
# rewrite to a `%cI`-shaped field rather than to any `+00:00` a blob read
# happens to end a line with.
_Z_RENDERING_GIT_SHIM = r"""#!/bin/sh
"{git}" "$@" | sed -e 's/\(T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\)+00:00$/\1Z/'
"""


@pytest.fixture
def z_rendering_git(
    *, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prepend a `git` shim that renders a `+00:00` committer offset as a trailing `Z`.

    A GIT-VERSION DOUBLE, NOT A GIT DOUBLE. git 2.51 changed how `%cI` spells a
    UTC offset: measured 2026-10-14 on hp-xubuntu (git 2.51.0), `%cI` prints
    `2026-01-02T00:00:00Z` where `%ci` still prints `+0000`, while every older
    git — including the Fabro sandbox image's 2.43 — prints `+00:00`.
    `datetime.fromisoformat` only began accepting that suffix in Python 3.11
    and this repository pins 3.10.16, so on a git>=2.51 host every
    committer-instant read of the heading-coverage debt register raised
    `ValueError`: 14 suite tests failed and the register generator crashed
    outright, while CI stayed green on a runner image carrying an older git.

    That split is the reason this fixture exists rather than a `+00:00` fixture
    commit and a host upgrade. A defect reachable on one fleet host and
    UNPROVABLE on another is how this one reached master; a test that observes
    the newer rendering on any host is the thing that was missing.
    """
    real_git = shutil.which("git")
    assert real_git is not None, "the suite requires a real `git` on PATH"
    shim_dir = tmp_path_factory.mktemp("z-rendering-git")
    shim = shim_dir / "git"
    _ = shim.write_text(_Z_RENDERING_GIT_SHIM.format(git=real_git), encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
