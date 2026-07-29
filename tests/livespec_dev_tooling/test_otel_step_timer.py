"""Tests for otel_step_timer — the baked sandbox prepare-step timing wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders
from livespec_dev_tooling.otel_step_timer import (
    DATASET,
    DEFAULT_ENDPOINT,
    build_trace_payload,
    main,
    parse_argv,
    post_span,
    run,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_OTEL_STEP_TIMER_REL = Path("livespec_dev_tooling/otel_step_timer.py")
_OTEL_STEP_TIMER = Path(__file__).resolve().parents[2] / _OTEL_STEP_TIMER_REL


def _recorder(store: list[dict[str, object]]) -> Callable[..., None]:
    """Return an emit-seam recorder that appends each (endpoint, payload)."""

    def _emit(*, endpoint: str, payload: dict[str, object]) -> None:
        store.append({"endpoint": endpoint, "payload": payload})

    return _emit


def _wire(payload: object) -> Any:
    """Round-trip the payload through JSON — the exact bytes post_span sends."""
    return json.loads(json.dumps(payload))


def _service_name(payload: object) -> Any:
    return _wire(payload)["resourceSpans"][0]["resource"]["attributes"][0]


def _span(payload: object) -> Any:
    return _wire(payload)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def _attrs(span: Any) -> dict[str, Any]:
    return {
        entry["key"]: entry["value"].get("stringValue", entry["value"].get("intValue"))
        for entry in span["attributes"]
    }


def test_parse_argv_splits_on_first_double_dash() -> None:
    assert parse_argv(argv=["uv-sync", "--", "uv", "sync", "--all-groups"]) == (
        "uv-sync",
        ["uv", "sync", "--all-groups"],
    )


def test_parse_argv_keeps_dashes_after_first_separator() -> None:
    assert parse_argv(argv=["s", "--", "cmd", "--flag", "--x"]) == ("s", ["cmd", "--flag", "--x"])


@pytest.mark.parametrize(
    "argv",
    [
        ["no-separator", "here"],
        ["--", "cmd"],
        ["", "--", "cmd"],
        ["a", "b", "--", "cmd"],
        ["step", "--"],
    ],
)
def test_parse_argv_malformed_returns_none(argv: list[str]) -> None:
    assert parse_argv(argv=argv) is None


def test_build_trace_payload_shape_and_routing() -> None:
    payload = build_trace_payload(
        step_name="uv-sync", start_ns=100, end_ns=250, exit_code=0, work_item_id=None
    )
    name_attr = _service_name(payload)
    assert name_attr["key"] == "service.name"
    assert name_attr["value"]["stringValue"] == DATASET
    span = _span(payload)
    assert span["name"] == "prepare.uv-sync"
    assert span["startTimeUnixNano"] == "100"
    assert span["endTimeUnixNano"] == "250"
    assert span["status"] == {"code": 1}
    assert len(span["traceId"]) == 32
    assert len(span["spanId"]) == 16
    attrs = _attrs(span)
    assert attrs["step.name"] == "uv-sync"
    assert attrs["exit_code"] == "0"
    assert "work_item_id" not in attrs


def test_build_trace_payload_error_status_and_work_item() -> None:
    payload = build_trace_payload(
        step_name="mise-install", start_ns=1, end_ns=2, exit_code=3, work_item_id="bd-ib-l7c"
    )
    span = _span(payload)
    assert span["status"] == {"code": 2}
    attrs = _attrs(span)
    assert attrs["exit_code"] == "3"
    assert attrs["work_item_id"] == "bd-ib-l7c"


def test_run_passes_through_exit_code_and_records_span() -> None:
    store: list[dict[str, object]] = []
    code = run(argv=["step", "--", "sh", "-c", "exit 7"], environ={}, emit=_recorder(store))
    assert code == 7
    assert len(store) == 1
    assert _attrs(_span(store[0]["payload"]))["exit_code"] == "7"


def test_run_streams_pass_through(capfd: pytest.CaptureFixture[str]) -> None:
    code = run(
        argv=["step", "--", "sh", "-c", "printf hello; printf boom 1>&2"],
        environ={},
        emit=_recorder([]),
    )
    assert code == 0
    captured = capfd.readouterr()
    assert captured.out == "hello"
    assert captured.err == "boom"


def test_run_malformed_returns_2_without_emitting(capsys: pytest.CaptureFixture[str]) -> None:
    store: list[dict[str, object]] = []
    code = run(argv=["no-separator"], environ={}, emit=_recorder(store))
    assert code == 2
    assert store == []
    assert "usage" in capsys.readouterr().err


def test_run_endpoint_override_and_default() -> None:
    store: list[dict[str, object]] = []
    _ = run(argv=["s", "--", "true"], environ={}, emit=_recorder(store))
    _ = run(
        argv=["s", "--", "true"],
        environ={"LIVESPEC_SANDBOX_OTEL_ENDPOINT": "  http://host:9999  "},
        emit=_recorder(store),
    )
    assert store[0]["endpoint"] == DEFAULT_ENDPOINT
    assert store[1]["endpoint"] == "http://host:9999"


def test_post_span_success_posts_json_to_traces_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    def _fake_urlopen(request: Any, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    post_span(endpoint="http://recv:4318", payload={"resourceSpans": []})
    assert captured["url"] == "http://recv:4318/v1/traces"
    assert json.loads(captured["data"]) == {"resourceSpans": []}  # type: ignore[arg-type]


def test_post_span_swallows_network_error() -> None:
    # 127.0.0.1:1 is an unbound reserved port → a real connection-refused
    # OSError that post_span must swallow (a broken stopwatch never raises).
    post_span(endpoint="http://127.0.0.1:1", payload={"resourceSpans": []}, timeout=0.5)


def test_main_drives_run_from_argv_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # main() drives the real post_span; point it at a closed port so the
    # emit swallows the connection error and the wrapped `true` still exits 0.
    monkeypatch.setattr("sys.argv", ["livespec-step-timer", "lefthook-install", "--", "true"])
    monkeypatch.setenv("LIVESPEC_SANDBOX_OTEL_ENDPOINT", "http://127.0.0.1:1")
    assert main() == 0


def test_all_declares_only_the_boundary_crossing_entry_point() -> None:
    """`__all__` names only what crosses a module boundary, so the ROP check sees the real surface.

    This module cannot import the railway at ALL: the base image ``COPY``s this one
    file to ``/usr/local/bin/livespec-step-timer`` and runs it on the system python3
    BEFORE the first ``uv sync``, so a ``returns`` import would break every dispatched
    Fabro prepare step. Its offenders therefore cannot be closed by conversion — only
    by declaring the public surface honestly.

    ``parse_argv``, ``build_trace_payload``, ``run`` and ``post_span`` are internal
    helpers of a baked CLI, exported so this file could reach them. Each was justified
    individually against the FLEET-WIDE boundary oracle (see the commit): zero
    references in any of the eight siblings. ``main`` stays — the baked binary name is
    referenced 15 times fleet-wide and every one of those enters through it.

    The residual ``main`` offender is deliberately NOT closed here: it needs a reasoned
    ``supervisor_entry_files`` entry, which grants FOUR exemptions, and bundling that
    into this change would smuggle in exemptions this file does not need.
    """
    offenders = _find_offenders(
        source=_OTEL_STEP_TIMER.read_text(encoding="utf-8"),
        rel_path=_OTEL_STEP_TIMER_REL,
        commands_trees=(),
    )

    assert [name for _lineno, name in offenders] == ["main"], (
        "otel_step_timer's declared public surface should reduce to its single baked "
        f"entry point; got {[name for _lineno, name in offenders]}"
    )
