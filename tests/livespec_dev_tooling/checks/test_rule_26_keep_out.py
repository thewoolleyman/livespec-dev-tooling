"""Scenario coverage for the Rule-26 mutation kill-matrix keep-out guard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "rule_26_keep_out.py"


def _load_check() -> ModuleType:
    """Load the on-disk check module after the Red existence assertion."""
    spec = importlib.util.spec_from_file_location("rule_26_keep_out_under_test", str(_CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_check(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    module = _load_check()
    monkeypatch.chdir(root)
    result = module.main()
    captured = capsys.readouterr()
    records = [
        json.loads(line)
        for line in (captured.out + captured.err).splitlines()
        if line.strip().startswith("{")
    ]
    return result, records


@pytest.mark.integration
def test_reachable_mutation_kill_matrix_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A transitive aggregate dependency is a keep-out violation."""
    assert _CHECK.is_file(), "the Rule-26 keep-out guard must ship as a shared check"
    _ = (tmp_path / "justfile").write_text(
        "check: check-fast\n"
        "check-fast: mutation-kill-matrix\n"
        "mutation-kill-matrix:\n"
        "    echo matrix\n",
        encoding="utf-8",
    )

    result, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result != 0
    assert any(
        record.get("recipe") == "mutation-kill-matrix" and record.get("aggregate") == "just check"
        for record in records
    )


def test_unreachable_mutation_kill_matrix_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An on-demand mutation recipe outside `check` remains permitted."""
    assert _CHECK.is_file(), "the Rule-26 keep-out guard must ship as a shared check"
    _ = (tmp_path / "justfile").write_text(
        "check: check-fast\n"
        "check-fast:\n"
        "    echo fast\n"
        "mutation-kill-matrix:\n"
        "    echo matrix\n",
        encoding="utf-8",
    )

    result, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 0
    assert not records


def test_target_array_member_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fleet aggregate's ``targets`` array is also a reachability edge."""
    assert _CHECK.is_file(), "the Rule-26 keep-out guard must ship as a shared check"
    _ = (tmp_path / "justfile").write_text(
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    targets=(\n"
        "        mutation-kill-matrix\n"
        "    )\n",
        encoding="utf-8",
    )

    result, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result != 0
    assert any(record.get("recipe") == "mutation-kill-matrix" for record in records)


def test_missing_justfile_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository without an aggregate has no mutation recipe to keep out."""
    assert _CHECK.is_file(), "the Rule-26 keep-out guard must ship as a shared check"

    result, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 0
    assert not records
