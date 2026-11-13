"""Outside-in coverage for the consumer dev-tooling import declaration check."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.config import load_config

__all__: list[str] = []


_CONFIG_API_CONSUMERS = {
    "load_delegated_gate": (
        "livespec-orchestrator-beads-fabro's tests/integration/test_delegated_pre_push_gate.py",
        "livespec-driver-claude's tests/hooks/test_check_pre_push_delegation.py",
        "livespec-overseer's tests/test_pre_push_delegated_gate.py",
        "livespec's tests/test_delegated_pre_push_gate_wiring.py",
        "livespec-orchestrator-git-jsonl's tests/integration/test_pre_push_delegated_gate.py",
    ),
    "load_delegated_pre_commit": (
        "livespec-orchestrator-beads-fabro's tests/test_delegated_pre_commit.py",
        "livespec-driver-claude's tests/hooks/test_delegated_pre_commit.py",
        "livespec-overseer's tests/test_pre_commit_gate_shape.py",
        "livespec's tests/test_delegated_pre_commit_wiring.py",
        "livespec-driver-codex's tests/integration/test_delegated_pre_commit.py",
    ),
    "load_gate_check_suite": (
        "livespec-orchestrator-beads-fabro's tests/integration/test_delegated_pre_push_gate.py",
        "livespec-orchestrator-beads-fabro's tests/test_delegated_pre_commit.py",
        "livespec-driver-claude's tests/hooks/test_delegated_pre_commit.py",
        "livespec-overseer's tests/test_pre_commit_gate_shape.py",
    ),
    "load_config": (
        "livespec-orchestrator-beads-fabro's .claude/hooks/livespec_tdd_order_guard.py",
        "livespec-orchestrator-beads-fabro's tests/integration/test_incident_lifecycle_walk.py",
    ),
    "derive_source_prefixes": (
        "livespec-orchestrator-beads-fabro's .claude/hooks/livespec_tdd_order_guard.py",
        "livespec-orchestrator-beads-fabro's tests/integration/test_incident_lifecycle_walk.py",
    ),
    "is_vendored_path": (
        "livespec-orchestrator-beads-fabro's .claude/hooks/livespec_tdd_order_policy.py",
    ),
    "iter_first_party_py_files": (
        "livespec-orchestrator-git-jsonl's tests/test_no_buffer_write_dodge.py",
    ),
}


_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)


def _git(*, repo: Path, args: list[str]) -> None:
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV_VARS}
    subprocess.run(["git", *args], cwd=repo, check=True, env=env)


def _consumer(*, tmp_path: Path, test_body: str, product_body: str = "") -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["config", "user.name", "Test"])
    (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ntests_tree_prefix = "tests/"\n',
        encoding="utf-8",
    )
    (repo / "pkg").mkdir()
    (repo / "pkg" / "local.py").write_text(product_body, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_imports.py").write_text(test_body, encoding="utf-8")
    _git(repo=repo, args=["add", "."])
    _git(repo=repo, args=["commit", "-qm", "fixture"])
    return repo


def _run(
    *,
    repo: Path,
    fail: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    module = importlib.import_module(
        "livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared"
    )
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["dev-tooling-imports-declared"])
    if fail:
        monkeypatch.setenv("LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS", "1")
    else:
        monkeypatch.delenv("LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS", raising=False)
    return module.main(), capsys.readouterr().err


def test_undeclared_direct_import_warns_or_refuses_with_its_site_and_definition(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _consumer(
        tmp_path=tmp_path,
        product_body='raise RuntimeError("consumer code must not execute")\n',
        test_body="from livespec_dev_tooling.incident_release_entry import screen\n\nscreen()\n",
    )
    warning, warning_text = _run(repo=repo, fail=False, monkeypatch=monkeypatch, capsys=capsys)
    refusal, refusal_text = _run(repo=repo, fail=True, monkeypatch=monkeypatch, capsys=capsys)
    assert warning == 0
    assert refusal == 4
    assert '"level": "warning"' in warning_text
    assert '"level": "error"' in refusal_text
    for output in (warning_text, refusal_text):
        assert "tests/test_imports.py" in output
        assert "line" in output
        assert "livespec_dev_tooling/incident_release_entry.py" in output
        assert "screen" in output


def test_empty_fail_variable_warns_without_refusing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _consumer(
        tmp_path=tmp_path,
        test_body="from livespec_dev_tooling.incident_release_entry import screen\n\nscreen()\n",
    )
    module = importlib.import_module(
        "livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared"
    )
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["dev-tooling-imports-declared"])
    monkeypatch.setenv("LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS", "")

    result = module.main()

    assert result == 0
    assert '"level": "warning"' in capsys.readouterr().err


def test_declared_local_public_and_private_reaches_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _consumer(
        tmp_path=tmp_path,
        product_body=(
            "from livespec_dev_tooling.check_purity import audit_check_purity\n\n"
            "def use_local_public() -> None:\n    audit_check_purity()\n"
        ),
        test_body=(
            "from livespec_dev_tooling.green_token import main\n"
            "from livespec_dev_tooling.check_purity import audit_check_purity, _private\n\n"
            "main()\naudit_check_purity()\n_private()\n"
        ),
    )
    result, output = _run(repo=repo, fail=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result == 0, output


def test_declared_config_api_imports_pass_in_a_consumer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The released config API surface covers every fleet-consumed helper."""
    repo = _consumer(
        tmp_path=tmp_path,
        test_body=(
            "from livespec_dev_tooling.config import (\n"
            "    derive_source_prefixes,\n"
            "    is_vendored_path,\n"
            "    iter_first_party_py_files,\n"
            "    load_config,\n"
            "    load_delegated_gate,\n"
            "    load_delegated_pre_commit,\n"
            "    load_gate_check_suite,\n"
            ")\n"
        ),
    )

    result, output = _run(repo=repo, fail=True, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 0, output


def test_config_api_consumers_are_declared_with_their_import_sites() -> None:
    """Every fleet-consumed config helper names its consuming files."""
    root = Path(__file__).resolve().parents[3]
    declarations = {
        entry.function: entry.reason
        for entry in load_config(repo_root=root).cross_repo_public_api
        if entry.file.as_posix() == "livespec_dev_tooling/config.py"
    }

    assert set(declarations) == set(_CONFIG_API_CONSUMERS)
    for function, consuming_files in _CONFIG_API_CONSUMERS.items():
        for consuming_file in consuming_files:
            assert consuming_file in declarations[function]


def test_module_attribute_reach_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _consumer(
        tmp_path=tmp_path,
        test_body=(
            "from livespec_dev_tooling import incident_release_entry\n\n"
            "incident_release_entry.screen()\n"
        ),
    )
    result, output = _run(repo=repo, fail=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result == 4
    assert "tests/test_imports.py" in output
    assert "livespec_dev_tooling/incident_release_entry.py" in output
    assert "screen" in output


def test_generated_installed_file_does_not_make_an_import_locally_public(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    package = tmp_path / "installed" / "livespec_dev_tooling"
    (package / "workflow_checks").mkdir(parents=True)
    (package / "data").mkdir()
    (package / "data" / "cross_repo_public_api.json").write_text("[]", encoding="utf-8")
    (package / "hidden.py").write_text("def hidden() -> None:\n    pass\n", encoding="utf-8")
    (package / "generated_user.py").write_text(
        "# @generated\nfrom livespec_dev_tooling.hidden import hidden\n\nhidden()\n",
        encoding="utf-8",
    )
    repo = _consumer(
        tmp_path=tmp_path,
        test_body="from livespec_dev_tooling.hidden import hidden\n\nhidden()\n",
    )
    module = importlib.import_module(
        "livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared"
    )
    monkeypatch.setattr(module, "__file__", str(package / "workflow_checks" / "check.py"))
    result, output = _run(repo=repo, fail=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result == 4, output
    assert "hidden" in output
