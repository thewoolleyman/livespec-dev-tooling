"""The signature verifier's wall-clock bound is one named value the suite removes.

`verify_ci_signature` runs the approved system crypto as a bounded subprocess and
fails closed when the bound expires. The bound protects a serving observer from
a hung verifier; it says nothing about a correct signature. A suite that runs the
real crypto under that production bound therefore reports a loaded host as a
wrong signature: master run 42134512261 failed one fixture setup that took 6.19
seconds while 7707 other tests, many through the same fixture, passed
(livespec-dev-tooling-jfp2w5).

The bound is a module value, read at call time, so `tests/conftest.py` removes
it for every test while production keeps its own. These tests hold the halves
together: the suite runs under no bound, whatever the module names is exactly
what the subprocess is given, and an expired bound still fails closed.
"""

from __future__ import annotations

import subprocess

from livespec_dev_tooling import incident_ci_jws
from livespec_dev_tooling.incident_ci_oidc import verify_oidc
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jfp2w5
_ABSENT = "the module names no bound"
_NAMED_BOUND = 4321.0
_ISSUED_NOW = 1700000010


def test_the_suite_runs_real_crypto_under_no_wall_clock_bound(trusted) -> None:
    _, policy, token, *_ = trusted

    assert getattr(incident_ci_jws, "VERIFY_TIMEOUT_SECONDS", _ABSENT) is None
    assert verify_oidc(token=token, policy=policy, now=_ISSUED_NOW) is not None


def test_the_subprocess_is_given_the_bound_the_module_names(trusted, monkeypatch) -> None:
    _, policy, token, *_ = trusted
    given: list[object] = []
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        given.append(kwargs.get("timeout"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(incident_ci_jws, "VERIFY_TIMEOUT_SECONDS", _NAMED_BOUND, raising=False)
    monkeypatch.setattr(subprocess, "run", recording_run)

    assert verify_oidc(token=token, policy=policy, now=_ISSUED_NOW) is not None
    assert given == [_NAMED_BOUND]


def test_an_expired_bound_still_fails_closed(trusted, monkeypatch) -> None:
    _, policy, token, *_ = trusted

    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout") or 0.0)

    monkeypatch.setattr(subprocess, "run", expired)

    assert verify_oidc(token=token, policy=policy, now=_ISSUED_NOW) is None
