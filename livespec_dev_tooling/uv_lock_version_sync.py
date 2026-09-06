"""uv_lock_version_sync — `uv.lock`'s self-entry version tracks `pyproject.toml`.

release-please bumps `[project].version` in `pyproject.toml` when it cuts a
release. `uv.lock` carries its OWN copy of that number, in the `[[package]]`
entry whose `source` is `{ editable = "." }`, and nothing re-resolves the lock
as part of the release commit. The two therefore drift apart the moment a
release merges, and the FIRST `uv` invocation in any checkout — a `uv run`, a
`just` recipe, a lefthook hook — silently reconciles the lock and leaves the
working tree dirty before a single edit has been made.

That is not merely cosmetic. A tree that is dirty on arrival trains every
contributor and every agent to ignore dirty state, which is precisely the habit
that hides a REAL stray edit; it produces spurious "uncommitted change"
warnings at `gh pr create`; and it invites the lock churn to be swept into an
unrelated PR's diff, which is how unrelated changes ride along unnoticed.

The PREVENTION lives in `release-please-config.json`: an `extra-files` entry
rewrites the lock's self-entry version inside the release commit itself, so
master is never in the drifted state. This check is the BACKSTOP for that
prevention rather than a substitute for it. The failure mode it exists to catch
is a silent one: release-please's TOML updater resolves its JSONPath against a
parsed document whose scalars are TAGGED (`{start, end, value}`) rather than
bare, so the filter must match on `@.name.value`, not `@.name`. Get that wrong
— or rename the package — and the updater logs `No entries modified` and
returns the file UNCHANGED. Nothing fails; the drift simply resumes. With this
check wired, that regression surfaces on the release PR instead of being
absorbed into every subsequent checkout.

Scope is deliberately narrow: the self-entry version ONLY. Proving the whole
lock still resolves is `uv lock --check`'s job and needs the network; this
check reads two committed files and nothing else, so it is safe in any venue.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in `livespec_dev_tooling/**`. Diagnostics
flow through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor` is added to `sys.path` at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
import tomli  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_PYPROJECT_PATH = Path("pyproject.toml")
_UV_LOCK_PATH = Path("uv.lock")

# The `source` value that marks a lock entry as the project's OWN entry, as
# opposed to a same-named package resolved from a registry.
_EDITABLE_ROOT = "."

_REMEDIATION = (
    "run `uv lock` and commit the result. If this fired on a release PR, the "
    "release-please-config.json `extra-files` entry for uv.lock stopped matching — its "
    'JSONPath filters on the TAGGED scalar (`$.package[?(@.name.value=="<name>")].version`), '
    "and a non-matching path is a silent no-op. Repair that entry rather than hand-editing "
    "the lock, or master re-drifts at the next release."
)


def _string_field(*, table: dict[str, object], key: str) -> str | None:
    """The `key` entry of `table` when it is a string, else None."""
    value = table.get(key)
    return value if isinstance(value, str) else None


def _sub_table(*, table: dict[str, object], key: str) -> dict[str, object] | None:
    """The `key` entry of `table` when it is itself a table, else None."""
    value = table.get(key)
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _project_identity(*, pyproject_text: str) -> tuple[str, str] | None:
    """The `[project]` table's `(name, version)` pair, or None when either is absent.

    A `dynamic = ["version"]` project has no static version to compare, so it
    reads as absent rather than as a match.
    """
    document = cast("dict[str, object]", tomli.loads(pyproject_text))
    project = _sub_table(table=document, key="project")
    if project is None:
        return None
    name = _string_field(table=project, key="name")
    version = _string_field(table=project, key="version")
    if name is None or version is None:
        return None
    return (name, version)


def _locked_self_version(*, uv_lock_text: str, project_name: str) -> str | None:
    """The version `uv.lock` records for the project's OWN editable entry.

    Returns None when the lock carries no `[[package]]` array, no entry naming
    this project with an `editable` source, or an entry whose `version` is not
    a string. Matching on the editable source (not the name alone) keeps a
    same-named registry package from being mistaken for the self-entry.
    """
    packages = cast("dict[str, object]", tomli.loads(uv_lock_text)).get("package")
    if not isinstance(packages, list):
        return None
    for entry in cast("list[object]", packages):
        if not isinstance(entry, dict):
            continue
        package = cast("dict[str, object]", entry)
        source = _sub_table(table=package, key="source")
        if _string_field(table=package, key="name") != project_name or source is None:
            continue
        if _string_field(table=source, key="editable") != _EDITABLE_ROOT:
            continue
        return _string_field(table=package, key="version")
    return None


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("uv_lock_version_sync")
    cwd = Path.cwd()
    pyproject_path = cwd / _PYPROJECT_PATH
    uv_lock_path = cwd / _UV_LOCK_PATH
    missing = [path for path in (pyproject_path, uv_lock_path) if not path.is_file()]
    if missing:
        for path in missing:
            log.error(
                "uv lock version-sync input file missing",
                file=str(path.relative_to(cwd)),
            )
        return 1
    identity = _project_identity(pyproject_text=pyproject_path.read_text(encoding="utf-8"))
    if identity is None:
        log.error(
            "pyproject.toml declares no static [project] name/version to compare",
            file=str(_PYPROJECT_PATH),
            remediation=_REMEDIATION,
        )
        return 1
    project_name, declared_version = identity
    locked_version = _locked_self_version(
        uv_lock_text=uv_lock_path.read_text(encoding="utf-8"),
        project_name=project_name,
    )
    if locked_version is None:
        log.error(
            "uv.lock carries no editable self-entry for the project",
            package=project_name,
            file=str(_UV_LOCK_PATH),
            remediation=_REMEDIATION,
        )
        return 1
    if locked_version != declared_version:
        log.error(
            "uv.lock self-entry version disagrees with the pyproject version",
            package=project_name,
            pyproject_version=declared_version,
            uv_lock_version=locked_version,
            remediation=_REMEDIATION,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
