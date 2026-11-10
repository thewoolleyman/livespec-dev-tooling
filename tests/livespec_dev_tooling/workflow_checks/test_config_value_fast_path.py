"""Mirror coverage for the config-value commit-hook workflow check."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest
import tomli

from livespec_dev_tooling.workflow_checks import config_value_fast_path as subject
from livespec_dev_tooling.workflow_checks.config_value_fast_path import (
    CONFIG_VALUE_FAST_PATH_RULES,
)

__all__: list[str] = []


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run one fixture repository command."""
    _ = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write(*, root: Path, path: str, text: str) -> None:
    """Write a fixture path, creating its parent directories."""
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _repository(*, tmp_path: Path) -> Path:
    """Create a committed fixture repository with each qualifying file shape."""
    root = tmp_path / "repo"
    root.mkdir()
    _write(
        root=root,
        path=".livespec.jsonc",
        text='{"dispatcher": {\n  "wip_cap": 4\n},\n"stall_timeout_seconds": 60\n}\n',
    )
    _write(root=root, path="ansible/inventory/host_vars/node.yml", text="max_concurrent_runs: 2\n")
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profiles/test.env",
        text="ADMISSION_CAPACITY_C=2\n",
    )
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profile.sh",
        text='profile_load() { test -n "$(grep "^ADMISSION_CAPACITY_C=[1-9]" "$1")"; }\n',
    )
    _git(cwd=root, args=["init", "--quiet", "-b", "master"])
    _git(cwd=root, args=["add", "."])
    _git(cwd=root, args=["commit", "--quiet", "-m", "base"])
    return root


def test_the_workflow_check_declares_the_required_capacity_keys() -> None:
    """The shared list remains the one declaration used by the hook classifier."""
    assert {rule.key_path for rule in CONFIG_VALUE_FAST_PATH_RULES} >= {
        "ADMISSION_CAPACITY_C",
        "dispatcher.wip_cap",
        "max_concurrent_runs",
        "stall_timeout_seconds",
    }


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (".livespec.jsonc", '"wip_cap": 4', '"wip_cap": 6'),
        (
            "ansible/inventory/host_vars/node.yml",
            "max_concurrent_runs: 2",
            "max_concurrent_runs: 3",
        ),
        (
            "ci-runner/k3s/phase0-bare-metal/profiles/test.env",
            "ADMISSION_CAPACITY_C=2",
            "ADMISSION_CAPACITY_C=3",
        ),
    ],
)
def test_declared_value_replacements_qualify_in_every_supported_format(
    *, tmp_path: Path, path: str, before: str, after: str
) -> None:
    """A complete declared value-line replacement is the only qualifying diff."""
    root = _repository(tmp_path=tmp_path)
    target = root / path
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace(before, after), encoding="utf-8"
    )
    _git(cwd=root, args=["add", path])
    assert subject.is_config_value_fast_path(cwd=root) is True
    assert subject.validate_config_value_fast_path(cwd=root) == ()


def test_classifier_rejects_empty_binary_added_removed_and_comment_diffs(*, tmp_path: Path) -> None:
    """Everything other than paired declared value lines retains ordinary pre-commit."""
    root = _repository(tmp_path=tmp_path)
    assert subject.is_config_value_fast_path(cwd=root) is False
    target = root / ".livespec.jsonc"
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace('"wip_cap": 4', '"wip_cap": 6\n"new": 1'),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", ".livespec.jsonc"])
    assert subject.is_config_value_fast_path(cwd=root) is False
    _git(cwd=root, args=["reset", "--hard", "HEAD"])
    _write(root=root, path="blob.bin", text="\x00changed")
    _git(cwd=root, args=["add", "blob.bin"])
    assert subject.is_config_value_fast_path(cwd=root) is False


def test_invalid_jsonc_yaml_and_profile_values_name_the_affected_rule(*, tmp_path: Path) -> None:
    """Validation preserves file/key diagnostics for every authoritative parser."""
    root = _repository(tmp_path=tmp_path)
    _write(root=root, path=".livespec.jsonc", text="{")
    _write(root=root, path="ansible/inventory/host_vars/node.yml", text="[")
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profiles/test.env",
        text="ADMISSION_CAPACITY_C=0\n",
    )
    _git(cwd=root, args=["add", "."])
    failures = subject.validate_config_value_fast_path(cwd=root)
    assert {(failure.path, failure.key_path) for failure in failures} >= {
        (".livespec.jsonc", "dispatcher.wip_cap"),
        ("ansible/inventory/host_vars/node.yml", "max_concurrent_runs"),
        ("ci-runner/k3s/phase0-bare-metal/profiles/test.env", "ADMISSION_CAPACITY_C"),
    }


def test_the_python_311_tomllib_import_path_loads_the_same_public_rules(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newer consumers use the standard-library TOML reader."""
    module_path = Path(subject.__file__)
    spec = importlib.util.spec_from_file_location("config_value_fast_path_tomllib", module_path)
    assert spec is not None
    assert spec.loader is not None
    fake_tomllib = types.ModuleType("tomllib")
    _ = setattr(fake_tomllib, "loads", tomli.loads)
    monkeypatch.setitem(sys.modules, "tomllib", fake_tomllib)
    monkeypatch.setattr(sys, "version_info", (3, 11))
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    try:
        spec.loader.exec_module(loaded)
    finally:
        del sys.modules[spec.name]
    assert {rule.key_path for rule in loaded.CONFIG_VALUE_FAST_PATH_RULES} == {
        rule.key_path for rule in CONFIG_VALUE_FAST_PATH_RULES
    }
