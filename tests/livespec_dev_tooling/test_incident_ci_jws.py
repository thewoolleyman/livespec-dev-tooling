"""The approved crypto process verifies actual signing bytes with bounded failure."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from livespec_dev_tooling import incident_ci_jws as jws
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


def test_crypto_unavailable_and_private_input_write_failure_refuse(trusted, monkeypatch):
    _, policy, *_ = trusted

    def unavailable(*_args, **_kwargs):
        raise OSError("controlled unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert not jws.verify_ci_signature(
        policy=policy, kid="fixture-key", message=b"bytes", signature=b"x" * 256
    )
    monkeypatch.setattr(Path, "write_bytes", unavailable)
    assert not jws.verify_ci_signature(
        policy=policy, kid="fixture-key", message=b"bytes", signature=b"x" * 256
    )
    assert not jws.verify_ci_signature(
        policy=replace(policy, keys=(("fixture-key", "!", "AQAB"),)),
        kid="fixture-key",
        message=b"bytes",
        signature=b"x" * 256,
    )
