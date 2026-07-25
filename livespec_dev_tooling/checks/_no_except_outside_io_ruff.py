"""Ruff BLE001 backstop probes for no_except_outside_io."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = ["find_ruff_backstop_gaps"]

_RUFF_BLE001_SETTING = "blind-except (BLE001)"
_RUFF_EXCLUDED_REASON = "inspected file is excluded from Ruff; BLE001 backstop is absent"
_RUFF_NO_BLE_REASON = "Ruff lint select does not enable BLE/BLE001 for inspected file"


def _explicit_ruff_lint_select_configured(*, repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    text = pyproject.read_text(encoding="utf-8")
    return "[tool.ruff.lint]" in text and "select" in text


def _ruff_show_files(*, repo_root: Path, source_trees: tuple[Path, ...]) -> frozenset[Path]:
    result = subprocess.run(
        ["ruff", "check", "--show-files", "--force-exclude", *(str(path) for path in source_trees)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    resolved_root = repo_root.resolve()
    out: set[Path] = set()
    for line in result.stdout.splitlines():
        out.add(Path(line).resolve().relative_to(resolved_root))
    return frozenset(out)


def _ruff_enables_ble001(*, repo_root: Path, rel_path: Path) -> bool:
    result = subprocess.run(
        ["ruff", "check", "--show-settings", str(rel_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and _RUFF_BLE001_SETTING in result.stdout


def find_ruff_backstop_gaps(
    *, repo_root: Path, source_trees: tuple[Path, ...], inspected_files: tuple[Path, ...]
) -> list[tuple[Path, str]]:
    """Return inspected files that Ruff will not lint with BLE001 enabled."""
    if not _explicit_ruff_lint_select_configured(repo_root=repo_root):
        return []
    ruff_files = _ruff_show_files(repo_root=repo_root, source_trees=source_trees)
    gaps: list[tuple[Path, str]] = []
    for rel_path in inspected_files:
        if rel_path not in ruff_files:
            gaps.append((rel_path, _RUFF_EXCLUDED_REASON))
        elif not _ruff_enables_ble001(repo_root=repo_root, rel_path=rel_path):
            gaps.append((rel_path, _RUFF_NO_BLE_REASON))
    return gaps
