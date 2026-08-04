"""Fail closed when a ShellCheck pin is projected without its enforcing gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path

__all__: list[str] = ["main"]


_MISE_FILE = Path(".mise.toml")
_JUSTFILE = Path("justfile")
_CI_YML = Path(".github") / "workflows" / "ci.yml"
_SHELLCHECK_PIN = re.compile(r"^shellcheck\s*=", re.MULTILINE)
_SHELL_QUALITY_TARGET = re.compile(r"^[ \t]*check-shell-quality[ \t]*$", re.MULTILINE)
_SHELL_QUALITY_RECIPE = re.compile(r"^check-shell-quality([ \t][^:]*)?:", re.MULTILINE)


def _has_shellcheck_pin(*, mise_text: str) -> bool:
    """Return True when `.mise.toml` carries a ShellCheck tool pin."""
    return _SHELLCHECK_PIN.search(mise_text) is not None


def _missing_justfile_wiring(*, justfile_text: str) -> tuple[str, ...]:
    """Return missing justfile surfaces for the check-shell-quality gate."""
    missing: list[str] = []
    if _SHELL_QUALITY_TARGET.search(justfile_text) is None:
        missing.append("justfile aggregate target check-shell-quality")
    if _SHELL_QUALITY_RECIPE.search(justfile_text) is None:
        missing.append("check-shell-quality recipe")
    return tuple(missing)


def _missing_wiring() -> tuple[str, ...]:
    """Inspect cwd and return every missing ShellCheck enforcement surface."""
    missing = list(_missing_justfile_wiring(justfile_text=_JUSTFILE.read_text(encoding="utf-8")))
    if "check-shell-quality" not in _CI_YML.read_text(encoding="utf-8"):
        missing.append("CI check-shell-quality job or matrix target")
    return tuple(missing)


def _emit(*, annotation: str, message: str) -> None:
    """Write a GitHub Actions annotation."""
    _ = sys.stdout.write(f"::{annotation}::{message}\n")


def main() -> int:
    """Require every ShellCheck-pinned consumer to wire check-shell-quality."""
    if not _MISE_FILE.is_file() or not _has_shellcheck_pin(
        mise_text=_MISE_FILE.read_text(encoding="utf-8")
    ):
        _emit(
            annotation="notice",
            message=(
                "no ShellCheck pin present after tool-pin projection; "
                "skipping check-shell-quality invariant"
            ),
        )
        return 0

    missing = _missing_wiring()
    if missing:
        detail = "".join(f" {surface};" for surface in missing)
        _emit(
            annotation="error",
            message=(
                "ShellCheck pin is present but check-shell-quality is not fully wired; "
                f"missing:{detail}"
            ),
        )
        return 1

    _emit(annotation="notice", message="ShellCheck pin is gated by check-shell-quality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
