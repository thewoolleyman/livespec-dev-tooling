"""The recovery App's RS256 signer: the pinned crypto program, or the fixed system one.

CI signature verification runs only a program whose path and sha256 the installation
pinned (`incident_ci_identity_policy.pinned_crypto_intact`). The recovery App signs
with that same program under that same check, so the identity that is verified and
the identity that signs cannot be served by two different binaries.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_dev_tooling.incident_ci_identity_policy import pinned_crypto_intact

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_ci_identity_policy import CiIdentityPolicy

__all__: list[str] = ["openssl_sign", "pinned_signer"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gwzviw
_OPENSSL = "/usr/bin/openssl"
_SIGN_TIMEOUT_SECONDS = 10.0


def openssl_sign(
    *,
    message: bytes,
    private_key: str,
    program: Path | None = None,
    sha256: str | None = None,
) -> bytes:
    """RS256 over `message` with the installed system crypto; empty bytes on refusal.

    The rewrapped key exists only inside a private temporary directory for the
    one signing call, the shape the fleet's installation-token minter uses. With a
    `program` and its `sha256` the signer runs only that pinned program, rechecked
    before and after the call exactly as CI signature verification rechecks it
    (`incident_ci_identity_policy.pinned_crypto_intact`); a program that fails either
    check yields no signature. Without a pin it runs the fixed system program.
    """
    pinned = program is not None and sha256 is not None
    if pinned and not pinned_crypto_intact(path=cast("Path", program), sha256=cast("str", sha256)):
        return b""
    with tempfile.TemporaryDirectory(prefix="livespec-recovery-app-") as name:
        key = Path(name) / "key.pem"
        descriptor = os.open(key, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            _ = stream.write(private_key)
        try:
            done = subprocess.run(  # noqa: S603 — pinned or fixed system crypto argv; no shell or caller input.
                [
                    _OPENSSL if program is None else str(program),
                    "dgst",
                    "-sha256",
                    "-sign",
                    str(key),
                    "-binary",
                ],
                input=message,
                capture_output=True,
                check=False,
                env={"PATH": "/usr/bin:/bin", "HOME": name, "OPENSSL_CONF": "/dev/null"},
                timeout=_SIGN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return b""
    if pinned and not pinned_crypto_intact(path=cast("Path", program), sha256=cast("str", sha256)):
        return b""
    return done.stdout if done.returncode == 0 else b""


def pinned_signer(*, policy: CiIdentityPolicy | None) -> Callable[..., bytes]:
    """The signer an installation mints its tokens with: its pinned program, or the fixed one.

    An installation that provisioned CI identity trust pins one crypto program (path and
    sha256) for verification; the recovery App signs with that same program under the same
    check. One that did not pin has no digest to hold the program to, so it keeps the fixed
    system program rather than losing recovery for an optional policy.
    """
    if policy is None:
        return openssl_sign
    return partial(openssl_sign, program=policy.crypto_path, sha256=policy.crypto_sha256)
