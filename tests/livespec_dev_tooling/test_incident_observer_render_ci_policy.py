"""The role renders each installation's CI identity policy from its inventory entry alone."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from livespec_dev_tooling import incident_ci_identity_policy as policy_module
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "incident_observer"
    / "files"
    / "render_ci_identity_policy.py"
)
_PUBLISHER = "fleet/livespec-dev-tooling"
_SHA = "1" * 40


def script() -> ModuleType:
    assert _SCRIPT.is_file(), "the role ships files/render_ci_identity_policy.py"
    spec = importlib.util.spec_from_file_location("render_ci_identity_policy", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _jwks(*, keys) -> dict:
    return {"keys": keys}


def _argv(*, jwks: Path, crypto: Path, shas=(_SHA,)) -> list[str]:
    argv = [
        "--repository",
        "fleet/served",
        "--repository-id",
        "4242",
        "--owner-id",
        "77",
        "--audience",
        "livespec-incident-observer:fleet/served",
        "--publisher-repository",
        _PUBLISHER,
        "--jwks",
        str(jwks),
        "--crypto",
        str(crypto),
    ]
    for sha in shas:
        argv += ["--publisher-sha", sha]
    return argv


def test_the_rendered_policy_is_the_one_the_controller_loads(
    trusted, tmp_path, capsys, monkeypatch
):
    original, _, _, _, _ = trusted
    fixture = json.loads(Path(original["path"]).read_text())
    pinned = fixture["issuer_keys"][0]
    crypto = Path(fixture["crypto"]["path"])
    jwks = tmp_path / "jwks.json"
    jwks.write_text(
        json.dumps(
            _jwks(
                keys=[
                    {"kty": "RSA", "alg": "RS256", "use": "sig", **pinned, "x5t": "ignored"},
                    {"kty": "EC", "kid": "not-rsa", "crv": "P-256", "x": "a", "y": "b"},
                ]
            )
        )
    )
    module = script()
    assert module.main(argv=_argv(jwks=jwks, crypto=crypto)) == 0
    rendered = capsys.readouterr().out
    data = json.loads(rendered)
    assert data == {
        "schema": 1,
        "audience": "livespec-incident-observer:fleet/served",
        "subject": "repo:fleet/served:pull_request",
        "repository": "fleet/served",
        "repository_id": 4242,
        "repository_owner_id": 77,
        "approved_reusable_workflows": [
            {
                "ref": _PUBLISHER + "/.github/workflows/reusable-incident-ci-publish.yml@" + _SHA,
                "sha": _SHA,
            }
        ],
        "issuer_keys": [{"kid": pinned["kid"], "n": pinned["n"], "e": pinned["e"]}],
        "crypto": {"path": str(crypto), "sha256": hashlib.sha256(crypto.read_bytes()).hexdigest()},
    }
    # The controller's own loader accepts it as an installation policy.
    path = tmp_path / "ci-identity.json"
    path.write_text(rendered)
    path.chmod(0o600)
    monkeypatch.setattr(policy_module, "protected_path", lambda *, path: path is not None)
    loaded = policy_module.load_identity_policy(
        descriptor={"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        repository="fleet/served",
    )
    assert loaded is not None
    assert loaded.workflows == (
        (_PUBLISHER + "/.github/workflows/reusable-incident-ci-publish.yml@" + _SHA, _SHA),
    )


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"keys": []}, "no RSA signing key"),
        ({"keys": "x"}, "no RSA signing key"),
        ({}, "no RSA signing key"),
        ({"keys": [{"kty": "RSA", "kid": "k", "n": _b64(b"\x01" * 256)}]}, "no RSA signing key"),
    ],
)
def test_an_unusable_key_set_refuses_by_name(trusted, tmp_path, capsys, change, named):
    original, _, _, _, _ = trusted
    crypto = Path(json.loads(Path(original["path"]).read_text())["crypto"]["path"])
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(change))
    assert script().main(argv=_argv(jwks=jwks, crypto=crypto)) == 2
    assert named in capsys.readouterr().err


@pytest.mark.parametrize("shas", [(), ("not-a-sha",), ("A" * 40,)])
def test_a_publisher_commit_must_be_a_full_lowercase_sha(trusted, tmp_path, capsys, shas):
    original, _, _, _, _ = trusted
    fixture = json.loads(Path(original["path"]).read_text())
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(_jwks(keys=[{"kty": "RSA", **fixture["issuer_keys"][0]}])))
    crypto = Path(fixture["crypto"]["path"])
    assert script().main(argv=_argv(jwks=jwks, crypto=crypto, shas=shas)) == 2
    assert "publisher commit" in capsys.readouterr().err
