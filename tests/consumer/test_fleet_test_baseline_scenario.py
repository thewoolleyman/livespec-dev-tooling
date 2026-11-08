"""Consumer-tier scenario for the on-demand fleet test baseline recipe."""

from __future__ import annotations

import json
import os
import subprocess
from importlib import import_module
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(*, path: Path, body: str) -> None:
    """Write an executable fixture tool without relying on host toolchains."""
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _child_env(*, tools: Path) -> dict[str, str]:
    """Build a coverage-safe child environment with fixture tools first on PATH."""
    removed = {"COVERAGE_PROCESS_START", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COV_CORE_SOURCE"}
    return {key: value for key, value in os.environ.items() if key not in removed} | {
        "PATH": f"{tools}:{os.environ['PATH']}"
    }


def test_fleet_test_baseline_reports_all_ecosystems_and_fleet_totals(*, tmp_path: Path) -> None:
    """`just fleet-test-baseline` reports the stated data for three fixture clones."""
    tools = tmp_path / "tools"
    tools.mkdir()
    _write_executable(
        path=tools / "mise",
        body='#!/usr/bin/env bash\nshift\n[ "$1" = -- ] && shift\nexec "$@"\n',
    )
    _write_executable(
        path=tools / "uv",
        body=(
            "#!/usr/bin/env bash\n"
            "shift\n"
            'if [ "$1" = python ]; then exec "$@"; fi\n'
            '[ "$1" = pytest ] && shift\n'
            'if [[ " $* " == *" --collect-only "* ]]; then\n'
            "  echo '5 tests collected in 0.01s'\n"
            'elif [[ " $* " == *" --version "* ]]; then\n'
            "  echo 'pytest 8.3.4'\n"
            "fi\n"
        ),
    )
    _write_executable(
        path=tools / "cargo",
        body=(
            "#!/usr/bin/env bash\n"
            "if [ \"$1 $2 $3\" = 'nextest list --message-format' ]; then\n"
            '  echo \'{"rust-build-meta":{},"rust-suites":{},"test-count":3}\'\n'
            'elif [ "$1 $2" = "nextest --version" ]; then\n'
            "  echo 'cargo-nextest 0.9.82'\n"
            'elif [ "$1" = --version ]; then\n'
            "  echo 'cargo 1.82.0'\n"
            "fi\n"
        ),
    )
    python_repository = tmp_path / "pytest-suite"
    rust_repository = tmp_path / "rust-suite"
    shell_repository = tmp_path / "shell-suite"
    python_repository.mkdir()
    rust_repository.mkdir()
    shell_repository.mkdir()
    _ = rust_repository.joinpath("Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    for name in ("first.test.sh", "second.test.sh"):
        _write_executable(path=shell_repository / name, body="#!/usr/bin/env bash\n")

    completed = subprocess.run(
        [
            "just",
            "fleet-test-baseline",
            str(python_repository),
            str(rust_repository),
            str(shell_repository),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
        env=_child_env(tools=tools),
        text=True,
    )

    report = json.loads(completed.stdout)
    rows = {row["name"]: row for row in report["repositories"]}
    assert {name: row["test_count"] for name, row in rows.items()} == {
        "pytest-suite": 5,
        "rust-suite": 3,
        "shell-suite": 2,
    }
    assert report["fleet_totals"]["test_count"] == 10
    assert report["fleet_totals"]["runtime_seconds"] == sum(
        row["runtime_seconds"] for row in report["repositories"]
    )
    assert report["timing_method"] == "time.perf_counter around each repository test-only command"
    assert report["host"]["hostname"]
    assert all(row["toolchain_versions"] for row in report["repositories"])


def test_fleet_test_baseline_cli_emits_the_measurement_json(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public CLI transports its JSON-ready measurement unchanged."""
    module = import_module("livespec_dev_tooling.fleet_test_baseline")
    expected: dict[str, object] = {"fleet_totals": {"runtime_seconds": 1.5, "test_count": 3}}

    def fake_measure_repositories(*, paths: tuple[Path, ...]) -> dict[str, object]:
        assert paths == (Path("/clones/example"),)
        return expected

    monkeypatch.setattr(module, "measure_repositories", fake_measure_repositories)

    assert module.main(argv=["/clones/example"]) == 0
    assert json.loads(capsys.readouterr().out) == expected
