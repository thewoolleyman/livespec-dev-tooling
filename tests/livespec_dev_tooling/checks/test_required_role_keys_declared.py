"""Tests for `required_role_keys_declared`."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from livespec_dev_tooling.config import REQUIRED_ROLE_KEYS

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "required_role_keys_declared.py"


def _load_check() -> ModuleType:
    assert _CHECK.is_file(), "required_role_keys_declared check module must exist"
    spec = importlib.util.spec_from_file_location(
        "required_role_keys_declared_under_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_check(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    module = _load_check()
    monkeypatch.chdir(root)
    rc = module.main()
    captured = capsys.readouterr()
    records = [
        json.loads(line)
        for line in (captured.out + captured.err).splitlines()
        if line.strip().startswith("{")
    ]
    return rc, records


def _write_justfile(*, root: Path, targets: tuple[str, ...]) -> None:
    lines = "\n".join(f"        {target}" for target in targets)
    _ = (root / "justfile").write_text(
        "check:\n" "    #!/usr/bin/env bash\n" "    targets=(\n" f"{lines}\n" "    )\n",
        encoding="utf-8",
    )


# The two role keys whose TOML spelling is a scalar rather than an array. Named
# explicitly rather than inferred from `Config.__dataclass_fields__` defaults:
# the union (livespec-dev-tooling-8o8e.1) made those defaults `LegacyAmbiguousEmpty`
# for every key, so a `default is None` test silently emitted `[]` for the scalars
# and produced a block that no longer parses.
_SCALAR_SPELLED_ROLE_KEYS = frozenset({"dataclasses_tree", "neutral_hook_body_path"})


def _all_required_empty_block() -> str:
    lines = ["[tool.livespec_dev_tooling]"]
    for key in sorted(REQUIRED_ROLE_KEYS):
        value = '""' if key in _SCALAR_SPELLED_ROLE_KEYS else "[]"
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def test_layout_dependent_wiring_missing_one_role_key_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(root=tmp_path, targets=("check-no-inheritance",))
    missing_key = sorted(REQUIRED_ROLE_KEYS)[0]
    pyproject = _all_required_empty_block().replace(f"{missing_key} = []\n", "")
    _ = (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1
    assert any(record.get("missing_keys") == [missing_key] for record in records)
    assert any("declare the real value" in str(record.get("event")) for record in records)


def test_declared_empty_required_role_keys_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(root=tmp_path, targets=("check-no-inheritance",))
    _ = (tmp_path / "pyproject.toml").write_text(_all_required_empty_block(), encoding="utf-8")

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert not [record for record in records if record.get("level") == "error"]


def test_layout_independent_wiring_is_named_exclusion(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(
        root=tmp_path,
        targets=(
            "check-plugin-resolution",
            "check-primary-checkout-commit-refuse-hook-installed",
        ),
    )

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert any(
        record.get("status") == "excluded"
        and "no layout-dependent checks wired" in str(record.get("reason"))
        for record in records
    )
