"""Every caller of the incident authority reaches it through one client.

livespec-dev-tooling-iezdmk. Five clients carried five ceilings (30, 45, 45, 120 and
600 s) and four different sets of reply checks, so a slow but sound call was refused
in one place and accepted in another, and only the hook refused a missing proof flag.
The client owns the ceiling and the reply checks; each caller keeps only its own
trust boundary (which command it runs) and its own meaning of the result.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling import (
    _incident_original_run_ports as operator_ports,
)
from livespec_dev_tooling import (
    incident_authority_client as client,
)
from livespec_dev_tooling import (
    incident_hook_process as hook,
)
from livespec_dev_tooling import (
    incident_observer_provenance as observer_provenance,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-iezdmk
_HEAD = "b" * 40


def _dump(value: object) -> str:
    return json.dumps(value)


def _reply(*, action: str = "read-current", **changes: object) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": action == "read-current",
        "normal_factory_proof": False,
        "result": {"marker": "ok"},
    }
    reply.update(changes)
    return reply


def _without(*, reply: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in reply.items() if name != key}


def _run_returning(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
    error: BaseException | None = None,
) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append({"argv": argv, **kwargs})
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)
    return seen


def _call(*, action: str = "read-current") -> Any:
    return client.call_authority(
        command=["reader", "--flag"],
        action=action,
        flags={"repo": "/governed", "generation": 3},
        cwd=Path("/governed"),
        env={"HOME": "/home/operator"},
    )


def test_a_verified_reply_returns_its_result_and_runs_under_the_one_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _run_returning(monkeypatch=monkeypatch, stdout=_dump(_reply()))
    checked = _call()
    assert is_successful(checked)
    assert checked.unwrap() == {"marker": "ok"}
    assert seen[0]["argv"] == [
        "reader",
        "--flag",
        "read-current",
        "--repo",
        "/governed",
        "--generation",
        "3",
    ]
    assert seen[0]["timeout"] == client.AUTHORITY_CALL_CEILING_SECONDS == 600
    assert seen[0]["cwd"] == Path("/governed")
    assert seen[0]["env"] == {"HOME": "/home/operator"}
    assert "shell" not in seen[0]


def test_a_history_reply_is_verified_when_it_authorizes_no_current_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, stdout=_dump(_reply(action="read-history")))
    assert is_successful(_call(action="read-history"))


def test_the_wrapper_command_names_the_registered_plugin_script() -> None:
    assert client.registered_authority_command(plugin_root=Path("/registered")) == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "python3",
        "/registered/scripts/bin/incident_authority.py",
    ]


_DUPLICATE = _dump(_reply()).replace('"schema": 1', '"schema": 1, "schema": 1')
_REFUSALS: list[tuple[str, dict[str, Any], str]] = [
    ("exit", {"stdout": _dump(_reply()), "returncode": 1}, "incident-authority-exit"),
    (
        "one-password-500",
        {"stdout": "", "returncode": 1, "stderr": "[ERROR] (500) Internal Server Error"},
        "incident-authority-exit",
    ),
    ("not-json", {"stdout": "not json"}, "incident-authority-malformed-reply"),
    ("too-deep", {"stdout": "[" * 100_000}, "incident-authority-malformed-reply"),
    ("array", {"stdout": "[]"}, "incident-authority-malformed-reply"),
    ("duplicate", {"stdout": _DUPLICATE}, "incident-authority-duplicate-keys"),
    ("schema-bool", {"stdout": _dump(_reply(schema=True))}, "incident-authority-schema"),
    ("schema-2", {"stdout": _dump(_reply(schema=2))}, "incident-authority-schema"),
    ("schema-text", {"stdout": _dump(_reply(schema="1"))}, "incident-authority-schema"),
    (
        "proof-missing",
        {"stdout": _dump(_without(reply=_reply(), key="normal_factory_proof"))},
        "incident-authority-proof-flag",
    ),
    (
        "proof-true",
        {"stdout": _dump(_reply(normal_factory_proof=True))},
        "incident-authority-proof-flag",
    ),
    (
        "proof-text",
        {"stdout": _dump(_reply(normal_factory_proof="false"))},
        "incident-authority-proof-flag",
    ),
    (
        "not-verified",
        {"stdout": _dump(_reply(status="refused"))},
        "incident-authority-not-verified",
    ),
    (
        "current-without-authority",
        {"stdout": _dump(_reply(authorizes_current_effects=False))},
        "incident-authority-wrong-kind",
    ),
    (
        "authority-flag-missing",
        {"stdout": _dump(_without(reply=_reply(), key="authorizes_current_effects"))},
        "incident-authority-wrong-kind",
    ),
    (
        "result-not-an-object",
        {"stdout": _dump(_reply(result=[]))},
        "incident-authority-malformed-result",
    ),
]


@pytest.mark.parametrize(("reply", "code"), [pytest.param(r, c, id=i) for i, r, c in _REFUSALS])
def test_a_bad_reply_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, reply: dict[str, Any], code: str
) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, **reply)
    refused = _call()
    assert not is_successful(refused)
    assert refused.failure().code == code
    assert refused.failure().canonical is False


def test_history_never_authorizes_current_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _run_returning(
        monkeypatch=monkeypatch,
        stdout=_dump(_reply(action="read-history", authorizes_current_effects=True)),
    )
    assert _call(action="read-history").failure().code == "incident-authority-wrong-kind"


def test_a_call_past_the_ceiling_is_refused_naming_the_action_and_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, error=subprocess.TimeoutExpired("reader", 600))
    refused = _call(action="read-local-gates").failure()
    assert refused.code == "incident-authority-timeout"
    assert "read-local-gates" in refused.detail
    assert f"{client.AUTHORITY_CALL_CEILING_SECONDS} s" in refused.detail


def test_a_reader_that_cannot_start_is_refused_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, error=OSError("no such reader"))
    refused = _call().failure()
    assert refused.code == "incident-authority-unavailable"
    assert "no such reader" in refused.detail


def _canonical(*, code: object = "incident-authority-missing", detail: object = "no chain") -> str:
    return _dump(
        _reply(
            status="refused",
            authorizes_current_effects=False,
            result={"code": code, "detail": detail},
        )
    )


def test_a_canonical_refusal_keeps_its_own_code_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, stdout=_canonical(), returncode=78)
    refused = _call().failure()
    assert (refused.code, refused.detail, refused.canonical) == (
        "incident-authority-missing",
        "no chain",
        True,
    )


@pytest.mark.parametrize(
    "stdout",
    [
        _canonical(code=False),
        _canonical(code=""),
        _canonical(detail=[]),
        _dump(_reply()),
        _dump(_reply(status="refused", authorizes_current_effects=True)),
        _dump(_without(reply=json.loads(_canonical()), key="authorizes_current_effects")),
        _dump({**json.loads(_canonical()), "status": "verified"}),
        _dump({**json.loads(_canonical()), "status": "unavailable"}),
        _dump(_without(reply=json.loads(_canonical()), key="status")),
    ],
)
def test_exit_78_requires_an_actual_named_refusal(
    monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    _ = _run_returning(monkeypatch=monkeypatch, stdout=stdout, returncode=78)
    refused = _call().failure()
    assert refused.code == "incident-authority-malformed-refusal"
    assert refused.canonical is False


# ---- Every caller reaches the client: one ceiling and one set of reply checks. ----

_ATTEMPT: dict[str, Any] = {
    "repository": "owner/repo",
    "item_id": "incident-1",
    "attempt_id": "repair-1",
    "phase": "repair",
    "operation_id": "operation-2",
    "generation": 2,
    "owner": "owner",
    "base": "e" * 40,
    "head": "c" * 40,
    "pr_number": 55,
    "landed_commits": [],
    "landed_trees": [],
    "original_paths": ["module.py"],
    "deferred_work": [],
    "repayment_required": True,
}
_HISTORY_QUERY: dict[str, Any] = {
    "repository": "owner/repo",
    "item_id": "incident-1",
    "attempt_id": "attempt-1",
    "phase": "repair",
    "operation_id": "operation-2",
    "generation": 2,
    "owner": "operator",
    "base": "a" * 40,
    "head": _HEAD,
    "pr_number": 7,
    "commit_sha": _HEAD,
    "tree_sha": "c" * 40,
}
_HOOK_QUERY: dict[str, Any] = {
    "repository": "owner/repo",
    "item": "incident",
    "attempt": "attempt",
    "phase": "repair",
    "operation": "operation",
    "generation": 1,
    "owner": "operator",
}


def _history_reply() -> dict[str, Any]:
    attempt = {k: v for k, v in _HISTORY_QUERY.items() if k not in {"commit_sha", "tree_sha"}}
    attempt |= {
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["livespec_dev_tooling/repair.py"],
        "deferred_work": [],
        "repayment_required": True,
    }
    result = {"attempt": attempt, "committed_token_id": "token-1", "current_token_id": "token-2"}
    return _reply(action="read-history", result=result)


def _hook_caller(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, Callable[[], bool]]:
    monkeypatch.setattr(hook, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(hook, "registered_plugin_root", lambda **_kwargs: tmp_path)

    def refused() -> bool:
        try:
            _ = hook.invoke_authority(repo=tmp_path, query=_HOOK_QUERY, action="read-current")
        except hook.HookRefusalError:
            return True
        return False

    return _dump(_reply(result={"is_current": True})), refused


def _observer_reader_caller(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, Callable[[], bool]]:
    _ = monkeypatch
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        phase="repair",
        operation_id="operation-2",
        generation=2,
        owner="owner",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("ci-green",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(_ATTEMPT, sort_keys=True, separators=(",", ":")).encode(),
    )
    reader = CurrentAuthorityReader(
        command=("installed-reader",),
        repo=tmp_path,
        release="v1.2.3",
        installed_reader_approved=lambda _release, _command: True,
    )
    good = _reply(result={"is_current": True, "attempt": _ATTEMPT})
    return _dump(good), lambda: not reader(arm)


def _operator_caller(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, Callable[[], bool]]:
    _ = monkeypatch
    _ = (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant\n")
    installation = SimpleNamespace(
        config=tmp_path / "controller.json", repo=tmp_path, reader=("installed-reader",)
    )
    authority = operator_ports.installed_ports(installation=installation).canonical.authority

    def refused() -> bool:
        try:
            _ = authority("read-current", {"item": "incident-1"}, {})
        except ValueError:
            return True
        return False

    return _dump(_reply()), refused


def _observer_provenance_caller(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, Callable[[], bool]]:
    _ = monkeypatch
    settings = SimpleNamespace(repo=tmp_path, reader=("installed-reader",))

    def refused() -> bool:
        answer = observer_provenance.ObserverProvenance(installation=settings).execute(
            path="/provenance", payload=dict(_HISTORY_QUERY)
        )
        return answer["status"] == "refused"

    return _dump(_history_reply()), refused


_CALLERS = {
    "hook": _hook_caller,
    "observer-reader": _observer_reader_caller,
    "operator": _operator_caller,
    "observer-provenance": _observer_provenance_caller,
}


@pytest.mark.parametrize("caller", _CALLERS)
def test_every_caller_accepts_a_sound_reply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caller: str
) -> None:
    good, refused = _CALLERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path)
    _ = _run_returning(monkeypatch=monkeypatch, stdout=good)
    assert refused() is False


@pytest.mark.parametrize("caller", _CALLERS)
def test_every_caller_waits_the_one_ceiling_and_refuses_past_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caller: str
) -> None:
    _, refused = _CALLERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path)
    seen = _run_returning(monkeypatch=monkeypatch, error=subprocess.TimeoutExpired("reader", 1))
    assert refused() is True
    assert [call["timeout"] for call in seen] == [client.AUTHORITY_CALL_CEILING_SECONDS]


def _duplicate_keys(good: str) -> str:
    return good.replace('"schema": 1', '"schema": 1, "schema": 1')


def _schema_true(good: str) -> str:
    return _dump({**json.loads(good), "schema": True})


def _deeply_nested(good: str) -> str:
    return "[" * 100_000 + good


def _proof_missing(good: str) -> str:
    return _dump(_without(reply=json.loads(good), key="normal_factory_proof"))


@pytest.mark.parametrize("caller", _CALLERS)
@pytest.mark.parametrize(
    "mutate",
    [_duplicate_keys, _schema_true, _proof_missing, _deeply_nested],
    ids=lambda f: f.__name__,
)
def test_every_caller_refuses_what_the_client_refuses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caller: str,
    mutate: Callable[[str], str],
) -> None:
    good, refused = _CALLERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path)
    _ = _run_returning(monkeypatch=monkeypatch, stdout=mutate(good))
    assert refused() is True


@pytest.mark.parametrize("caller", _CALLERS)
def test_every_caller_refuses_a_non_zero_exit_even_with_a_sound_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caller: str
) -> None:
    good, refused = _CALLERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path)
    _ = _run_returning(monkeypatch=monkeypatch, stdout=good, returncode=1)
    assert refused() is True


@pytest.mark.parametrize("caller", _CALLERS)
def test_a_failed_wrapper_refuses_by_exit_not_by_a_json_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caller: str
) -> None:
    _, refused = _CALLERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path)
    _ = _run_returning(
        monkeypatch=monkeypatch,
        stdout="",
        returncode=1,
        stderr="[ERROR] (500) Internal Server Error",
    )
    assert refused() is True
