"""The incident-ci entrance provisions locked pyright before it fans out its members.

livespec-dev-tooling-xdt4ue: two pyright-invoking members launched together on a
cold `~/.cache/pyright-python` type-check against a half-written typeshed
(measured on livespec#3199, CI run 43431280787). The normal parallel dispatcher
runs `warm_locked_pyright` before it fans out; the entrance must do the same,
launch nothing when that provisioning fails, and skip it for a lock that does
not pin pyright.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_entry as module
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget
from tests.livespec_dev_tooling.test_incident_ci_payload import packet

_PROVISION = "run --frozen pyright --version"
_MEMBERS = ("check-types", "check-no-shadow-ledger-body-typechecks")


def _event() -> CiEvent:
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )


def _uv_stub(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int = 0) -> Path:
    """A `uv` on PATH that records provisioning and marks the cache ready."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "uv"
    _ = stub.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$PYRIGHT_LOG"\n'
        f"if [ \"$*\" = '{_PROVISION}' ]; then\n"
        f"    [ {status} -eq 0 ] || exit {status}\n"
        '    touch "$PYRIGHT_READY"\n'
        "    exit 0\n"
        "fi\n"
        "exit 99\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    log = tmp_path / "pyright.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("PYRIGHT_LOG", str(log))
    monkeypatch.setenv("PYRIGHT_READY", str(tmp_path / "pyright-ready"))
    return log


def _repository(*, tmp_path: Path, pins_pyright: bool) -> Path:
    """A consumer checkout whose two members each need a provisioned pyright cache."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dev = '    { name = "pyright" },\n' if pins_pyright else ""
    _ = (repo / "uv.lock").write_text(
        "version = 1\n\n"
        '[[package]]\nname = "consumer"\nversion = "0.1.0"\n'
        'source = { editable = "." }\n\n'
        f"[package.dev-dependencies]\ndev = [\n{dev}]\n",
        encoding="utf-8",
    )
    recipe = "\n".join(
        f'{name}:\n    test -f "$PYRIGHT_READY" || {{ echo cold >> "$PYRIGHT_LOG"; exit 3; }}\n'
        f'    echo {name} >> "$PYRIGHT_LOG"'
        for name in _MEMBERS
    )
    _ = (repo / "justfile").write_text(recipe + "\n", encoding="utf-8")
    return repo


def _execute(*, repo: Path, environ: dict[str, str], lines: list[str] | None) -> int:
    entry = module.CiEntry(
        repo=repo,
        targets=tuple(CiTarget(name=name, classification="fast") for name in _MEMBERS),
        current=lambda **_: True,
        observer=lambda **_: True,
    )
    payload = json.dumps(packet())
    plan = entry.plan(event=_event(), payload=payload, environ=environ)
    assert plan is not None
    return entry.execute(
        plan=plan,
        names=_MEMBERS,
        report=repo / "outcomes.jsonl",
        payload=payload,
        environ=environ,
        echo=None if lines is None else (lambda *, text: lines.append(text)),
    )


def _log(*, path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


def test_two_pyright_members_start_only_after_one_completed_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _uv_stub(tmp_path=tmp_path, monkeypatch=monkeypatch)
    repo = _repository(tmp_path=tmp_path, pins_pyright=True)
    code = _execute(repo=repo, environ=dict(os.environ), lines=[])
    entries = _log(path=log)
    assert entries[:1] == [_PROVISION], f"provisioning must run before any member: {entries}"
    assert entries.count(_PROVISION) == 1, f"provisioning must run once: {entries}"
    assert sorted(entries[1:]) == sorted(_MEMBERS), f"members ran on a cold cache: {entries}"
    assert code == 0


def test_failed_provisioning_launches_no_member_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _uv_stub(tmp_path=tmp_path, monkeypatch=monkeypatch, status=4)
    repo = _repository(tmp_path=tmp_path, pins_pyright=True)
    lines: list[str] = []
    code = _execute(repo=repo, environ=dict(os.environ), lines=lines)
    assert _log(path=log) == [_PROVISION], "no member may start after failed provisioning"
    assert code != 0
    assert any("pyright provisioning failed" in line for line in lines), lines
    assert not (repo / "outcomes.jsonl").exists()


def test_a_lock_that_does_not_pin_pyright_launches_members_without_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _uv_stub(tmp_path=tmp_path, monkeypatch=monkeypatch)
    (tmp_path / "pyright-ready").touch()
    repo = _repository(tmp_path=tmp_path, pins_pyright=False)
    code = _execute(repo=repo, environ=dict(os.environ), lines=[])
    assert _PROVISION not in _log(path=log)
    assert sorted(_log(path=log)) == sorted(_MEMBERS)
    assert code == 0


def test_an_already_warmed_environment_skips_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _uv_stub(tmp_path=tmp_path, monkeypatch=monkeypatch)
    (tmp_path / "pyright-ready").touch()
    repo = _repository(tmp_path=tmp_path, pins_pyright=True)
    environ = dict(os.environ) | {"LIVESPEC_PYRIGHT_WARMED": "1"}
    code = _execute(repo=repo, environ=environ, lines=[])
    assert _PROVISION not in _log(path=log)
    assert code == 0


def test_failed_provisioning_without_an_echo_still_launches_no_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _uv_stub(tmp_path=tmp_path, monkeypatch=monkeypatch, status=4)
    repo = _repository(tmp_path=tmp_path, pins_pyright=True)
    assert _execute(repo=repo, environ=dict(os.environ), lines=None) != 0
    assert _log(path=log) == [_PROVISION]
