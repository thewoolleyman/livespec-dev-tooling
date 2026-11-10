"""Regression guards for counted pipefail readers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_sweep_module() -> ModuleType:
    """Load the sweep helper from the same source its own tests exercise."""
    path = _REPO_ROOT / "tests" / "test_pipefail_reader_sweep.py"
    spec = importlib.util.spec_from_file_location("pipefail_reader_sweep", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _early_reader_violations(*, paths: tuple[Path, ...], repo_root: Path) -> tuple[str, ...]:
    """Run the sweep helper through its normal module boundary."""
    module = _load_sweep_module()
    return module.__dict__["_early_reader_violations"](paths=paths, repo_root=repo_root)


def test_pipefail_sweep_reports_every_counted_early_reader(tmp_path: Path) -> None:
    """Counted grep and head readers must name every unsafe pipeline line."""
    unsafe_script = tmp_path / "scripts" / "unsafe.sh"
    unsafe_script.parent.mkdir()
    unsafe_script.write_text(
        "#!/usr/bin/env bash\nset -o pipefail\n"
        "printf 'needle\\n' | grep -m 2 needle\n"
        "printf 'needle\\n' | grep -m2 needle\n"
        "printf 'needle\\n' | head -n 2\n"
        "printf 'needle\\n' | head -n2\n"
        "printf 'needle\\n' | head -2\n"
        "printf 'needle\\n' | head -c 2\n"
        "printf 'needle\\n' | head -c2\n",
        encoding="utf-8",
    )

    assert _early_reader_violations(paths=(unsafe_script,), repo_root=tmp_path) == (
        "scripts/unsafe.sh:3: printf 'needle\\n' | grep -m 2 needle",
        "scripts/unsafe.sh:4: printf 'needle\\n' | grep -m2 needle",
        "scripts/unsafe.sh:5: printf 'needle\\n' | head -n 2",
        "scripts/unsafe.sh:6: printf 'needle\\n' | head -n2",
        "scripts/unsafe.sh:7: printf 'needle\\n' | head -2",
        "scripts/unsafe.sh:8: printf 'needle\\n' | head -c 2",
        "scripts/unsafe.sh:9: printf 'needle\\n' | head -c2",
    )


def test_pipefail_sweep_ignores_counted_reader_text_inside_a_grep_pattern(tmp_path: Path) -> None:
    """A quoted grep pattern can contain a mode-like string without being an option."""
    safe_script = tmp_path / "scripts" / "safe.sh"
    safe_script.parent.mkdir()
    safe_script.write_text(
        "#!/usr/bin/env bash\nset -o pipefail\nprintf 'mode -m 0755\\n' | grep -E '-m 0755'\n",
        encoding="utf-8",
    )

    assert _early_reader_violations(paths=(safe_script,), repo_root=tmp_path) == ()
