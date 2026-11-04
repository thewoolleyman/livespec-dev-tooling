"""Untrusted JOSE bytes never choose trust, crypto, or an incident capability."""

from __future__ import annotations

import base64
import json
import subprocess

import pytest

from livespec_dev_tooling._incident_ci_identity_json import identity_json, unbase64url
from livespec_dev_tooling.incident_ci_oidc import verify_oidc
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests
from tests.livespec_dev_tooling.test_incident_ci_oidc import encoded

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


def resign(trusted, *, claims=None, header=None, raw_claims=None, raw_header=None):
    _, policy, _, original, private = trusted
    claims = original if claims is None else claims
    header = (
        {"typ": "JWT", "alg": "RS256", "kid": "fixture-key", "x5t": "documented"}
        if header is None
        else header
    )
    message = (
        encoded(json.dumps(header).encode() if raw_header is None else raw_header)
        + "."
        + encoded(json.dumps(claims).encode() if raw_claims is None else raw_claims)
    ).encode()
    signature = subprocess.run(
        [str(policy.crypto_path), "dgst", "-sha256", "-sign", str(private)],
        input=message,
        capture_output=True,
        check=True,
    ).stdout
    return message.decode() + "." + encoded(signature)


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker"},
        {"aud": ["urn:livespec:fixture"]},
        {"sub": "foreign"},
        {"repository": "other/repo"},
        {"repository_id": "0123"},
        {"repository_owner_id": True},
        {"run_id": 0},
        {"run_attempt": True},
        {"check_run_id": "-2"},
        {"event_name": "push"},
        {"event_name": "pull_request_target"},
        {"ref": "refs/pull/55/head"},
        {"iat": True},
        {"nbf": "1700000000"},
        {"iat": 1700000020},
        {"nbf": 1700000020},
        {"exp": 1700000010},
        {"job_workflow_ref": "owner/provider/.github/workflows/protected.yml@master"},
        {"job_workflow_sha": "e" * 40},
        {"sha": "not-sha"},
        {"workflow_sha": "not-sha"},
        {"workflow_ref": "other/repo/.github/workflows/ci.yml@refs/pull/55/merge"},
        {"head_ref": "\n"},
    ],
)
def test_signed_unsupported_or_wrong_identity_refuses(trusted, change):
    _, policy, _, claims, _ = trusted
    token = resign(trusted, claims=claims | change)
    assert verify_oidc(token=token, policy=policy, now=1700000010) is None


@pytest.mark.parametrize(
    "change",
    [
        {"alg": "none"},
        {"alg": "HS256"},
        {"typ": "other"},
        {"kid": "rotated"},
        {"kid": []},
        {"jku": "https://attacker"},
        {"jwk": {}},
        {"crit": []},
        {"x5u": "https://attacker"},
        {"x5t": "x" * 257},
    ],
)
def test_signed_header_cannot_inject_keys_urls_or_critical_semantics(trusted, change):
    _, policy, *_ = trusted
    header = {"typ": "JWT", "alg": "RS256", "kid": "fixture-key"} | change
    assert verify_oidc(token=resign(trusted, header=header), policy=policy, now=1700000010) is None


def test_real_signature_rejects_claim_and_signature_tampering(trusted):
    _, policy, token, claims, _ = trusted
    first, _, signature = token.split(".")
    tampered = (
        first
        + "."
        + encoded(json.dumps(claims | {"check_run_id": "914"}).encode())
        + "."
        + signature
    )
    assert verify_oidc(token=tampered, policy=policy, now=1700000010) is None
    signature_bytes = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    tampered = (
        ".".join(token.split(".")[:2])
        + "."
        + encoded(bytes([signature_bytes[0] ^ 1]) + signature_bytes[1:])
    )
    assert verify_oidc(token=tampered, policy=policy, now=1700000010) is None


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":Infinity}', b"[]", b"\xff", b"{"]
)
def test_strict_identity_json_rejects_ambiguity_and_extensions(raw):
    with pytest.raises((ValueError, TypeError, UnicodeError)):
        identity_json(raw=raw)


@pytest.mark.parametrize("value", ["", "a", "AB", "a=", "+/", "a" * 17, 3])
def test_base64_requires_bounded_canonical_unpadded_encoding(value):
    with pytest.raises(ValueError, match="identity|base64"):
        unbase64url(value=value, limit=16)


def test_bounds_malformed_and_duplicate_signed_tokens(trusted):
    _, policy, *_ = trusted
    assert unbase64url(value="AA", limit=2) == b"\0"
    with pytest.raises(ValueError, match="identity|base64"):
        identity_json(raw=b"{}", limit=1)
    for token in (
        "",
        "x" * 16385,
        "a.b",
        "a.b.c",
        resign(trusted, raw_header=b'{"alg":"RS256","alg":"none"}'),
        resign(trusted, raw_claims=b'{"exp":NaN}'),
    ):
        assert verify_oidc(token=token, policy=policy, now=1700000010) is None
