"""Fail closed when a ShellCheck pin is projected without its enforcing gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path

__all__: list[str] = ["main"]


_MISE_FILE = Path(".mise.toml")
_JUSTFILE = Path("justfile")
_CI_YML = Path(".github") / "workflows" / "ci.yml"
# Every place the fleet declares its `just check` aggregate target list, by
# MEASUREMENT across all nine repos rather than by one repo's shape:
#   inline justfile targets                                     7 repos
#   .github/scripts/check.sh `targets=()`                       livespec-runtime
#   check-targets.txt, read line-by-line by an aggregate script livespec-driver-codex
# Reading only the justfile reported the latter two as unwired. Because this
# gate runs inside the bump-pin fanout, that FALSE failure blocked every pin
# bump into both of them (livespec-dev-tooling-62jh).
#
# The driver-codex case is why the search is over DECLARATION SITES rather
# than over delegating scripts: dev-tooling/check-aggregate.sh contains no
# target names at all, so searching the script the recipe invokes would still
# have missed it.
_AGGREGATE_SOURCES: tuple[Path, ...] = (
    Path("justfile"),
    Path(".github") / "scripts" / "check.sh",
    Path("check-targets.txt"),
)
_SHELLCHECK_PIN = re.compile(r"^shellcheck\s*=", re.MULTILINE)
_SHELL_QUALITY_TARGET = re.compile(r"^[ \t]*check-shell-quality[ \t]*$", re.MULTILINE)
_SHELL_QUALITY_RECIPE = re.compile(r"^check-shell-quality([ \t][^:]*)?:", re.MULTILINE)


def _has_shellcheck_pin(*, mise_text: str) -> bool:
    """Return True when `.mise.toml` carries a ShellCheck tool pin."""
    return _SHELLCHECK_PIN.search(mise_text) is not None


def _source_text(*, path: Path) -> str:
    """Return an aggregate declaration site's text, or empty when absent.

    Absent is the COMMON case, not an error: each repo carries exactly one of
    these layouts, so the other two are expected to be missing and simply
    contribute no targets.
    """
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _declares_aggregate_target() -> bool:
    """Return True when ANY declaration site lists check-shell-quality."""
    return any(
        _SHELL_QUALITY_TARGET.search(_source_text(path=path)) is not None
        for path in _AGGREGATE_SOURCES
    )


def _searched_locations() -> str:
    """Render the declaration sites searched, for the failure diagnostic."""
    return ", ".join(path.as_posix() for path in _AGGREGATE_SOURCES)


def _missing_wiring() -> tuple[str, ...]:
    """Inspect cwd and return every missing ShellCheck enforcement surface.

    The AGGREGATE TARGET may be declared at any site in `_AGGREGATE_SOURCES`;
    all three spellings mean the same thing — `just check` runs
    check-shell-quality. The RECIPE is always the justfile's, because a
    delegated aggregate NAMES targets and does not define them, so only the
    target lookup is widened.
    """
    missing: list[str] = []
    if not _declares_aggregate_target():
        # The leading phrase is kept verbatim from before the multi-layout
        # widening: it is the string operators grep for and the one the
        # existing fail-closed control asserts. The parenthetical is what
        # makes it honest now that the target may legitimately be declared
        # somewhere other than the justfile.
        missing.append(
            "justfile aggregate target check-shell-quality " f"(searched: {_searched_locations()})"
        )
    if _SHELL_QUALITY_RECIPE.search(_JUSTFILE.read_text(encoding="utf-8")) is None:
        missing.append("check-shell-quality recipe")
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
