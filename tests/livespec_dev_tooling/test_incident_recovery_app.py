"""The recovery App credential fails closed by name and mints only a scoped write token."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livespec_runtime_budget.github_budget import GithubBudgetedClient, GithubBudgetResponse

from livespec_dev_tooling import _incident_recovery_signing as signing
from livespec_dev_tooling import incident_ci_identity_policy as policy_module
from livespec_dev_tooling import incident_recovery_app as app
from livespec_dev_tooling import incident_recovery_principal_service as principal_service
from livespec_dev_tooling.incident_forge_reads import ForgeReads
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

    monkeypatch.setattr(signing.subprocess, "run", run)
    assert signing.openssl_sign(message=b"header.claims", private_key="PEM\n") == b"signature"
    assert seen["argv"][0] == "/usr/bin/openssl"
    assert seen["input"] == b"header.claims"
    assert seen["key"] == "PEM\n"
    assert set(seen["env"]) == {"PATH", "HOME", "OPENSSL_CONF"}
    monkeypatch.setattr(
        signing.subprocess,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 1, stdout=b"x"),
    )
    assert signing.openssl_sign(message=b"m", private_key="PEM\n") == b""


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


def test_connect_mints_a_contents_read_token_when_asked():
    forge = Forge(
        **{
            _INSTALLATION: (200, {"id": 7}),
            _TOKENS: (201, {"token": "ghs_r", "permissions": {"contents": "read"}}),
        }
    )
    connected = RecoveryForge.connect(
        repository="owner/repo",
        credential=_CREDENTIAL,
        transport=forge,
        clock=lambda: 1_000_000.0,
        signer=lambda **_: b"sig",
        access="read",
    )
    assert isinstance(connected, RecoveryForge)
    assert forge.requests[1].value["permissions"] == {"contents": "read"}


@pytest.mark.parametrize(
    ("access", "granted"),
    [
        ("read", {"contents": "write"}),
        ("read", {"contents": "write", "metadata": "read"}),
        ("read", {"contents": "read", "actions": "read"}),
        ("write", {"contents": "read"}),
    ],
)
def test_a_token_reporting_another_grant_is_refused(access, granted):
    forge = Forge(
        **{
            _INSTALLATION: (200, {"id": 7}),
            _TOKENS: (201, {"token": "ghs_x", "permissions": granted}),
        }
    )
    refusal = RecoveryForge.connect(
        repository="owner/repo",
        credential=_CREDENTIAL,
        transport=forge,
        clock=lambda: 1_000_000.0,
        signer=lambda **_: b"sig",
        access=access,
    )
    assert isinstance(refusal, AppRefusal)
    assert refusal.code == "recovery-app-token-refused"
    assert f"contents-{access}" in refusal.detail


def test_a_revalidated_read_is_the_retained_body_at_status_200():
    answers = iter(
        [
            GithubBudgetResponse(
                status_code=200, headers={"ETag": "x"}, value={"id": 1}, primary_budget_spent=1
            ),
            GithubBudgetResponse(status_code=304, headers={}, value=None, primary_budget_spent=1),
        ]
    )
    client = GithubBudgetedClient(transport=lambda **_: next(answers), max_attempts=1)
    forge = RecoveryForge(repository="owner/repo", token="t", client=client)  # noqa: S106
    assert forge.request(method="GET", path="pulls/1") == (200, {"id": 1})
    assert forge.request(method="GET", path="pulls/1") == (200, {"id": 1})


def test_signing_that_outlives_its_ceiling_answers_no_signature(monkeypatch):
    monkeypatch.setattr(
        signing.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("openssl", 10))
    )
    assert signing.openssl_sign(message=b"m", private_key="PEM\n") == b""


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


# livespec-dev-tooling-gwzviw: the recovery App signs with the pinned program, digest included.
def _pin() -> SimpleNamespace:
    name = shutil.which("openssl")
    assert name is not None
    program = Path(name).resolve()
    return SimpleNamespace(
        crypto_path=program, crypto_sha256=hashlib.sha256(program.read_bytes()).hexdigest()
    )


def _spy(monkeypatch: pytest.MonkeyPatch, *, signature: bytes = b"signature") -> Mock:
    spy = Mock(side_effect=lambda argv, **_: subprocess.CompletedProcess(argv, 0, stdout=signature))
    monkeypatch.setattr(signing.subprocess, "run", spy)
    return spy


def test_the_pinned_program_check_is_the_one_ci_verification_rechecks(tmp_path: Path) -> None:
    pin = _pin()
    intact = policy_module.pinned_crypto_intact
    assert intact(path=pin.crypto_path, sha256=pin.crypto_sha256) is True
    assert intact(path=pin.crypto_path, sha256="0" * 64) is False
    assert intact(path=tmp_path / "missing", sha256=pin.crypto_sha256) is False
    assert intact(path=Path("openssl"), sha256=pin.crypto_sha256) is False
    plain = tmp_path / "plain"
    plain.write_bytes(b"not executable")
    plain.chmod(0o600)
    assert intact(path=plain, sha256=hashlib.sha256(b"not executable").hexdigest()) is False


def test_signing_runs_the_pinned_program_when_its_digest_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = _pin()
    spy = _spy(monkeypatch)
    signed = signing.openssl_sign(
        message=b"m", private_key="PEM\n", program=pin.crypto_path, sha256=pin.crypto_sha256
    )
    assert signed == b"signature"
    assert spy.call_args.args[0][:3] == [str(pin.crypto_path), "dgst", "-sha256"]


def test_signing_never_runs_a_program_whose_digest_is_not_the_pinned_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = _pin()
    spy = _spy(monkeypatch)
    signed = signing.openssl_sign(
        message=b"m", private_key="PEM\n", program=pin.crypto_path, sha256="0" * 64
    )
    assert signed == b""
    assert spy.call_count == 0


def test_a_program_replaced_while_it_signed_yields_no_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = _pin()
    _spy(monkeypatch)
    monkeypatch.setattr(signing, "pinned_crypto_intact", Mock(side_effect=[True, False]))
    signed = signing.openssl_sign(
        message=b"m", private_key="PEM\n", program=pin.crypto_path, sha256=pin.crypto_sha256
    )
    assert signed == b""


def test_an_installation_with_no_pin_keeps_the_fixed_system_signer() -> None:
    assert signing.pinned_signer(policy=None) is signing.openssl_sign


def test_an_installed_pin_makes_the_signer_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    pin = _pin()
    spy = _spy(monkeypatch)
    assert signing.pinned_signer(policy=pin)(message=b"m", private_key="PEM\n") == b"signature"
    assert spy.call_args.args[0][0] == str(pin.crypto_path)
    spy.reset_mock()
    wrong = SimpleNamespace(crypto_path=pin.crypto_path, crypto_sha256="0" * 64)
    assert signing.pinned_signer(policy=wrong)(message=b"m", private_key="PEM\n") == b""
    assert spy.call_count == 0


@pytest.mark.parametrize("pinned", [True, False])
def test_both_connectors_mint_their_token_with_the_installations_signer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, pinned: bool
) -> None:
    pin = _pin() if pinned else None
    credential = tmp_path / app.RECOVERY_APP_CREDENTIAL
    credential.write_text(json.dumps({"app_id": "7", "private_key": _SINGLE_LINE}))
    credential.chmod(0o600)
    installation = SimpleNamespace(
        config=tmp_path / "controller.json", repository="owner/repo", ci_identity_policy=pin
    )
    connect = Mock(return_value=Mock(repository="owner/repo"))
    monkeypatch.setattr(RecoveryForge, "connect", connect)
    ForgeReads.installed(installation=installation).connect()
    principal_service._connector(installation=installation, config=installation.config)()  # noqa: SLF001
    assert connect.call_count == 2
    for call in connect.call_args_list:
        signer = call.kwargs["signer"]
        assert (signer is signing.openssl_sign) is (not pinned)
        if pin is not None:
            assert signer.func is signing.openssl_sign
            assert signer.keywords == {"program": pin.crypto_path, "sha256": pin.crypto_sha256}
