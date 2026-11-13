"""Tests for the aggregate guard on Ansible-driving test modules."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from livespec_dev_tooling.agent_hooks._foreground_pytest import _is_gate_job_only_pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "ansible_test_gate_job_only.py"


def _module() -> ModuleType:
    """Import the check only after its existence assertion has made Red genuine."""
    return importlib.import_module("livespec_dev_tooling.ansible_test_gate_job_only")


def _tree(*, root: Path, declaration: str) -> Path:
    """Create a minimal configured repository with two test modules."""
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" + declaration,
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    marker = "ansible" + "-playbook"
    _ = (tests / "test_declared.py").write_text(f'COMMAND = "{marker}"\n', encoding="utf-8")
    _ = (tests / "test_plain.py").write_text(
        "def test_plain() -> None:\n    pass\n", encoding="utf-8"
    )
    return root


def test_the_check_exists_and_accepts_a_declaration_covering_every_matching_module(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The aggregate passes only when every Ansible-driving module has a glob."""
    assert _MODULE_PATH.is_file()
    root = _tree(root=tmp_path, declaration='gate_job_only_tests = ["tests/test_declared.py"]\n')
    monkeypatch.chdir(root)

    assert _module().main() == 0


def test_the_check_names_an_unmatched_ansible_driving_test_module(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An uncovered module is a check failure with its repository-relative name."""
    assert _MODULE_PATH.is_file()
    root = _tree(root=tmp_path, declaration="gate_job_only_tests = []\n")
    monkeypatch.chdir(root)

    module = _module()
    assert module.undeclared_gate_job_only_modules(repo_root=root) == ("tests/test_declared.py",)
    assert module.main() == 1


def test_this_repository_declares_every_ansible_driving_test_module() -> None:
    """The existing pytest aggregate checks the real repository declaration."""
    assert _module().undeclared_gate_job_only_modules(repo_root=_REPO_ROOT) == ()


def test_gate_only_classifier_handles_options_directories_and_missing_node_ids(
    *, tmp_path: Path
) -> None:
    """Only real selected test modules matching a declared glob trigger the refusal."""
    root = _tree(root=tmp_path, declaration='gate_job_only_tests = ["tests/test_*.py"]\n')

    assert _is_gate_job_only_pytest(
        pytest_argv=("pytest", "--ignore", "ignored", "tests/test_declared.py"), cwd=root
    )
    assert _is_gate_job_only_pytest(pytest_argv=("pytest", "tests"), cwd=root)
    assert not _is_gate_job_only_pytest(pytest_argv=("pytest", "--quiet"), cwd=root)
    assert not _is_gate_job_only_pytest(
        pytest_argv=("pytest", "missing.py::test_missing"), cwd=root
    )

    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ngate_job_only_tests = ["tests/test_other.py"]\n',
        encoding="utf-8",
    )
    assert not _is_gate_job_only_pytest(pytest_argv=("pytest", "tests/test_declared.py"), cwd=root)
