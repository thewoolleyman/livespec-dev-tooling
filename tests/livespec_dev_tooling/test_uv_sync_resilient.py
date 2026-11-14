"""Outside-in test for `livespec_dev_tooling/uv_sync_resilient.py`.

The module wraps the fleet's dependency-install step so that the two RECORDED
transient failure mechanisms — a PyPI package download that times out, and a
`git+https` cross-repo-pin fetch that fails TLS trust — re-attempt themselves
instead of leaving a master branch red until a human notices.

The whole risk in a self-healing install step is that it heals a GENUINE
failure too, which is why every test here is paired against that hazard rather
than only against the happy path:

* `test_unrecognised_failure_is_not_retried` is the load-bearing one. A
  resolution error (a package that does not exist, a lock that cannot be
  satisfied) must propagate on the FIRST attempt with uv's own exit code and
  ZERO re-attempts. A wrapper that retries whatever it is handed is the
  "retry-the-whole-job wrapper that masks a genuine failure as a transient"
  the work item explicitly forbids.
* `test_marker_without_a_corroborator_is_not_retried` is the same hazard one
  level finer. `Failed to download` alone is NOT a transient — uv prints it
  for a package that is genuinely absent too. Only the marker CORROBORATED by
  a transport symptom (`operation timed out`, `Request failed after`, a git
  transport/trust failure) classifies.

The fixtures are the verbatim failure tails recorded on the work item across
five repositories, not paraphrases: a classifier tested against invented
strings proves nothing about the output uv actually emits.

`main()` is driven IN-PROCESS with an injected command runner and an injected
sleep, so no test spawns `uv`, waits a real backoff, or touches the network.
The ONE test that exercises the real default runner
(`test_the_default_runner_invokes_uv_sync`) reaches it through `main()` with
`subprocess.run` stubbed, rather than by importing the private helper — the
argv it builds is part of what this module promises, and a test that reached
past `main()` to assert it would be asserting an implementation detail.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

import pytest

from livespec_dev_tooling import uv_sync_resilient

__all__: list[str] = []


# The PyPI-download mechanism, verbatim from run 31467774243 (this repo's own
# master, 2026-08-11T07:13:16Z). Five distinct packages were recorded across
# the fleet with this identical shape; the package name is the only variable.
_PACKAGE_TIMEOUT = (
    "  x Failed to download `pytest-xdist==3.8.0`\n"
    "  |-> Request failed after 5 retries\n"
    "  `-> operation timed out\n"
)

# The git-fetch mechanism, verbatim from livespec run 31511508628
# (2026-08-11T16:16:59Z). It exits IMMEDIATELY rather than after exhausting
# `UV_HTTP_RETRIES`, which is exactly why no retry knob reaches it.
_GIT_TLS = (
    "  x Failed to download and build `livespec-dev-tooling @ "
    "git+https://github.com/thewoolleyman/livespec-dev-tooling.git@aeb6aa32`\n"
    "  |-> Git operation failed\n"
    "  |-> failed to clone into: /github/home/.cache/uv/git-v0/db/65b9be868a1be312\n"
    "  `-> fatal: unable to access 'https://github.com/thewoolleyman/"
    "livespec-dev-tooling.git/': server certificate verification failed. "
    "CAfile: none CRLfile: none\n"
)

# A GENUINE failure: the lock cannot be satisfied. Nothing here is transient
# and re-attempting it would burn CI time to reach the identical verdict.
_GENUINE_RESOLUTION_FAILURE = (
    "  x No solution found when resolving dependencies:\n"
    "  `-> Because there is no version of nonexistent-package==9.9.9 and the "
    "project depends on nonexistent-package==9.9.9, we can conclude that the "
    "project's requirements are unsatisfiable.\n"
)

# `Failed to download` with no transport symptom beside it. uv emits this for
# a package that is simply absent from the index.
_UNCORROBORATED_MARKER = (
    "  x Failed to download `nonexistent-package==9.9.9`\n"
    "  `-> Package `nonexistent-package` was not found in the registry\n"
)

# The mid-transfer mechanism measured on livespec#3227 (CI run 43598329598,
# 2026-11-14): the git-sourced `livespec-runtime` fetch died with libcurl's
# "Failure when receiving data from the peer". The transport symptom sits in
# git's own stderr, beneath uv's `Git operation failed` / `failed to fetch
# commit` frames.
_GIT_PEER_FAILURE = (
    "  x Failed to download and build `livespec-runtime @ "
    "git+https://github.com/thewoolleyman/livespec-runtime.git@0123abc`\n"
    "  |-> Git operation failed\n"
    "  |-> failed to fetch commit `0123abc`\n"
    "  `-> process didn't exit successfully: `/usr/bin/git fetch --force "
    "--update-head-ok` (exit status: 128)\n"
    "      --- stderr\n"
    "      error: RPC failed; curl 56 Failure when receiving data from the peer\n"
    "      fatal: expected flush after ref listing\n"
)

# PERMANENT git failures. Each carries the SAME uv frames as the transient
# above (`Git operation failed` + `failed to fetch commit`), so only the
# permanent diagnosis beneath them tells the two apart.
# The same transport symptom WITHOUT uv's `failed to fetch commit` frame, so
# the peer failure itself is what has to classify.
_GIT_PEER_FAILURE_BARE = (
    "  x Failed to download and build `livespec-runtime @ "
    "git+https://github.com/thewoolleyman/livespec-runtime.git@0123abc`\n"
    "  |-> Git operation failed\n"
    "  `-> fatal: Failure when receiving data from the peer\n"
)

_GIT_UNKNOWN_COMMIT = (
    "  x Failed to download and build `livespec-runtime @ "
    "git+https://github.com/thewoolleyman/livespec-runtime.git@deadbeef`\n"
    "  |-> Git operation failed\n"
    "  |-> failed to fetch commit `deadbeef`\n"
    "  `-> process didn't exit successfully: `/usr/bin/git fetch` "
    "(exit status: 128)\n"
    "      --- stderr\n"
    "      fatal: couldn't find remote ref deadbeef\n"
)

_GIT_AUTH_REFUSAL = (
    "  x Failed to download and build `livespec-runtime @ "
    "git+https://github.com/thewoolleyman/livespec-runtime.git@0123abc`\n"
    "  |-> Git operation failed\n"
    "  |-> failed to fetch commit `0123abc`\n"
    "  `-> process didn't exit successfully: `/usr/bin/git fetch` "
    "(exit status: 128)\n"
    "      --- stderr\n"
    "      fatal: unable to access "
    "'https://github.com/thewoolleyman/livespec-runtime.git/': "
    "The requested URL returned error: 403\n"
    "      fatal: Authentication failed for "
    "'https://github.com/thewoolleyman/livespec-runtime.git/'\n"
)

_SUCCESS = "Resolved 214 packages\nInstalled 3 packages\n"


def _scripted(*, outcomes: list[tuple[int, str]]) -> Callable[[], tuple[int, str]]:
    """Return a runner yielding `outcomes` in order, one per attempt."""
    remaining = list(outcomes)

    def run() -> tuple[int, str]:
        return remaining.pop(0)

    return run


def _recorder() -> tuple[Callable[[float], None], list[float]]:
    """Return a sleep that records its delays instead of waiting."""
    delays: list[float] = []

    def sleep(seconds: float) -> None:
        delays.append(seconds)

    return sleep, delays


def test_a_clean_install_runs_exactly_once() -> None:
    sleep, delays = _recorder()
    outcomes = [(0, _SUCCESS)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 0
    assert delays == []


def test_package_download_timeout_is_re_attempted_and_recovers() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _PACKAGE_TIMEOUT), (0, _SUCCESS)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 0
    assert len(delays) == 1


def test_git_trust_failure_is_re_attempted_and_recovers() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_TLS), (0, _SUCCESS)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 0
    assert len(delays) == 1


def test_a_persistent_transient_exhausts_its_attempts_and_fails() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _PACKAGE_TIMEOUT), (2, _PACKAGE_TIMEOUT), (2, _PACKAGE_TIMEOUT)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 2
    assert len(delays) == 2


def test_unrecognised_failure_is_not_retried() -> None:
    sleep, delays = _recorder()
    outcomes = [(1, _GENUINE_RESOLUTION_FAILURE)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 1
    assert delays == []


def test_marker_without_a_corroborator_is_not_retried() -> None:
    sleep, delays = _recorder()
    outcomes = [(1, _UNCORROBORATED_MARKER)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 1
    assert delays == []


def test_the_default_runner_invokes_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no runner injected, `main()` installs via `uv sync --all-groups`.

    The wrapper must add resilience and NOTHING else: a wrapper that quietly
    installed a different dependency set would satisfy every other test here
    while changing what CI actually verifies.
    """
    sleep, delays = _recorder()
    invocations: list[list[str]] = []
    wiring: list[dict[str, object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        invocations.append(argv)
        wiring.append(kwargs)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=_SUCCESS)

    monkeypatch.setattr(uv_sync_resilient.subprocess, "run", fake_run)
    rc = uv_sync_resilient.main(sleep=sleep)
    assert rc == 0
    assert invocations == [["uv", "sync", "--all-groups"]]
    assert delays == []
    # uv's stderr MUST be folded into the captured stream. Both recorded
    # mechanisms print their diagnostic tail on stderr, so a runner that
    # captured stdout alone would hand the classifier an empty string and
    # every transient would read as a genuine failure.
    assert wiring[0]["stderr"] is subprocess.STDOUT
    assert wiring[0]["check"] is False


def test_backoff_lengthens_between_attempts() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_TLS), (2, _PACKAGE_TIMEOUT), (2, _GIT_TLS)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 2
    assert delays[1] > delays[0]


def test_a_git_fetch_peer_failure_is_re_attempted_and_recovers() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_PEER_FAILURE), (2, _GIT_PEER_FAILURE_BARE), (0, _SUCCESS)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 0
    assert len(delays) == 2


def test_an_exhausted_git_fetch_fails_closed_naming_dependency_error_and_attempts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_PEER_FAILURE)] * 3
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 2
    assert len(delays) == 2
    exhaustion = [
        json.loads(line) for line in capsys.readouterr().err.splitlines() if "exhausted" in line
    ]
    assert len(exhaustion) == 1
    record = exhaustion[0]
    assert "livespec-runtime" in record["dependency"]
    assert "Failure when receiving data from the peer" in record["transport_error"]
    assert record["attempts"] == 3
    for named in ("livespec-runtime", "Failure when receiving data from the peer", "3"):
        assert named in record["event"]


def test_an_unknown_commit_is_not_retried() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_UNKNOWN_COMMIT)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 2
    assert delays == []


def test_an_authentication_refusal_is_not_retried() -> None:
    sleep, delays = _recorder()
    outcomes = [(2, _GIT_AUTH_REFUSAL)]
    rc = uv_sync_resilient.main(run=_scripted(outcomes=outcomes), sleep=sleep)
    assert rc == 2
    assert delays == []
