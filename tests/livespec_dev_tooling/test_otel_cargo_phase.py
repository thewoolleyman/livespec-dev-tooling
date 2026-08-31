"""Tests for otel_cargo_phase — the baked factory cargo-phase telemetry emitter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from livespec_dev_tooling.checks._public_api_consumption import repo_local_public_names
from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders
from livespec_dev_tooling.otel_cargo_phase import (
    BUILD_ENV,
    DATASET,
    DEFAULT_ENDPOINT,
    _read_text,
    _repo_from_remote,
    _stdout_of,
    _toolchain_version,
    build_span_payload,
    gather_source_facts,
    main,
    parse_env,
    post_span,
    run,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_OTEL_CARGO_PHASE_REL = Path("livespec_dev_tooling/otel_cargo_phase.py")
_OTEL_CARGO_PHASE = Path(__file__).resolve().parents[2] / _OTEL_CARGO_PHASE_REL

_FACTS = {
    "repo": "thewoolleyman/livespec-console-beads-fabro",
    "sha": "a" * 40,
    "toolchain": "1.92.0",
}


def _base_env(**overrides: str) -> dict[str, str]:
    env = {
        "BUILD_PHASE": "compile",
        "BUILD_SUBCMD": "build",
        "BUILD_START_NANO": "100",
        "BUILD_END_NANO": "250",
        "BUILD_EXIT_CODE": "0",
    }
    env.update(overrides)
    return env


def _recorder(store: list[dict[str, object]]) -> Callable[..., bool]:
    def _emit(*, endpoint: str, payload: dict[str, object]) -> bool:
        store.append({"endpoint": endpoint, "payload": payload})
        return True

    return _emit


def _wire(payload: object) -> Any:
    return json.loads(json.dumps(payload))


def _resource_attrs(payload: object) -> dict[str, Any]:
    attrs = _wire(payload)["resourceSpans"][0]["resource"]["attributes"]
    return {entry["key"]: entry["value"]["stringValue"] for entry in attrs}


def _span(payload: object) -> Any:
    return _wire(payload)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def _attrs(span: Any) -> dict[str, Any]:
    return {
        entry["key"]: entry["value"].get("stringValue", entry["value"].get("intValue"))
        for entry in span["attributes"]
    }


def test_parse_env_reads_all_required_inputs() -> None:
    parsed = parse_env(environ=_base_env(BUILD_EXIT_CODE="-7"))
    assert parsed == {
        "phase": "compile",
        "subcmd": "build",
        "start_ns": 100,
        "end_ns": 250,
        "exit_code": -7,
        "work_item_id": None,
    }


def test_parse_env_captures_optional_work_item() -> None:
    parsed = parse_env(environ=_base_env(LIVESPEC_WORK_ITEM_ID="bd-2er6nc"))
    assert parsed is not None
    assert parsed["work_item_id"] == "bd-2er6nc"


@pytest.mark.parametrize(
    "overrides",
    [
        {"BUILD_PHASE": ""},
        {"BUILD_SUBCMD": ""},
        {"BUILD_START_NANO": "notanumber"},
        {"BUILD_END_NANO": ""},
        {"BUILD_EXIT_CODE": "1.5"},
    ],
)
def test_parse_env_malformed_returns_none(overrides: dict[str, str]) -> None:
    assert parse_env(environ=_base_env(**overrides)) is None


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        (
            "git@github.com:thewoolleyman/livespec-console-beads-fabro.git",
            "thewoolleyman/livespec-console-beads-fabro",
        ),
        (
            "https://github.com/thewoolleyman/livespec-console-beads-fabro",
            "thewoolleyman/livespec-console-beads-fabro",
        ),
        ("https://gitlab.com/owner/repo.git", "unknown"),
        ("git@github.com:.git", "unknown"),
    ],
)
def test_repo_from_remote(remote: str, expected: str) -> None:
    assert _repo_from_remote(remote_url=remote) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('[toolchain]\nchannel = "1.92.0"\n', "1.92.0"),
        ("channel='1.90.1'", "1.90.1"),
        ("[toolchain]\ncomponents = []\n", "unknown"),
        ('channel = ""\n', "unknown"),
    ],
)
def test_toolchain_version(text: str, expected: str) -> None:
    assert _toolchain_version(text=text) == expected


def test_stdout_of_returns_trimmed_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="  owner/repo\n", stderr="")

    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase.subprocess.run", _fake_run)
    assert _stdout_of(command=["git", "x"]) == "owner/repo"


def test_stdout_of_nonzero_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="ignored", stderr="boom")

    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase.subprocess.run", _fake_run)
    assert _stdout_of(command=["git", "x"]) == ""


def test_stdout_of_swallows_spawn_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("no git")

    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase.subprocess.run", _fake_run)
    assert _stdout_of(command=["git", "x"]) == ""


def test_read_text_roundtrips(tmp_path: Path) -> None:
    target = tmp_path / "rust-toolchain.toml"
    _ = target.write_text('channel = "1.92.0"\n', encoding="utf-8")
    monkeypatch_cwd = target.parent
    assert _read_text(path=str(monkeypatch_cwd / "rust-toolchain.toml")) == 'channel = "1.92.0"\n'


def test_gather_source_facts_assembles_from_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    outputs = {
        (
            "git",
            "remote",
            "get-url",
            "origin",
        ): "git@github.com:thewoolleyman/livespec-console-beads-fabro.git",
        ("git", "rev-parse", "HEAD"): "b" * 40,
    }

    def _fake_stdout(*, command: list[str]) -> str:
        return outputs[tuple(command)]

    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase._stdout_of", _fake_stdout)
    monkeypatch.setattr(
        "livespec_dev_tooling.otel_cargo_phase._read_text",
        lambda **_kwargs: 'channel = "1.92.0"\n',
    )
    assert gather_source_facts() == {
        "repo": "thewoolleyman/livespec-console-beads-fabro",
        "sha": "b" * 40,
        "toolchain": "1.92.0",
    }


def test_gather_source_facts_degrades_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase._stdout_of", lambda **_kwargs: "")

    def _raise_read(**_kwargs: str) -> str:
        raise OSError("missing")

    monkeypatch.setattr("livespec_dev_tooling.otel_cargo_phase._read_text", _raise_read)
    assert gather_source_facts() == {"repo": "unknown", "sha": "unknown", "toolchain": "unknown"}


def test_build_span_payload_routing_and_scheme_attributes() -> None:
    payload = build_span_payload(
        inputs={
            "phase": "compile",
            "subcmd": "build",
            "start_ns": 100,
            "end_ns": 250,
            "exit_code": 0,
            "work_item_id": None,
        },
        facts=_FACTS,
    )
    resource = _resource_attrs(payload)
    assert resource["service.name"] == DATASET
    assert resource["service.namespace"] == "livespec-family"
    span = _span(payload)
    assert span["name"] == "build.cargo-build"
    assert span["startTimeUnixNano"] == "100"
    assert span["endTimeUnixNano"] == "250"
    assert span["status"] == {"code": 1}
    assert len(span["traceId"]) == 32
    assert len(span["spanId"]) == 16
    attrs = _attrs(span)
    assert attrs["build.env"] == BUILD_ENV
    assert attrs["build.phase"] == "compile"
    assert attrs["repo"] == _FACTS["repo"]
    assert attrs["git.commit.sha"] == _FACTS["sha"]
    assert attrs["toolchain.version"] == "1.92.0"
    assert attrs["cargo.subcommand"] == "build"
    assert attrs["exit_code"] == "0"
    assert "work_item_id" not in attrs


def test_build_span_payload_error_status_and_work_item() -> None:
    payload = build_span_payload(
        inputs={
            "phase": "test",
            "subcmd": "nextest",
            "start_ns": 1,
            "end_ns": 2,
            "exit_code": 101,
            "work_item_id": "bd-2er6nc",
        },
        facts=_FACTS,
    )
    span = _span(payload)
    assert span["name"] == "build.cargo-nextest"
    assert span["status"] == {"code": 2}
    attrs = _attrs(span)
    assert attrs["exit_code"] == "101"
    assert attrs["work_item_id"] == "bd-2er6nc"


def test_run_emits_span_and_returns_zero() -> None:
    store: list[dict[str, object]] = []
    code = run(environ=_base_env(), emit=_recorder(store), facts=lambda: _FACTS)
    assert code == 0
    assert len(store) == 1
    assert store[0]["endpoint"] == DEFAULT_ENDPOINT
    assert _attrs(_span(store[0]["payload"]))["build.env"] == "factory"


def test_run_endpoint_override() -> None:
    store: list[dict[str, object]] = []
    _ = run(
        environ=_base_env(LIVESPEC_SANDBOX_OTEL_ENDPOINT="  http://host:9999  "),
        emit=_recorder(store),
        facts=lambda: _FACTS,
    )
    assert store[0]["endpoint"] == "http://host:9999"


def test_run_malformed_returns_2_without_emitting(capsys: pytest.CaptureFixture[str]) -> None:
    store: list[dict[str, object]] = []
    code = run(environ={"BUILD_PHASE": ""}, emit=_recorder(store), facts=lambda: _FACTS)
    assert code == 2
    assert store == []
    assert "usage" in capsys.readouterr().err


def test_post_span_success_posts_json_to_traces_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        status = 200

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    def _fake_urlopen(request: Any, **_kwargs: object) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["data"] = request.data
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    assert post_span(endpoint="http://recv:4318", payload={"resourceSpans": []}) is True
    assert captured["url"] == "http://recv:4318/v1/traces"
    assert json.loads(captured["data"]) == {"resourceSpans": []}  # type: ignore[arg-type]
    assert capsys.readouterr().err == ""


def test_post_span_reports_non_200_loudly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _FakeResponse:
        status = 429

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"slow down"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse())
    assert post_span(endpoint="http://recv:4318", payload={}) is False
    assert "HTTP 429" in capsys.readouterr().err


def test_post_span_reports_unreachable_loudly(capsys: pytest.CaptureFixture[str]) -> None:
    # 127.0.0.1:1 is an unbound reserved port → connection-refused OSError the
    # emitter suppresses, reporting a loud (non-fatal) line to stderr not raising.
    assert (
        post_span(
            endpoint="http://127.0.0.1:1",
            payload={"resourceSpans": []},
            timeout=0.5,
        )
        is False
    )
    assert "failed" in capsys.readouterr().err


def test_main_drives_run_from_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    # Point the real post_span at a closed port so the emit reports-and-swallows
    # and main() still returns 0 from the well-formed environment.
    monkeypatch.setenv("LIVESPEC_SANDBOX_OTEL_ENDPOINT", "http://127.0.0.1:1")
    assert main() == 0


def test_all_declares_only_the_boundary_crossing_entry_point() -> None:
    """`__all__` names only the baked entry point, so the ROP check sees the real surface.

    Like ``otel_step_timer``, this module is ``COPY``d as a lone file onto the
    fabro-sandbox image (``/usr/local/bin/livespec-cargo-phase-timer``) and runs
    on the system python3 before any ``uv sync``, so it cannot import the
    railway; its offenders are closed by declaring the public surface honestly,
    not by conversion. Only ``main`` — the baked binary's entry point — crosses
    a boundary.
    """
    source = _OTEL_CARGO_PHASE.read_text(encoding="utf-8")
    public = repo_local_public_names(sources={_OTEL_CARGO_PHASE_REL: source})
    offenders = _find_offenders(
        source=source,
        rel_path=_OTEL_CARGO_PHASE_REL,
        commands_trees=(),
        public_names=frozenset(name for _rel, name in public),
    )
    assert [name for _lineno, name in offenders] == ["main"], (
        "otel_cargo_phase's declared public surface should reduce to its single baked "
        f"entry point; got {[name for _lineno, name in offenders]}"
    )
