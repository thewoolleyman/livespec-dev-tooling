"""Actual bounded RS256 verification through the installed approved system crypto."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from livespec_dev_tooling._incident_ci_identity_json import unbase64url
from livespec_dev_tooling.incident_ci_identity_policy import (
    CiIdentityPolicy,
    identity_policy_intact,
)

_DER_SHORT_LIMIT = 128

__all__: list[str] = ["VERIFY_TIMEOUT_SECONDS", "verify_ci_signature"]

# The verifier's wall-clock bound. It protects a serving observer from a hung
# crypto process and fails closed when it expires; it is not evidence about the
# signature. It is a module value, read at call time, so a test suite can remove
# it (None: no bound) instead of reporting a loaded host as a wrong signature;
# see tests/conftest.py.
VERIFY_TIMEOUT_SECONDS: float | None = 5.0

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


def _der(*, tag: int, value: bytes) -> bytes:
    size = len(value)
    length = size.to_bytes(max(1, (size.bit_length() + 7) // 8), "big")
    encoded = bytes([size]) if size < _DER_SHORT_LIMIT else bytes([0x80 + len(length)]) + length
    return bytes([tag]) + encoded + value


def _integer(*, value: bytes) -> bytes:
    return _der(tag=2, value=(b"\0" if value[0] & 0x80 else b"") + value)


def _public_key(*, modulus: bytes, exponent: bytes) -> bytes:
    rsa = _der(tag=0x30, value=_integer(value=modulus) + _integer(value=exponent))
    algorithm = bytes.fromhex("300d06092a864886f70d0101010500")
    return _der(tag=0x30, value=algorithm + _der(tag=3, value=b"\0" + rsa))


def verify_ci_signature(
    *, policy: CiIdentityPolicy, kid: str, message: bytes, signature: bytes
) -> bool:
    """No token-selected program, URL, key material, arguments or process environment."""
    key = next((row for row in policy.keys if row[0] == kid), None)
    if key is None or not identity_policy_intact(policy=policy):
        return False
    try:
        modulus = unbase64url(value=key[1], limit=1366)
        exponent = unbase64url(value=key[2], limit=8)
        if len(signature) != len(modulus):
            return False
        with tempfile.TemporaryDirectory(prefix="livespec-ci-identity-", dir="/tmp") as name:
            root = Path(name)
            public, signed = root / "public.der", root / "signature"
            _ = public.write_bytes(_public_key(modulus=modulus, exponent=exponent))
            _ = signed.write_bytes(signature)
            done = subprocess.run(  # noqa: S603 — fixed crypto invocation from protected policy.
                [
                    str(policy.crypto_path),
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(public),
                    "-keyform",
                    "DER",
                    "-signature",
                    str(signed),
                ],
                input=message,
                cwd=root,
                env={"PATH": "/usr/bin:/bin", "HOME": name, "OPENSSL_CONF": "/dev/null"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=VERIFY_TIMEOUT_SECONDS,
                check=False,
            )
            return done.returncode == 0 and identity_policy_intact(policy=policy)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
