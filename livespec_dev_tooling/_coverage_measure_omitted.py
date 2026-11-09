"""A coverage configuration that still measures touched files the `omit` list excludes."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from coverage.files import GlobMatcher

from livespec_dev_tooling._isolated_coverage import COVERAGE_CONFIG

# stdlib `tomllib` lands in 3.11; the repo floor is 3.10, so fall back to the
# vendored `tomli`, which exposes an identical `loads(text) -> dict`.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = ["measuring_config"]

_RUN_OMIT = "omit"


def _excludes(*, repo_root: Path, pattern: str, path: str) -> bool:
    """Match `pattern`, and the pattern made absolute under the repo, against `path`."""
    return GlobMatcher([pattern, str(repo_root / pattern)]).match(path)


def measuring_config(*, repo_root: Path, names: Iterable[str], folder: Path) -> str:
    """Return the coverage config to measure `names` under.

    That is the repository's own configuration, unchanged, unless one of its
    `omit` patterns excludes a named file: coverage would then record no row for
    it, which reads as zero coverage. In that case return a copy in `folder`
    whose `omit` drops only the patterns that exclude a named file.
    """
    source = repo_root / COVERAGE_CONFIG
    document = _toml.loads(source.read_text(encoding="utf-8"))
    coverage = cast("dict[str, dict[str, Any]]", document.get("tool", {}).get("coverage", {}))
    omit = cast("list[str]", coverage.get("run", {}).get(_RUN_OMIT, []))
    paths = [str((repo_root / name).resolve()) for name in names]
    kept = [
        pattern
        for pattern in omit
        if not any(_excludes(repo_root=repo_root, pattern=pattern, path=path) for path in paths)
    ]
    if kept == omit:
        return COVERAGE_CONFIG
    coverage["run"][_RUN_OMIT] = kept
    lines = [
        line
        for section, table in coverage.items()
        for line in (
            f"[tool.coverage.{section}]",
            *(f"{json.dumps(key)} = {json.dumps(value)}" for key, value in table.items()),
        )
    ]
    target = folder / "coverage-measuring-omitted.toml"
    _ = target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)
