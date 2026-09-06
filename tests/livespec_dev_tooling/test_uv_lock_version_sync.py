"""Outside-in test for `livespec_dev_tooling/uv_lock_version_sync.py`.

The invariant is a two-file agreement: `uv.lock`'s own editable
`[[package]]` entry records the same version `pyproject.toml`'s
`[project]` table declares. The check is static, credential-free,
network-free, and fail-closed — it reads two committed files and
nothing else.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "uv_lock_version_sync.py"

_PROJECT = "livespec-dev-tooling"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "uv_lock_version_sync check module should exist"
    spec = importlib.util.spec_from_file_location("uv_lock_version_sync_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write(*, root: Path, name: str, text: str) -> None:
    """Write a fixture file under `root`."""
    _ = (root / name).write_text(text, encoding="utf-8")


def _pyproject(*, body: str = f'[project]\nname = "{_PROJECT}"\nversion = "1.47.0"\n') -> str:
    """A `pyproject.toml` fixture; `body` overrides the whole document."""
    return body


def _uv_lock(*, entries: str) -> str:
    """A `uv.lock` fixture wrapping `entries` in the lock's preamble."""
    return f"version = 1\nrevision = 3\n\n{entries}"


def _self_entry(*, version: str) -> str:
    """The project's OWN editable `[[package]]` entry at `version`."""
    return (
        f'[[package]]\nname = "{_PROJECT}"\nversion = "{version}"\nsource = {{ editable = "." }}\n'
    )


def _tree(*, root: Path, pyproject: str, uv_lock: str) -> Path:
    """Materialize a two-file fixture tree and return its root."""
    _write(root=root, name="pyproject.toml", text=pyproject)
    _write(root=root, name="uv.lock", text=uv_lock)
    return root


def test_matching_versions_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lock whose self-entry equals the pyproject version stays green."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(),
        uv_lock=_uv_lock(entries=_self_entry(version="1.47.0")),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"in-sync versions should pass; stderr={result.stderr!r}"
    assert result.stdout == ""


def test_drifted_self_entry_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression: release-please bumped pyproject, the lock kept the old version."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(),
        uv_lock=_uv_lock(entries=_self_entry(version="1.46.0")),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"drifted self-entry should fail; stderr={result.stderr!r}"
    assert result.stdout == ""
    assert '"level": "error"' in combined
    assert "1.47.0" in combined, "the finding should name the pyproject version"
    assert "1.46.0" in combined, "the finding should name the locked version"
    assert "uv lock" in combined, "the finding should carry a remediation"


def test_missing_pyproject_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent `pyproject.toml` is a hard failure, not a vacuous pass."""
    _write(root=tmp_path, name="uv.lock", text=_uv_lock(entries=_self_entry(version="1.47.0")))
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"missing pyproject should fail; stderr={result.stderr!r}"
    assert "pyproject.toml" in result.stderr


def test_missing_uv_lock_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent `uv.lock` is a hard failure, not a vacuous pass."""
    _write(root=tmp_path, name="pyproject.toml", text=_pyproject())
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"missing uv.lock should fail; stderr={result.stderr!r}"
    assert "uv.lock" in result.stderr


def test_pyproject_without_project_table_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `pyproject.toml` carrying no `[project]` table cannot be compared."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(body='[tool.other]\nkey = "value"\n'),
        uv_lock=_uv_lock(entries=_self_entry(version="1.47.0")),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"no [project] table should fail; stderr={result.stderr!r}"
    assert '"level": "error"' in result.stderr


def test_pyproject_without_string_version_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `[project]` table whose `version` is absent (dynamic) cannot be compared."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(body=f'[project]\nname = "{_PROJECT}"\ndynamic = ["version"]\n'),
        uv_lock=_uv_lock(entries=_self_entry(version="1.47.0")),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"missing project version should fail; stderr={result.stderr!r}"
    assert '"level": "error"' in result.stderr


def test_uv_lock_without_package_array_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lock with no `[[package]]` array carries no self-entry to compare."""
    _ = _tree(root=tmp_path, pyproject=_pyproject(), uv_lock="version = 1\nrevision = 3\n")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"no package array should fail; stderr={result.stderr!r}"
    assert _PROJECT in result.stderr


def test_uv_lock_non_table_package_entry_is_skipped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `package` array of non-tables yields no self-entry rather than crashing."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(),
        uv_lock='version = 1\nrevision = 3\npackage = ["not-a-table"]\n',
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"non-table entries should fail; stderr={result.stderr!r}"
    assert _PROJECT in result.stderr


def test_only_the_editable_entry_counts_as_the_self_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unrelated packages, a sourceless entry, and a same-named registry entry are all skipped."""
    decoys = (
        '[[package]]\nname = "attrs"\nversion = "26.1.0"\nsource = { registry = "u" }\n\n'
        f'[[package]]\nname = "{_PROJECT}"\nversion = "0.0.1"\n\n'
        f'[[package]]\nname = "{_PROJECT}"\nversion = "0.0.2"\nsource = {{ registry = "u" }}\n\n'
    )
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(),
        uv_lock=_uv_lock(entries=decoys + _self_entry(version="1.47.0")),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"decoy entries should be skipped; stderr={result.stderr!r}"


def test_self_entry_without_string_version_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An editable self-entry whose `version` is not a string cannot be compared."""
    _ = _tree(
        root=tmp_path,
        pyproject=_pyproject(),
        uv_lock=_uv_lock(
            entries=(
                f'[[package]]\nname = "{_PROJECT}"\nversion = 1\nsource = {{ editable = "." }}\n'
            )
        ),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"non-string version should fail; stderr={result.stderr!r}"
    assert _PROJECT in result.stderr


def test_this_repo_is_in_sync(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The committed tree satisfies its own invariant — the acceptance case for this fix."""
    result = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"this repo should be in sync; stderr={result.stderr!r}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
