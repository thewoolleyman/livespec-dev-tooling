#!/usr/bin/env python3
"""Render one installation's protected CI identity policy from its inventory entry.

Work-item livespec-dev-tooling-bqnzcm.4 (plan expedited-incident-response-flag).

Run with the INSTALLATION's own interpreter, isolated:

    /opt/livespec-incident/venv/bin/python -I render_ci_identity_policy.py \\
        --repository <owner/name> --repository-id <id> --owner-id <id> \\
        --audience <audience> --publisher-repository <owner/name> \\
        --publisher-sha <40-hex> [--publisher-sha <40-hex> ...] \\
        --jwks <file the role fetched> --crypto /usr/bin/openssl

It prints the policy JSON on stdout and writes nothing: the role installs it beside
controller.json, private to the controller account, and binds it into the
released-installation manifest by path and digest (docs/incident-ci-identity.md).

Every value comes from the role's inventory entry and variables, never from a
literal in this file: the served repository and its stable repository and owner ids,
the audience, and the approved publisher commits of
`<publisher-repository>/.github/workflows/reusable-incident-ci-publish.yml`. The
issuer keys are the RSA signing keys of the forge's JWKS, which the role fetched at
apply time. A forge key rotation is remedied by re-applying the role, which
re-fetches them; until then a token under the new key is refused by its key id.
The crypto executable is pinned by the digest of its bytes on this host.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

__all__: list[str] = ["PolicyRefusalError", "main", "render_policy"]

_PUBLISHER_WORKFLOW = ".github/workflows/reusable-incident-ci-publish.yml"
_SHA = re.compile(r"[0-9a-f]{40}")
_KEY_FIELDS = ("kid", "n", "e")
# The bounds incident_ci_identity_policy's loader enforces on every issuer key. One
# key outside them makes the loader refuse the WHOLE policy, so a row outside them
# is dropped here, by name, rather than written.
_MAX_KEYS = 16
_MIN_RSA_BITS = 2048
_MAX_RSA_BITS = 8192
_MIN_EXPONENT = 3
_MODULUS_LIMIT = 1366
_EXPONENT_LIMIT = 8
_KID_LIMIT = 256
_MIN_CHARACTER = 32
_CHARACTER_LIMIT = 127
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


class PolicyRefusalError(ValueError):
    """The inputs cannot make a policy the controller would load."""


def render_policy(*, args: argparse.Namespace) -> dict[str, Any]:
    """The schema-1 policy for one installation, or PolicyRefusalError naming why."""
    shas = cast("list[str]", args.publisher_sha or [])
    if not shas or any(_SHA.fullmatch(sha) is None for sha in shas):
        message = "every publisher commit must be a full lowercase 40-hex SHA, and one is required"
        raise PolicyRefusalError(message)
    keys = _issuer_keys(jwks=json.loads(Path(args.jwks).read_text(encoding="utf-8")))
    if not keys:
        message = "the forge's JWKS carries no RSA signing key with kid, n and e within bounds"
        raise PolicyRefusalError(message)
    if len(keys) > _MAX_KEYS:
        message = f"the forge's JWKS carries more than {_MAX_KEYS} usable keys; none was chosen"
        raise PolicyRefusalError(message)
    crypto = Path(args.crypto)
    return {
        "schema": 1,
        "audience": args.audience,
        "subject": "repo:" + args.repository + ":pull_request",
        "repository": args.repository,
        "repository_id": args.repository_id,
        "repository_owner_id": args.owner_id,
        "approved_reusable_workflows": [
            {"ref": args.publisher_repository + "/" + _PUBLISHER_WORKFLOW + "@" + sha, "sha": sha}
            for sha in shas
        ],
        "issuer_keys": keys,
        "crypto": {"path": str(crypto), "sha256": hashlib.sha256(crypto.read_bytes()).hexdigest()},
    }


def _issuer_keys(*, jwks: object) -> list[dict[str, str]]:
    """The JWKS's RSA keys the loader accepts; every other row is dropped with its reason."""
    rows = cast("dict[str, object]", jwks).get("keys") if isinstance(jwks, dict) else None
    candidates: list[dict[str, str]] = []
    for raw in cast("list[object]", rows) if isinstance(rows, list) else []:
        row = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
        problem = _key_problem(row=row)
        if problem is None:
            candidates.append({k: cast("str", row[k]) for k in _KEY_FIELDS})
        else:
            _ = sys.stderr.write("dropped issuer key " + problem + "\n")
    kids = [key["kid"] for key in candidates]
    for kid in sorted({kid for kid in kids if kids.count(kid) > 1}):
        _ = sys.stderr.write(f"dropped issuer key {kid}: the key set repeats this key id\n")
    return [key for key in candidates if kids.count(key["kid"]) == 1]


def _key_problem(*, row: dict[str, object]) -> str | None:
    """Why the loader would refuse this row, or None when it accepts it."""
    kid = row.get("kid")
    if (
        not isinstance(kid, str)
        or not 0 < len(kid) <= _KID_LIMIT
        or not all(_MIN_CHARACTER <= ord(c) < _CHARACTER_LIMIT for c in kid)
    ):
        return "with an unprintable or oversized kid"
    if row.get("kty") != "RSA":
        return kid + ": not an RSA key"
    modulus = _unbase64url(value=row.get("n"), limit=_MODULUS_LIMIT)
    if (
        not modulus
        or modulus[0] == 0
        or not _MIN_RSA_BITS <= int.from_bytes(modulus, "big").bit_length() <= _MAX_RSA_BITS
        or modulus[-1] % 2 == 0
    ):
        return kid + ": modulus is not a canonical odd 2048-8192-bit RSA modulus"
    exponent = _unbase64url(value=row.get("e"), limit=_EXPONENT_LIMIT)
    value = int.from_bytes(exponent or b"", "big")
    if not exponent or exponent[0] == 0 or not _MIN_EXPONENT <= value < 2**32 or value % 2 == 0:
        return kid + ": exponent is not a canonical odd value in [3, 2**32)"
    return None


def _unbase64url(*, value: object, limit: int) -> bytes | None:
    """Canonical unpadded base64url within `limit` characters, as the loader requires."""
    # A length of 1 mod 4 is the one shape this alphabet cannot decode; every
    # other length decodes once padded, so no decode below can raise.
    if (
        not isinstance(value, str)
        or len(value) > limit
        or len(value) % 4 == 1
        or _BASE64URL.fullmatch(value) is None
    ):
        return None
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    return decoded if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode() == value else None


def main(*, argv: list[str] | None = None) -> int:
    """Print the policy JSON, or refuse naming the cause."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repository", required=True)
    _ = parser.add_argument("--repository-id", required=True, type=int)
    _ = parser.add_argument("--owner-id", required=True, type=int)
    _ = parser.add_argument("--audience", required=True)
    _ = parser.add_argument("--publisher-repository", required=True)
    _ = parser.add_argument("--publisher-sha", action="append")
    _ = parser.add_argument("--jwks", required=True)
    _ = parser.add_argument("--crypto", required=True)
    try:
        policy = render_policy(args=parser.parse_args(sys.argv[1:] if argv is None else argv))
    except (PolicyRefusalError, OSError, json.JSONDecodeError) as error:
        _ = sys.stderr.write("refused: " + str(error) + "\n")
        return 2
    _ = sys.stdout.write(json.dumps(policy, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
