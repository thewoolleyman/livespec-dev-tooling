"""ROP sweep regressions for config-driven library checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS = _REPO_ROOT / "livespec_dev_tooling" / "checks"


def _load_check(*, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", str(_CHECKS / f"{name}.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_check(
    *,
    name: str,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    universe: tuple[Path, ...] | None = None,
) -> tuple[int, str]:
    module = _load_check(name=name)
    if universe is not None and hasattr(module, "resolve_check_universe"):
        monkeypatch.setattr(module, "resolve_check_universe", lambda: (root, universe))
    monkeypatch.chdir(root)
    rc = module.main()
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def test_supervisor_discipline_hard_fails_configured_consumer_source_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["consumer_pkg"]\n',
        encoding="utf-8",
    )
    package_dir = tmp_path / "consumer_pkg"
    package_dir.mkdir()
    (package_dir / "foo.py").write_text(
        "from __future__ import annotations\n"
        "import sys\n"
        "__all__: list[str] = []\n"
        "def quit_now() -> None:\n"
        "    sys.exit(0)\n",
        encoding="utf-8",
    )

    rc, combined = _run_check(
        name="supervisor_discipline",
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        universe=(Path("consumer_pkg/foo.py"),),
    )

    assert rc != 0
    assert "consumer_pkg/foo.py" in combined


def test_main_guard_hard_fails_configured_consumer_plugin_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source_tree = ".claude-plugin/scripts/consumer_pkg"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.livespec_dev_tooling]\nsource_trees = ["{source_tree}"]\n',
        encoding="utf-8",
    )
    package_dir = tmp_path / source_tree
    package_dir.mkdir(parents=True)
    (package_dir / "foo.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "def main() -> int:\n"
        "    return 0\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )

    rc, combined = _run_check(
        name="main_guard",
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        universe=(Path(source_tree) / "foo.py",),
    )

    assert rc != 0
    assert f"{source_tree}/foo.py" in combined


def test_rop_pipeline_shape_hard_fails_configured_consumer_source_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["consumer_pkg"]\n',
        encoding="utf-8",
    )
    package_dir = tmp_path / "consumer_pkg"
    package_dir.mkdir()
    (package_dir / "foo.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "@rop_pipeline\n"
        "class Pipeline:\n"
        "    def run(self) -> int:\n"
        "        return 0\n"
        "    def also_run(self) -> int:\n"
        "        return 1\n",
        encoding="utf-8",
    )

    rc, combined = _run_check(
        name="rop_pipeline_shape",
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        universe=(Path("consumer_pkg/foo.py"),),
    )

    assert rc != 0
    assert "consumer_pkg/foo.py" in combined


def test_tests_mirror_pairing_uses_configured_consumer_mirror_pairing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'mirror_pairings = [{ source_tree = "consumer_pkg", test_tree = "tests/consumer_pkg" }]\n',
        encoding="utf-8",
    )
    package_dir = tmp_path / "consumer_pkg"
    package_dir.mkdir()
    (package_dir / "foo.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "def do_thing() -> int:\n"
        "    return 0\n",
        encoding="utf-8",
    )

    rc, combined = _run_check(
        name="tests_mirror_pairing", root=tmp_path, monkeypatch=monkeypatch, capsys=capsys
    )

    assert rc != 0
    assert "consumer_pkg/foo.py" in combined
    assert "tests/consumer_pkg/test_foo.py" in combined


def test_pbt_coverage_uses_configured_consumer_pure_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'pure_trees = ["consumer_pkg/parse"]\n'
        'mirror_pairings = [{ source_tree = "consumer_pkg", test_tree = "tests/consumer_pkg" }]\n',
        encoding="utf-8",
    )
    test_dir = tmp_path / "tests" / "consumer_pkg" / "parse"
    test_dir.mkdir(parents=True)
    (test_dir / "test_parser.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "def test_parser() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )

    rc, combined = _run_check(
        name="pbt_coverage_pure_modules",
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc != 0
    assert "tests/consumer_pkg/parse/test_parser.py" in combined


def test_check_mutation_noops_without_pure_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["consumer_pkg"]\npure_trees = { not_applicable = "consumer has no pure tree" }\n',
        encoding="utf-8",
    )
    module = _load_check(name="check_mutation")

    def fail_if_mutmut_runs(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("mutmut should not run without configured pure_trees")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_RUN_MUTATION", "true")
    monkeypatch.setattr(module.subprocess, "run", fail_if_mutmut_runs)

    rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert "pure_trees" in captured.out + captured.err


def test_source_trees_scoped_to_consumer_rejects_drifted_core_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_trees = [".claude-plugin/scripts/livespec"]\n'
        'commands_trees = [".claude-plugin/scripts/livespec/commands"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".claude-plugin" / "scripts" / "consumer_pkg").mkdir(parents=True)
    (tmp_path / ".claude-plugin" / "scripts" / "livespec" / "commands").mkdir(parents=True)

    rc, combined = _run_check(
        name="source_trees_scoped_to_consumer",
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc != 0
    assert ".claude-plugin/scripts/livespec" in combined
    assert "foreign_package" in combined
