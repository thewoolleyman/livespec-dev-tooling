"""The recovery App credential fails closed by name and mints only a scoped write token."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest
from livespec_runtime_budget.github_budget import GithubBudgetResponse

from livespec_dev_tooling import incident_recovery_app as app
from livespec_dev_tooling.incident_recovery_app import (
    AppRefusal,
    RecoveryAppCredential,
    RecoveryForge,
)

_BODY = "".join(chr(65 + index % 26) for index in range(130))
_SINGLE_LINE = f"-----BEGIN RSA PRIVATE KEY----- {_BODY} -----END RSA PRIVATE KEY-----"


def _write(tmp_path, value, mode=0o600):
    path = tmp_path / app.RECOVERY_APP_CREDENTIAL
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    path.chmod(mode)
    return path


def test_absent_credential_is_a_named_refusal(tmp_path):
    refusal = RecoveryAppCredential.load(path=tmp_path / app.RECOVERY_APP_CREDENTIAL)
    assert refusal == AppRefusal(
        code="recovery-app-credential-absent",
        detail=f"no projected recovery App credential at {tmp_path / 'recovery-app.json'}",
    )


def test_group_readable_or_linked_credential_is_unprotected(tmp_path):
    path = _write(tmp_path, {"app_id": "1", "private_key": _SINGLE_LINE}, mode=0o640)
    assert RecoveryAppCredential.load(path=path).code == "recovery-app-credential-unprotected"
    link = tmp_path / "linked.json"
    path.chmod(0o600)
    link.symlink_to(path)
    assert RecoveryAppCredential.load(path=link).code == "recovery-app-credential-unprotected"


@pytest.mark.parametrize(
    "value",
    [
        "{not json",
        "[]",
        {"app_id": "1"},
        {"app_id": 1, "private_key": _SINGLE_LINE},
        {"app_id": "app", "private_key": _SINGLE_LINE},
        {"app_id": "1", "private_key": "not a key"},
        {
            "app_id": "1",
            "private_key": "-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----",
        },
        {
            "app_id": "1",
            "private_key": "-----BEGIN RSA PRIVATE KEY----------END RSA PRIVATE KEY-----",
        },
        {"app_id": "1", "private_key": _SINGLE_LINE, "extra": True},
    ],
)
def test_malformed_credential_is_a_named_refusal(tmp_path, value):
    refusal = RecoveryAppCredential.load(path=_write(tmp_path, value))
    assert refusal.code == "recovery-app-credential-malformed"


def test_single_line_projected_key_is_rewrapped_and_never_repr(tmp_path):
    credential = RecoveryAppCredential.load(
        path=_write(tmp_path, {"app_id": "12345", "private_key": _SINGLE_LINE})
    )
    lines = credential.private_key.splitlines()
    assert lines[0] == "-----BEGIN RSA PRIVATE KEY-----"
    assert lines[-1] == "-----END RSA PRIVATE KEY-----"
    assert "".join(lines[1:-1]) == _BODY
    assert all(len(line) <= 64 for line in lines)
    assert _BODY not in repr(credential)


def test_signing_uses_only_the_fixed_system_crypto_and_a_private_key_file(monkeypatch):
    seen = {}

    def run(argv, *, input, env, **_):
        seen.update(argv=argv, input=input, env=env)
        key = argv[argv.index("-sign") + 1]
        seen["key"] = Path(key).read_text()
        return subprocess.CompletedProcess(argv, 0, stdout=b"signature")

    monkeypatch.setattr(app.subprocess, "run", run)
    assert app.openssl_sign(message=b"header.claims", private_key="PEM\n") == b"signature"
    assert seen["argv"][0] == "/usr/bin/openssl"
    assert seen["input"] == b"header.claims"
    assert seen["key"] == "PEM\n"
    assert set(seen["env"]) == {"PATH", "HOME", "OPENSSL_CONF"}
    monkeypatch.setattr(
        app.subprocess, "run", lambda argv, **_: subprocess.CompletedProcess(argv, 1, stdout=b"x")
    )
    assert app.openssl_sign(message=b"m", private_key="PEM\n") == b""


class Forge:
    def __init__(self, **answers):
        self.answers, self.requests = answers, []

    def __call__(self, *, request):
        self.requests.append(request)
        status, value = self.answers.get(request.resource, (404, None))
        headers = {}
        if status == 403:
            headers = {
                "x-ratelimit-limit": "5000",
                "x-ratelimit-remaining": "0",
                "x-ratelimit-used": "5000",
                "x-ratelimit-reset": "1",
                "x-ratelimit-resource": "core",
            }
        return GithubBudgetResponse(
            status_code=status, headers=headers, value=value, primary_budget_spent=1
        )


_CREDENTIAL = RecoveryAppCredential(app_id="12345", private_key="PEM")
_INSTALLATION = "repos/owner/repo/installation"
_TOKENS = "app/installations/7/access_tokens"


def _connect(forge, *, signer=lambda **_: b"sig"):
    return RecoveryForge.connect(
        repository="owner/repo",
        credential=_CREDENTIAL,
        transport=forge,
        clock=lambda: 1_000_000.0,
        signer=signer,
    )


def test_connect_mints_a_contents_write_token_for_exactly_one_repository():
    forge = Forge(
        **{
            _INSTALLATION: (200, {"id": 7}),
            _TOKENS: (201, {"token": "ghs_x", "permissions": {"contents": "write"}}),
            "repos/owner/repo/git/ref/heads/master": (200, {"object": {"sha": "a" * 40}}),
        }
    )
    connected = _connect(forge)
    assert isinstance(connected, RecoveryForge)
    assert "ghs_x" not in repr(connected)
    jwt = forge.requests[0].headers["Authorization"].removeprefix("Bearer ")
    header, claims, signature = jwt.split(".")
    padded = claims + "=" * (-len(claims) % 4)
    assert json.loads(base64.urlsafe_b64decode(padded)) == {
        "iat": 999_940,
        "exp": 1_000_540,
        "iss": "12345",
    }
    assert base64.urlsafe_b64decode(signature + "==") == b"sig"
    assert header
    assert forge.requests[1].value == {
        "repositories": ["repo"],
        "permissions": {"contents": "write"},
    }
    assert connected.request(method="GET", path="git/ref/heads/master") == (
        200,
        {"object": {"sha": "a" * 40}},
    )
    assert forge.requests[2].headers["Authorization"] == "Bearer ghs_x"


@pytest.mark.parametrize(
    ("answers", "signer", "code"),
    [
        ({}, lambda **_: b"", "recovery-app-signing-unavailable"),
        ({}, lambda **_: b"sig", "recovery-app-not-installed"),
        ({_INSTALLATION: (200, {"id": "7"})}, lambda **_: b"sig", "recovery-app-not-installed"),
        ({_INSTALLATION: (200, [])}, lambda **_: b"sig", "recovery-app-not-installed"),
        ({_INSTALLATION: (403, None)}, lambda **_: b"sig", "recovery-app-not-installed"),
        ({_INSTALLATION: (200, {"id": 7})}, lambda **_: b"sig", "recovery-app-token-refused"),
        (
            {
                _INSTALLATION: (200, {"id": 7}),
                _TOKENS: (201, {"token": "t", "permissions": {"contents": "read"}}),
            },
            lambda **_: b"sig",
            "recovery-app-token-refused",
        ),
        (
            {_INSTALLATION: (200, {"id": 7}), _TOKENS: (201, ["t"])},
            lambda **_: b"sig",
            "recovery-app-token-refused",
        ),
        (
            {
                _INSTALLATION: (200, {"id": 7}),
                _TOKENS: (201, {"token": "", "permissions": {"contents": "write"}}),
            },
            lambda **_: b"sig",
            "recovery-app-token-refused",
        ),
    ],
)
def test_connect_refuses_by_name_when_no_scoped_token_exists(answers, signer, code):
    assert _connect(Forge(**answers), signer=signer).code == code


class _Answer(io.BytesIO):
    status, headers = 200, {"etag": "x"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _request():
    return app.GithubBudgetRequest(
        method="POST", resource="repos/owner/repo/git/trees", headers={"A": "b"}, value={"k": 1}
    )


def test_transport_posts_json_to_the_fixed_origin(monkeypatch):
    seen = []

    def urlopen(outgoing, *, timeout):
        seen.append((outgoing, timeout))
        return _Answer(b'{"sha": "t"}')

    monkeypatch.setattr(app.urllib.request, "urlopen", urlopen)
    response = app.urllib_transport(request=_request())
    assert (response.status_code, response.value) == (200, {"sha": "t"})
    outgoing, timeout = seen[0]
    assert outgoing.full_url == app.github_api_url(path="repos/owner/repo/git/trees")
    assert outgoing.data == b'{"k": 1}'
    assert outgoing.get_method() == "POST"
    assert timeout == 10.0


@pytest.mark.parametrize("failure", ["http", "network", "garbled", "empty"])
def test_transport_reports_refusals_and_unobserved_answers(monkeypatch, failure):
    def urlopen(outgoing, *, timeout):
        del timeout
        if failure == "http":
            raise urllib.error.HTTPError(
                outgoing.full_url, 422, "Unprocessable", {}, io.BytesIO(b'{"message": "no"}')
            )
        if failure == "network":
            raise urllib.error.URLError("unreachable")
        return _Answer(b"{garbled" if failure == "garbled" else b"")

    monkeypatch.setattr(app.urllib.request, "urlopen", urlopen)
    response = app.urllib_transport(request=_request())
    expected = {
        "http": (422, {"message": "no"}),
        "network": (0, None),
        "garbled": (200, None),
        "empty": (200, None),
    }
    assert (response.status_code, response.value) == expected[failure]
