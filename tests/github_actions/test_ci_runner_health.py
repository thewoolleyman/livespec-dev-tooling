"""Tests for the hosted CI runner-health action.

The action intentionally lives under ``.github/actions`` so that reusable
workflows can execute it without installing this package.  Import it directly
here: it has no third-party dependencies and its decision surface is pure.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_TEST_TOKEN = "not-a-secret"


def _load_action() -> ModuleType:
    path = (
        Path(__file__).parents[2] / ".github" / "actions" / "ci-runner-health" / "runner_health.py"
    )
    spec = importlib.util.spec_from_file_location("ci_runner_health", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_labels_require_a_nonempty_json_string_array() -> None:
    action = _load_action()

    assert action.parse_labels(raw='["self-hosted", "local-ci"]') == frozenset(
        {"self-hosted", "local-ci"}
    )

    for malformed in ("", "[]", '["local-ci", ""]', "not-json", '{"label": "local-ci"}'):
        with pytest.raises(ValueError, match="^$"):
            action.parse_labels(raw=malformed)


def test_only_idle_online_runners_with_every_required_label_are_healthy() -> None:
    action = _load_action()
    runners: list[dict[str, Any]] = [
        {
            "status": "offline",
            "busy": False,
            "labels": [{"name": "self-hosted"}, {"name": "local-ci"}],
        },
        {
            "status": "online",
            "busy": True,
            "labels": [{"name": "self-hosted"}, {"name": "local-ci"}],
        },
        {"status": "online", "busy": False, "labels": [{"name": "self-hosted"}]},
        {
            "status": "online",
            "busy": False,
            "labels": [{"name": "self-hosted"}, {"name": "local-ci"}],
        },
    ]

    assert (
        action.idle_matching_runners(
            runners=runners, required_labels=frozenset({"self-hosted", "local-ci"})
        )
        == 1
    )


def test_probe_fails_closed_on_an_api_error_without_exposing_the_token() -> None:
    action = _load_action()
    seen: list[str] = []

    def opener(*, url: str, token: str) -> dict[str, Any]:
        seen.extend((url, token))
        raise OSError("network unavailable")

    result = action.probe(
        repository="thewoolleyman/livespec-dev-tooling",
        token=_TEST_TOKEN,
        required_labels=frozenset({"self-hosted", "local-ci"}),
        opener=opener,
    )

    assert not result.healthy
    assert result.idle_matching == 0
    assert result.detail == "runner-api-error"
    assert seen[0].endswith(
        "/repos/thewoolleyman/livespec-dev-tooling/actions/runners?per_page=100"
    )
    assert _TEST_TOKEN not in result.detail


def test_probe_reports_healthy_from_a_matching_idle_runner() -> None:
    action = _load_action()

    def opener(*, url: str, token: str) -> dict[str, Any]:
        assert url.endswith("/repos/acme/widget/actions/runners?per_page=100")
        assert token == _TEST_TOKEN
        return {
            "runners": [
                {
                    "status": "online",
                    "busy": False,
                    "labels": [{"name": "self-hosted"}, {"name": "local-ci"}],
                }
            ]
        }

    result = action.probe(
        repository="acme/widget",
        token=_TEST_TOKEN,
        required_labels=frozenset({"self-hosted", "local-ci"}),
        opener=opener,
    )

    assert result.healthy
    assert result.idle_matching == 1
    assert result.detail == "idle-runner-observed"


def test_request_json_uses_the_read_only_github_api_headers(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _load_action()

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"runners": []}'

    def fake_urlopen(url: Any, *, timeout: int) -> Response:
        assert timeout == 10
        assert url.get_header("Accept") == "application/vnd.github+json"
        assert url.get_header("X-github-api-version") == "2022-11-28"
        assert url.get_header("Authorization") == f"Bearer {_TEST_TOKEN}"
        return Response()

    monkeypatch.setattr(action, "urlopen", fake_urlopen)

    assert action._request_json(  # noqa: SLF001 -- this test owns the composite action boundary.
        url="https://api.github.com/runners", token=_TEST_TOKEN
    ) == {"runners": []}


def test_probe_rejects_an_unparseable_runner_list() -> None:
    action = _load_action()

    result = action.probe(
        repository="acme/widget",
        token=_TEST_TOKEN,
        required_labels=frozenset({"self-hosted", "local-ci"}),
        opener=lambda **_: {"runners": "not-a-list"},
    )

    assert not result.healthy
    assert result.detail == "runner-api-error"


def test_probe_reports_unhealthy_when_no_matching_runner_is_idle() -> None:
    action = _load_action()

    result = action.probe(
        repository="acme/widget",
        token=_TEST_TOKEN,
        required_labels=frozenset({"self-hosted", "local-ci"}),
        opener=lambda **_: {
            "runners": [
                {
                    "status": "online",
                    "busy": True,
                    "labels": [{"name": "self-hosted"}, {"name": "local-ci"}],
                }
            ]
        },
    )

    assert not result.healthy
    assert result.detail == "no-idle-matching-runner"


def test_request_json_rejects_a_non_object_response(*, monkeypatch: pytest.MonkeyPatch) -> None:
    action = _load_action()

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def fake_urlopen(_request: Any, *, timeout: int) -> Response:
        assert timeout == 10
        return Response()

    monkeypatch.setattr(action, "urlopen", fake_urlopen)

    with pytest.raises(TypeError):
        action._request_json(  # noqa: SLF001 -- this test owns the composite action boundary.
            url="https://api.github.com/runners", token=_TEST_TOKEN
        )


def test_main_writes_safe_output_for_healthy_and_invalid_inputs(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _load_action()
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widget")
    monkeypatch.setenv("CI_RUNNER_HEALTH_TOKEN", _TEST_TOKEN)
    monkeypatch.setenv("CI_RUNNER_HEALTH_LABELS", '["self-hosted","local-ci"]')
    monkeypatch.setattr(
        action,
        "probe",
        lambda **_: action.ProbeResult(
            healthy=True, idle_matching=2, detail="idle-runner-observed"
        ),
    )

    assert action.main() == 0
    assert output.read_text(encoding="utf-8") == (
        "healthy=true\nidle-matching=2\ndetail=idle-runner-observed\n"
    )

    output.write_text("", encoding="utf-8")
    monkeypatch.setenv("CI_RUNNER_HEALTH_LABELS", "not-json")

    assert action.main() == 0
    assert output.read_text(encoding="utf-8") == (
        "healthy=false\nidle-matching=0\ndetail=invalid-health-probe-input\n"
    )
