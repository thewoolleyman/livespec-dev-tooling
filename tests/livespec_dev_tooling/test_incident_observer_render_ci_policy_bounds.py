"""The policy renderer never writes a key set the controller's loader would refuse.

livespec-dev-tooling-bqnzcm.4, grade fix 2 on livespec-dev-tooling#4496. The loader
refuses a WHOLE policy for one key outside its bounds (2048-8192-bit odd modulus,
an odd exponent in [3, 2**32), canonical base64url, a printable kid, unique kids,
at most 16 keys), which would leave the installation with no identity at all. So the
renderer drops each JWKS row outside those bounds, naming its kid and why, drops
every row of a kid the set repeats, and refuses when no key or more than 16 keys
survive. Whatever it renders, the loader accepts.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_identity_policy as policy_module
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests
from tests.livespec_dev_tooling import test_incident_observer_render_ci_policy as render_tests

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _modulus(*, seed: int, bits: int = 2048, odd: bool = True) -> bytes:
    size = bits // 8
    body = bytearray(hashlib.shake_256(seed.to_bytes(4, "big")).digest(size))
    body[0] |= 0x80
    body[-1] = (body[-1] | 1) if odd else (body[-1] & 0xFE)
    return bytes(body)


def _key(*, kid: str, seed: int, **changes) -> dict[str, str]:
    return {"kty": "RSA", "kid": kid, "n": _b64(_modulus(seed=seed)), "e": "AQAB"} | changes


def _render(trusted, tmp_path, capsys, keys):
    original, _, _, _, _ = trusted
    crypto = Path(json.loads(Path(original["path"]).read_text())["crypto"]["path"])
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": keys}))
    module = render_tests.script()
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
        "fleet/livespec-dev-tooling",
        "--publisher-sha",
        "1" * 40,
        "--jwks",
        str(jwks),
        "--crypto",
        str(crypto),
    ]
    code = module.main(argv=argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _loads(*, rendered: str, tmp_path: Path, monkeypatch) -> bool:
    path = tmp_path / "ci-identity.json"
    path.write_text(rendered)
    path.chmod(0o600)
    monkeypatch.setattr(policy_module, "protected_path", lambda *, path: path is not None)
    descriptor = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return (
        policy_module.load_identity_policy(descriptor=descriptor, repository="fleet/served")
        is not None
    )


_BAD = [
    (_key(kid="short", seed=1, n=_b64(_modulus(seed=1, bits=1024))), "short: modulus"),
    (_key(kid="even", seed=2, n=_b64(_modulus(seed=2, odd=False))), "even: modulus"),
    (_key(kid="huge", seed=3, n=_b64(_modulus(seed=3, bits=8200))), "huge: modulus"),
    (_key(kid="lead", seed=4, n=_b64(b"\x00" + _modulus(seed=4))), "lead: modulus"),
    (_key(kid="e-two", seed=5, e=_b64(b"\x02")), "e-two: exponent"),
    (_key(kid="e-even", seed=6, e=_b64((65536).to_bytes(3, "big"))), "e-even: exponent"),
    (_key(kid="e-big", seed=7, e=_b64((2**32 + 1).to_bytes(5, "big"))), "e-big: exponent"),
    (_key(kid="pad", seed=8, n=_b64(_modulus(seed=8)) + "="), "pad: modulus"),
    (_key(kid="tab\tkid", seed=9), "with an unprintable or oversized kid"),
    (_key(kid="k" * 257, seed=10), "with an unprintable or oversized kid"),
]


def test_each_key_outside_the_loaders_bounds_is_dropped_by_name(
    trusted, tmp_path, capsys, monkeypatch
) -> None:
    good = _key(kid="good", seed=100)
    code, out, err = _render(trusted, tmp_path, capsys, [good] + [row for row, _ in _BAD])
    assert code == 0, err
    assert [k["kid"] for k in json.loads(out)["issuer_keys"]] == ["good"]
    for _, named in _BAD:
        assert "dropped issuer key " + named in err, named
    assert _loads(rendered=out, tmp_path=tmp_path, monkeypatch=monkeypatch)


def test_a_repeated_key_id_drops_every_row_that_carries_it(
    trusted, tmp_path, capsys, monkeypatch
) -> None:
    rows = [_key(kid="twice", seed=1), _key(kid="twice", seed=2), _key(kid="once", seed=3)]
    code, out, err = _render(trusted, tmp_path, capsys, rows)
    assert code == 0, err
    assert [k["kid"] for k in json.loads(out)["issuer_keys"]] == ["once"]
    assert "dropped issuer key twice: the key set repeats this key id" in err
    assert _loads(rendered=out, tmp_path=tmp_path, monkeypatch=monkeypatch)


@pytest.mark.parametrize(
    ("rows", "named"),
    [
        ([row for row, _ in _BAD], "no RSA signing key"),
        ([_key(kid=f"k{i}", seed=i) for i in range(17)], "more than 16 usable"),
    ],
)
def test_no_surviving_key_or_too_many_refuses_by_name(trusted, tmp_path, capsys, rows, named):
    code, out, err = _render(trusted, tmp_path, capsys, rows)
    assert (code, out) == (2, "")
    assert named in err


def test_sixteen_good_keys_render_a_policy_the_loader_accepts(
    trusted, tmp_path, capsys, monkeypatch
) -> None:
    code, out, err = _render(
        trusted, tmp_path, capsys, [_key(kid=f"k{i}", seed=i) for i in range(16)]
    )
    assert code == 0, err
    assert len(json.loads(out)["issuer_keys"]) == 16
    assert _loads(rendered=out, tmp_path=tmp_path, monkeypatch=monkeypatch)
