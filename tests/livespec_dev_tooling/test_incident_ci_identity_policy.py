"""Optional pinned CI trust fails closed without disabling existing recovery."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_identity_policy as policy_module
from livespec_dev_tooling.incident_ci_jws import verify_ci_signature
from tests.livespec_dev_tooling import test_incident_controller_installation as installation_tests
from tests.livespec_dev_tooling.test_incident_ci_oidc import signed_fixture

host = installation_tests.host

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


@cache
def signing_material(root):
    root.mkdir(mode=0o700)
    return signed_fixture(root)


@pytest.fixture
def trusted(tmp_path, tmp_path_factory):
    original, token, claims, private = signing_material(
        tmp_path_factory.getbasetemp() / "ci-signing-template"
    )
    path = tmp_path / "ci-identity.json"
    path.write_bytes(Path(original["path"]).read_bytes())
    path.chmod(0o600)
    key = tmp_path / "private.pem"
    key.write_bytes(private.read_bytes())
    key.chmod(0o600)
    descriptor = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    policy = policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo")
    assert policy is not None
    return descriptor, policy, token, claims.copy(), key


@pytest.mark.parametrize(
    "descriptor",
    [None, [], {}, {"path": "relative", "sha256": "x"}, {"path": 1, "sha256": "0" * 64}],
)
def test_invalid_optional_descriptors_are_unavailable(descriptor):
    assert (
        policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo") is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"extra": True},
        {"repository": "other/repo"},
        {"repository_id": True},
        {"repository_owner_id": 0},
        {"audience": "\n"},
        {"approved_reusable_workflows": []},
        {"approved_reusable_workflows": [None]},
        {
            "approved_reusable_workflows": [
                {"ref": "owner/provider/.github/workflows/check.yml@master", "sha": "f" * 40}
            ]
        },
        {"issuer_keys": []},
        {"issuer_keys": [None]},
        {"issuer_keys": [{"kid": "key", "n": "AA", "e": "Ag"}]},
        {"crypto": []},
        {"crypto": {"path": "relative", "sha256": "0" * 64}},
        {"crypto": {"path": "/unapproved/program", "sha256": "0" * 64}},
    ],
)
def test_malformed_policy_is_not_trust(trusted, change):
    descriptor, policy, *_ = trusted
    data = json.loads(policy.path.read_bytes()) | change
    policy.path.write_text(json.dumps(data))
    descriptor["sha256"] = hashlib.sha256(policy.path.read_bytes()).hexdigest()
    assert (
        policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo") is None
    )


def test_key_and_workflow_duplicates_are_rejected(trusted):
    descriptor, policy, *_ = trusted
    original = json.loads(policy.path.read_bytes())
    for field in ("issuer_keys", "approved_reusable_workflows"):
        data = original | {field: original[field] * 2}
        policy.path.write_text(json.dumps(data))
        descriptor["sha256"] = hashlib.sha256(policy.path.read_bytes()).hexdigest()
        assert (
            policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo")
            is None
        )


def test_integrity_modes_symlinks_missing_crypto_and_failed_reads(trusted, tmp_path, monkeypatch):
    descriptor, policy, *_ = trusted
    assert policy_module.identity_policy_intact(policy=policy)
    assert not policy_module.protected_identity_path(path=Path("relative"))
    assert not policy_module.protected_identity_path(path=tmp_path / "absent")
    link = tmp_path / "policy-link"
    link.symlink_to(policy.path)
    assert policy_module.protected_identity_path(path=link)
    policy.path.chmod(0o644)
    assert not policy_module.identity_policy_intact(policy=policy)
    assert (
        policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo") is None
    )
    policy.path.chmod(0o600)
    assert not policy_module.identity_policy_intact(
        policy=replace(policy, crypto_path=tmp_path / "missing")
    )
    assert not policy_module.identity_policy_intact(policy=replace(policy, crypto_sha256="0" * 64))
    policy.path.write_text("tampered")
    assert not policy_module.identity_policy_intact(policy=policy)
    assert (
        policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo") is None
    )

    def unavailable(path, *_args, **_kwargs):
        assert path == policy.path
        raise OSError("controlled unavailable")

    monkeypatch.setattr(Path, "stat", unavailable)
    assert not policy_module.identity_policy_intact(policy=policy)
    assert not policy_module.protected_identity_path(path=policy.path)


def test_foreign_symlink_and_writable_ancestor_refuse(trusted, tmp_path, monkeypatch):
    _, policy, *_ = trusted
    folder = tmp_path / "unsafe"
    folder.mkdir(mode=0o777)
    folder.chmod(0o777)
    link = folder / "link"
    link.symlink_to(policy.path)
    assert not policy_module.protected_identity_path(path=link)
    folder.chmod(0o700)
    original = Path.lstat

    def foreign(path, *args, **_kwargs):
        info = original(path, *args, **_kwargs)
        fields = list(info)
        assert path == link
        fields[4] = os.geteuid() + 100
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "lstat", foreign)
    assert not policy_module.protected_identity_path(path=link)


def test_signature_unknown_key_bad_size_failure_and_timeout(trusted, monkeypatch):
    _, policy, *_ = trusted
    assert not verify_ci_signature(policy=policy, kid="rotated", message=b"x", signature=b"x")
    assert not verify_ci_signature(policy=policy, kid="fixture-key", message=b"x", signature=b"x")

    def timeout(*args, **_kwargs):
        assert _kwargs["stdout"] == subprocess.DEVNULL
        assert _kwargs["stderr"] == subprocess.DEVNULL
        assert _kwargs["env"]["OPENSSL_CONF"] == "/dev/null"
        assert "OPENSSL_MODULES" not in _kwargs["env"]
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert not verify_ci_signature(
        policy=policy, kid="fixture-key", message=b"x", signature=b"x" * 256
    )
    policy.path.unlink()
    assert not verify_ci_signature(
        policy=policy, kid="fixture-key", message=b"x", signature=b"x" * 256
    )


def test_optional_policy_loads_without_extending_mandatory_files(host):
    root, _, manifest, write = host
    descriptor, *_ = signed_fixture(root)
    manifest["ci_identity_policy"] = descriptor
    settings = policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo")
    assert settings is not None
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

    loaded = ControllerInstallation.load(config=write())
    assert loaded is not None and loaded.ci_identity_policy == settings
    for value in (None, {}, descriptor | {"sha256": "0" * 64}):
        manifest["ci_identity_policy"] = value
        loaded = ControllerInstallation.load(config=write())
        assert loaded is not None and loaded.ci_identity_policy is None


def test_optional_loader_and_integrity_io_errors_are_unavailable(trusted, monkeypatch):
    descriptor, policy, *_ = trusted
    policy.path.write_text("{")
    descriptor["sha256"] = hashlib.sha256(policy.path.read_bytes()).hexdigest()
    assert (
        policy_module.load_identity_policy(descriptor=descriptor, repository="owner/repo") is None
    )

    def unavailable(path):
        assert path == policy.path
        raise OSError("controlled read failure")

    monkeypatch.setattr(Path, "read_bytes", unavailable)
    assert not policy_module.identity_policy_intact(policy=policy)


def test_a_pinned_program_that_cannot_be_read_is_not_intact(tmp_path, monkeypatch):
    program = tmp_path / "program"
    program.write_bytes(b"pinned")
    program.chmod(0o700)
    digest = hashlib.sha256(b"pinned").hexdigest()
    assert policy_module.pinned_crypto_intact(path=program, sha256=digest)

    def unreadable(_self):
        raise OSError("controlled unreadable")

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    assert not policy_module.pinned_crypto_intact(path=program, sha256=digest)
