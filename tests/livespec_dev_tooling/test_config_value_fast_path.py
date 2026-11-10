"""The pre-commit config-value lane validates declared values without running tests."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "livespec_dev_tooling" / "config_value_fast_path.py"
_HOOK = _ROOT / "scripts" / "just" / "check-pre-commit.sh"
_FAKE_UV = """#!/usr/bin/env bash
printf '%s\\n' \"$*\" >> \"$UV_LOG\"
if [ \"$1\" = run ]; then
    shift
fi
exec \"$CONFIG_VALUE_FAST_PATH_PYTHON\" \"$@\"
"""
_FAKE_JUST = """#!/usr/bin/env bash
printf 'just %s\\n' \"$*\" >> \"$JUST_LOG\"
"""
_CONFIG = """{
  \"harnesses\": {
    \"dispatcher\": {
      \"wip_cap\": 4
    }
  },
  \"stall_timeout_seconds\": 60
}
"""


def _module() -> object:
    """Import the feature module after proving its shipped source exists."""
    assert (
        _MODULE_PATH.is_file()
    ), "the config-value fast-path classifier must ship as shared tooling"
    return importlib.import_module("livespec_dev_tooling.config_value_fast_path")


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a fixture git command."""
    _ = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write(*, root: Path, relative_path: str, body: str) -> None:
    """Write one fixture file."""
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _install_fixture(*, tmp_path: Path) -> None:
    """Create a minimal staged repository and the hook's harmless command doubles."""
    shutil.copytree(_ROOT / "scripts", tmp_path / "scripts")
    _write(root=tmp_path, relative_path=".livespec.jsonc", body=_CONFIG)
    _write(root=tmp_path, relative_path="README.md", body="# fixture\n")
    _write(root=tmp_path, relative_path="bin/uv", body=_FAKE_UV)
    _write(root=tmp_path, relative_path="bin/just", body=_FAKE_JUST)
    for command in (tmp_path / "bin" / "uv", tmp_path / "bin" / "just"):
        command.chmod(0o755)
    _git(cwd=tmp_path, args=["init", "--quiet", "-b", "master"])
    _git(cwd=tmp_path, args=["add", "."])
    _git(cwd=tmp_path, args=["commit", "--quiet", "-m", "base"])


def _run_hook(*, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the real hook script with the shared tooling importable from this checkout."""
    environment = {
        **os.environ,
        "CONFIG_VALUE_FAST_PATH_PYTHON": sys.executable,
        "JUST_LOG": str(tmp_path / "just.log"),
        "LIVESPEC_GATE_CONTEXT": "1",
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "PYTHONPATH": str(_ROOT),
        "UV_LOG": str(tmp_path / "uv.log"),
    }
    return subprocess.run(
        ["bash", "scripts/just/check-pre-commit.sh"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )


def _replace_and_stage(*, tmp_path: Path, old: str, new: str) -> None:
    """Replace one fixture fragment and stage its file."""
    path = tmp_path / ".livespec.jsonc"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    _git(cwd=tmp_path, args=["add", ".livespec.jsonc"])


def test_declared_config_value_changes_take_the_schema_only_pre_commit_lane(
    *, tmp_path: Path
) -> None:
    """Valid values bypass tests, invalid values name their key, and mixed diffs retain normal gating."""
    module = _module()
    rules = module.CONFIG_VALUE_FAST_PATH_RULES
    assert {(rule.pattern, rule.key_path) for rule in rules} >= {
        (".livespec.jsonc", "dispatcher.wip_cap"),
        (".livespec.jsonc", "stall_timeout_seconds"),
        ("ansible/inventory/host_vars/*.yml", "max_concurrent_runs"),
        ("ci-runner/k3s/phase0-bare-metal/profiles/*.env", "ADMISSION_CAPACITY_C"),
    }

    _install_fixture(tmp_path=tmp_path)
    _replace_and_stage(tmp_path=tmp_path, old='"wip_cap": 4', new='"wip_cap": 6')
    valid = _run_hook(tmp_path=tmp_path)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    assert not (tmp_path / "just.log").exists()
    assert "config_value_fast_path classify" in (tmp_path / "uv.log").read_text(encoding="utf-8")
    assert "config_value_fast_path validate" in (tmp_path / "uv.log").read_text(encoding="utf-8")

    _install_fixture(tmp_path=tmp_path)
    _replace_and_stage(tmp_path=tmp_path, old='"wip_cap": 4', new='"wip_cap": "bad"')
    invalid = _run_hook(tmp_path=tmp_path)
    assert invalid.returncode != 0
    assert ".livespec.jsonc" in invalid.stderr
    assert "dispatcher.wip_cap" in invalid.stderr
    assert not (tmp_path / "just.log").exists()

    _install_fixture(tmp_path=tmp_path)
    _replace_and_stage(tmp_path=tmp_path, old='"wip_cap": 4', new='"wip_cap": 6 // comment change"')
    mixed = _run_hook(tmp_path=tmp_path)
    assert mixed.returncode == 0, mixed.stdout + mixed.stderr
    assert (tmp_path / "just.log").read_text(encoding="utf-8") == "just check-pre-commit-doc-only\n"
