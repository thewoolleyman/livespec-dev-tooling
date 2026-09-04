"""Tests for otel_cargo_phase — the baked factory cargo-phase telemetry emitter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from livespec_dev_tooling.checks._public_api_consumption import repo_local_public_names
from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders
from livespec_dev_tooling.otel_cargo_phase import (
    BUILD_ENV,
    DATASET,
    DEFAULT_ENDPOINT,
    _backend_of,
    _counter_total,
    _read_text,
    _repo_from_remote,
    _sccache_binary,
    _stdout_of,
    _toolchain_version,
    build_span_payload,
    cache_attributes,
    gather_source_facts,
    main,
    parse_env,
    parse_sccache_stats,
    post_span,
    read_sccache_stats,
    registry_hit,
    run,
    zero_sccache_stats,
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
_MODULE = "livespec_dev_tooling.otel_cargo_phase"
# The endpoint substring below is the credential-shaped part `_backend_of` must
# never let through to an attribute (see the leak assertion further down).
_SCCACHE_JSON = json.dumps(
    {
        "stats": {
            "compile_requests": 12,
            "cache_hits": {"counts": {"Rust": 9}},
            "cache_misses": {"counts": {"Rust": 3}},
            "cache_errors": {"counts": {"Rust": 1}},
            "cache_location": "Redis: redis://sccache-redis.ci-sccache.svc.cluster.local:6379",
        }
    }
)
_CACHE_ATTRS: list[dict[str, object]] = [
    {"key": "build.cache.sccache.enabled", "value": {"boolValue": True}},
    {"key": "build.cache.registry.hit", "value": {"boolValue": False}},
]


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
    # Each OTLP AnyValue carries exactly one typed key (stringValue, intValue,
    # boolValue, doubleValue), so the sole value IS the attribute's value.
    return {entry["key"]: next(iter(entry["value"].values())) for entry in span["attributes"]}


def _cache_attrs(attrs: list[dict[str, object]]) -> dict[str, Any]:
    return _attrs(_wire({"attributes": attrs}))


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


def test_parse_sccache_stats_reads_the_nested_counts_shape() -> None:
    assert parse_sccache_stats(text=_SCCACHE_JSON) == (9, 3, 1, "redis")


def test_parse_sccache_stats_reads_the_bare_integer_shape() -> None:
    text = json.dumps(
        {
            "stats": {
                "cache_hits": 4,
                "cache_misses": 0,
                "cache_errors": 2,
                "cache_location": "Local disk: /root/.cache/sccache",
            }
        }
    )
    assert parse_sccache_stats(text=text) == (4, 0, 2, "local-disk")


@pytest.mark.parametrize(
    "text",
    ["", "not json at all", "[]", "{}", '{"stats": 5}'],
)
def test_parse_sccache_stats_unrecognised_text_returns_none(text: str) -> None:
    assert parse_sccache_stats(text=text) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (7, 7),
        ({"counts": {"Rust": 2, "C/C++": 3}}, 5),
        ({"counts": {}}, 0),
        ({"adv_counts": {"Rust": 2}}, 0),
        (None, 0),
        ("nine", 0),
    ],
)
def test_counter_total_reads_both_shapes_and_degrades(value: object, expected: int) -> None:
    assert _counter_total(value=value) == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        # The detail after the head — endpoint, bucket, credential — is dropped.
        ("Redis: redis://someuser:somepass@host:6379", "redis"),
        ("Local disk: /root/.cache/sccache", "local-disk"),
        ("S3, bucket: livespec", "s3"),
        ("Memcached", "memcached"),
        # A head that is not a bare word never reaches an attribute.
        ("/root/.cache/sccache", "unknown"),
        ("", "unknown"),
    ],
)
def test_backend_of_reduces_a_location_to_a_token(location: str, expected: str) -> None:
    assert _backend_of(location=location) == expected


def test_sccache_binary_prefers_path(tmp_path: Path) -> None:
    binary = tmp_path / "sccache"
    _ = binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)
    assert _sccache_binary(environ={"PATH": str(tmp_path)}) == str(binary)


def test_sccache_binary_falls_back_to_the_pool_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount = tmp_path / "pool-sccache"
    _ = mount.write_text("", encoding="utf-8")
    mount.chmod(0o755)
    monkeypatch.setattr(f"{_MODULE}._POOL_SCCACHE_BIN", str(mount))
    assert _sccache_binary(environ={"PATH": str(tmp_path / "empty")}) == str(mount)


def test_sccache_binary_absent_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(f"{_MODULE}._POOL_SCCACHE_BIN", str(tmp_path / "absent"))
    assert _sccache_binary(environ={"PATH": str(tmp_path)}) == ""


def test_zero_sccache_stats_invokes_zero_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def _fake_stdout(*, command: list[str]) -> str:
        seen.append(command)
        return "Statistics zeroed."

    monkeypatch.setattr(f"{_MODULE}._sccache_binary", lambda **_kwargs: "/usr/bin/sccache")
    monkeypatch.setattr(f"{_MODULE}._stdout_of", _fake_stdout)
    assert zero_sccache_stats(environ={}) is True
    assert seen == [["/usr/bin/sccache", "--zero-stats"]]


def test_zero_sccache_stats_without_sccache_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}._sccache_binary", lambda **_kwargs: "")
    assert zero_sccache_stats(environ={}) is False


def test_zero_sccache_stats_silent_run_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}._sccache_binary", lambda **_kwargs: "/usr/bin/sccache")
    monkeypatch.setattr(f"{_MODULE}._stdout_of", lambda **_kwargs: "")
    assert zero_sccache_stats(environ={}) is False


def test_read_sccache_stats_asks_for_the_json_format(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def _fake_stdout(*, command: list[str]) -> str:
        seen.append(command)
        return _SCCACHE_JSON

    monkeypatch.setattr(f"{_MODULE}._sccache_binary", lambda **_kwargs: "/usr/bin/sccache")
    monkeypatch.setattr(f"{_MODULE}._stdout_of", _fake_stdout)
    assert read_sccache_stats(environ={}) == _SCCACHE_JSON
    assert seen == [["/usr/bin/sccache", "--show-stats", "--stats-format=json"]]


def test_registry_hit_true_when_the_registry_cache_is_populated(tmp_path: Path) -> None:
    (tmp_path / "registry" / "cache").mkdir(parents=True)
    assert registry_hit(environ={"CARGO_HOME": f"  {tmp_path}  "}) is True


def test_registry_hit_false_without_a_registry_cache(tmp_path: Path) -> None:
    assert registry_hit(environ={"CARGO_HOME": str(tmp_path)}) is False


def test_registry_hit_false_when_the_cargo_home_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable ``CARGO_HOME`` reads as "no warm registry", never as a raise.

    Measured 2026-09-04: the fleet's post-merge janitor runs the suite as an
    unprivileged user on a host where ``/root`` exists and is 0700, so the
    default ``/root/.cargo/registry/cache`` probe raised ``PermissionError``
    out of ``run()`` (``pathlib`` swallows ENOENT, not EACCES) and turned a
    green PR into a red master. A stat failure of any kind is "absent".
    """

    def _deny(_self: Path) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "is_dir", _deny)
    assert registry_hit(environ={"CARGO_HOME": "/root/.cargo"}) is False


def test_registry_hit_defaults_to_the_image_cargo_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "registry" / "cache").mkdir(parents=True)
    monkeypatch.setattr(f"{_MODULE}._DEFAULT_CARGO_HOME", str(tmp_path))
    assert registry_hit(environ={"CARGO_HOME": ""}) is True


def test_cache_attributes_carry_every_pool_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: True)
    attrs = _cache_attrs(
        cache_attributes(environ={"SCCACHE_REDIS_RW_MODE": " read_only "}, stats=_SCCACHE_JSON)
    )
    assert attrs == {
        "build.cache.sccache.enabled": True,
        "build.cache.sccache.hits": "9",
        "build.cache.sccache.misses": "3",
        "build.cache.sccache.errors": "1",
        "build.cache.sccache.hit_ratio": 0.75,
        "build.cache.sccache.backend": "redis",
        "build.cache.sccache.rw_mode": "READ_ONLY",
        "build.cache.registry.hit": True,
    }
    # No emitter may carry the cache's endpoint or credential: the backend is a
    # token, never the `cache_location` string it was derived from.
    assert "cluster.local" not in json.dumps(attrs)


def test_cache_attributes_default_rw_mode_is_sccache_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: False)
    attrs = _cache_attrs(cache_attributes(environ={}, stats=_SCCACHE_JSON))
    assert attrs["build.cache.sccache.rw_mode"] == "READ_WRITE"
    assert attrs["build.cache.registry.hit"] is False


def test_cache_attributes_enabled_with_no_requests_has_zero_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: False)
    attrs = _cache_attrs(
        cache_attributes(
            environ={}, stats=json.dumps({"stats": {"cache_hits": 0, "cache_misses": 0}})
        )
    )
    assert attrs["build.cache.sccache.enabled"] is True
    assert attrs["build.cache.sccache.hit_ratio"] == 0.0
    assert attrs["build.cache.sccache.backend"] == "unknown"


def test_cache_attributes_degrade_without_sccache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: False)
    attrs = _cache_attrs(
        cache_attributes(environ={"SCCACHE_REDIS_RW_MODE": "READ_ONLY"}, stats=None)
    )
    assert attrs == {
        "build.cache.sccache.enabled": False,
        "build.cache.sccache.hits": "0",
        "build.cache.sccache.misses": "0",
        "build.cache.sccache.errors": "0",
        "build.cache.sccache.hit_ratio": 0.0,
        "build.cache.sccache.backend": "none",
        "build.cache.sccache.rw_mode": "none",
        "build.cache.registry.hit": False,
    }


def test_cache_attributes_degrade_on_unparseable_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: False)
    attrs = _cache_attrs(cache_attributes(environ={}, stats="sccache: command not found"))
    assert attrs["build.cache.sccache.enabled"] is False


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
        cache=_CACHE_ATTRS,
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
    assert attrs["build.cache.sccache.enabled"] is True
    assert attrs["build.cache.registry.hit"] is False
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
        cache=_CACHE_ATTRS,
    )
    span = _span(payload)
    assert span["name"] == "build.cargo-nextest"
    assert span["status"] == {"code": 2}
    attrs = _attrs(span)
    assert attrs["exit_code"] == "101"
    assert attrs["work_item_id"] == "bd-2er6nc"


def test_run_emits_span_with_cache_attributes_and_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f"{_MODULE}.registry_hit", lambda **_kwargs: True)
    store: list[dict[str, object]] = []
    code = run(
        environ=_base_env(),
        emit=_recorder(store),
        facts=lambda: _FACTS,
        stats=lambda **_kwargs: _SCCACHE_JSON,
    )
    assert code == 0
    assert len(store) == 1
    assert store[0]["endpoint"] == DEFAULT_ENDPOINT
    attrs = _attrs(_span(store[0]["payload"]))
    assert attrs["build.env"] == "factory"
    assert attrs["build.cache.sccache.hits"] == "9"
    assert attrs["build.cache.sccache.hit_ratio"] == 0.75
    assert attrs["build.cache.registry.hit"] is True


def test_run_endpoint_override() -> None:
    store: list[dict[str, object]] = []
    _ = run(
        environ=_base_env(LIVESPEC_SANDBOX_OTEL_ENDPOINT="  http://host:9999  "),
        emit=_recorder(store),
        facts=lambda: _FACTS,
        stats=lambda **_kwargs: None,
    )
    assert store[0]["endpoint"] == "http://host:9999"


def test_run_malformed_returns_2_without_emitting(capsys: pytest.CaptureFixture[str]) -> None:
    store: list[dict[str, object]] = []
    code = run(
        environ={"BUILD_PHASE": ""},
        emit=_recorder(store),
        facts=lambda: _FACTS,
        stats=lambda **_kwargs: None,
    )
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


def test_main_drives_run_from_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)
    # Point the real post_span at a closed port so the emit reports-and-swallows
    # and main() still returns 0 from the well-formed environment. The empty
    # PATH and absent pool mount keep the sccache probe off whatever the host
    # running the suite happens to have installed.
    monkeypatch.setenv("LIVESPEC_SANDBOX_OTEL_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(f"{_MODULE}._POOL_SCCACHE_BIN", str(tmp_path / "absent"))
    assert main() == 0


def test_main_zero_stats_mode_zeroes_before_cargo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, str]] = []

    def _fake_zero(*, environ: dict[str, str]) -> bool:
        calls.append(environ)
        return True

    monkeypatch.setattr(f"{_MODULE}.zero_sccache_stats", _fake_zero)
    monkeypatch.setattr(sys, "argv", ["livespec-cargo-phase-timer", "--zero-stats"])
    assert main() == 0
    assert len(calls) == 1


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
