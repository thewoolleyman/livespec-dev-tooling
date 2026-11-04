"""A genuine issuer-signature assertion with a controlled real RSA signer."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from livespec_dev_tooling.incident_ci_identity_policy import load_identity_policy
from livespec_dev_tooling.incident_ci_oidc import verify_oidc

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def signed_fixture(root):
    """Create an ephemeral test key, never a production identity credential."""
    crypto_name = shutil.which("openssl")
    assert crypto_name is not None
    crypto = Path(crypto_name).resolve()
    private = root / "fixture-private.pem"
    subprocess.run(
        [
            str(crypto),
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-pkeyopt",
            "rsa_keygen_pubexp:65537",
            "-out",
            str(private),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    modulus = (
        subprocess.run(
            [str(crypto), "rsa", "-in", str(private), "-noout", "-modulus"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
        .removeprefix("Modulus=")
    )
    revision = "f" * 40
    policy = {
        "schema": 1,
        "audience": "urn:livespec:fixture",
        "subject": "repo:owner/repo:pull_request",
        "repository": "owner/repo",
        "repository_id": 123,
        "repository_owner_id": 456,
        "approved_reusable_workflows": [
            {"ref": f"owner/provider/.github/workflows/protected.yml@{revision}", "sha": revision}
        ],
        "issuer_keys": [{"kid": "fixture-key", "n": encoded(bytes.fromhex(modulus)), "e": "AQAB"}],
        "crypto": {"path": str(crypto), "sha256": hashlib.sha256(crypto.read_bytes()).hexdigest()},
    }
    path = root / "ci-identity.json"
    path.write_text(json.dumps(policy))
    path.chmod(0o600)
    descriptor = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": policy["audience"],
        "sub": policy["subject"],
        "iat": 1700000000,
        "nbf": 1700000000,
        "exp": 1700000300,
        "repository": "owner/repo",
        "repository_id": "123",
        "repository_owner_id": "456",
        "run_id": "812",
        "run_attempt": "2",
        "check_run_id": "913",
        "event_name": "pull_request",
        "ref": "refs/pull/55/merge",
        "sha": "d" * 40,
        "base_ref": "master",
        "head_ref": "repair",
        "workflow_ref": "owner/repo/.github/workflows/ci.yml@refs/pull/55/merge",
        "workflow_sha": "d" * 40,
        "job_workflow_ref": policy["approved_reusable_workflows"][0]["ref"],
        "job_workflow_sha": revision,
    }
    header = {"typ": "JWT", "alg": "RS256", "kid": "fixture-key", "x5t": "fixture-thumbprint"}
    message = (
        encoded(json.dumps(header).encode()) + "." + encoded(json.dumps(claims).encode())
    ).encode()
    message_path, signature_path = root / "message", root / "signature"
    message_path.write_bytes(message)
    subprocess.run(
        [
            str(crypto),
            "dgst",
            "-sha256",
            "-sign",
            str(private),
            "-out",
            str(signature_path),
            str(message_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return (
        descriptor,
        message.decode() + "." + encoded(signature_path.read_bytes()),
        claims,
        private,
    )


def test_real_issuer_signature_authenticates_exact_supported_invocation(tmp_path):
    descriptor, token, claims, _ = signed_fixture(tmp_path)
    policy = load_identity_policy(descriptor=descriptor, repository="owner/repo")
    assert policy is not None
    identity = verify_oidc(token=token, policy=policy, now=1700000010)
    assert identity is not None, "a valid real signed fixture must authenticate"
    assert identity.run_id == int(claims["run_id"])
    assert identity.check_run_id == int(claims["check_run_id"])
    assert identity.run_attempt == 2
    assert identity.merge_sha == claims["sha"]
