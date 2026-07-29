"""Enforce complete role-key declarations for layout-dependent check consumers."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  -- vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.canonical_checks import canonical_check_slugs  # noqa: E402
from livespec_dev_tooling.config import (  # noqa: E402
    REQUIRED_ROLE_KEYS,
    UNION_ROLE_KEYS,
    ConfigParseError,
    load_config,
)

__all__: list[str] = [
    "MISSING_KEYS_EVENT",
    "RoleKeyDeclarationStatus",
    "classify_role_key_declarations",
    "layout_dependent_check_slugs",
    "main",
]


_CHECK_ID = "required_role_keys_declared"
_JUSTFILE_NAME = "justfile"
_CHECK_PREFIX = "check-"
_CHECKS_PACKAGE_DIR = Path(__file__).resolve().parent
_CHECK_RECIPE_HEADER = re.compile(r"^check:\s*$", re.MULTILINE)
_TARGETS_ARRAY_START = re.compile(r"^\s*targets=\(\s*$", re.MULTILINE)
_TARGETS_ARRAY_END = re.compile(r"^\s*\)\s*$")
_LOAD_CONFIG_MODULE = "livespec_dev_tooling.config"
# The remediation is read at the moment someone decides what to write, so it
# names every legal spelling inline rather than referring to one — the standard
# `config._spellings_hint` already sets. It MUST stay correct for BOTH key
# groups: `REQUIRED_ROLE_KEYS` spans the UNION keys, where a bare `[]` / `""` is
# the retired ambiguous spelling, AND the CLEAN keys, where it remains
# legitimate because emptiness there removes exemptions rather than files
# (SPECIFICATION v033 §"Clean role keys retain `[]`"). A blanket rewrite in
# either direction would be a new defect.
MISSING_KEYS_EVENT = (
    "required role keys missing -- declare the real value. For a UNION role key "
    f"({', '.join(sorted(UNION_ROLE_KEYS))}) the only other legal spelling is exactly one "
    "of the four declared-absent inline tables, each carrying a non-empty payload: "
    '{ not_applicable = "<reason>" }, { superseded_by = "<reason>" }, '
    '{ unarmed_until = "<ledger-id>" }, { convention_not_adopted = "<reason>" }. '
    'For every OTHER required key a bare [] (or "" for a scalar key) remains legitimate, '
    "because emptiness there makes the consuming check stricter rather than blinder"
)


class RoleKeyDeclarationStatus:
    """The declaration check result for one consumer justfile/config pair."""

    def __init__(
        self,
        *,
        wired_layout_dependent_checks: tuple[str, ...],
        missing_keys: tuple[str, ...],
        excluded_reason: str | None = None,
    ) -> None:
        self.wired_layout_dependent_checks = wired_layout_dependent_checks
        self.missing_keys = missing_keys
        self.excluded_reason = excluded_reason

    def is_excluded(self) -> bool:
        """True when the consumer wires no layout-dependent checks."""
        return self.excluded_reason is not None


def _slug_to_module_name(*, slug: str) -> str:
    return slug.removeprefix(_CHECK_PREFIX).replace("-", "_")


def _module_imports_load_config(*, path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != _LOAD_CONFIG_MODULE:
            continue
        for alias in node.names:
            if alias.name == "load_config":
                return True
    return False


def layout_dependent_check_slugs() -> tuple[str, ...]:
    """Canonical check slugs whose implementation imports `load_config`."""
    slugs: list[str] = []
    for slug in canonical_check_slugs():
        module_path = _CHECKS_PACKAGE_DIR / f"{_slug_to_module_name(slug=slug)}.py"
        if module_path.is_file() and _module_imports_load_config(path=module_path):
            slugs.append(slug)
    return tuple(slugs)


def _extract_check_recipe_body(*, justfile_text: str) -> str | None:
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return None
    lines = justfile_text[header_match.end() :].splitlines()
    body_lines: list[str] = []
    for raw in lines:
        if raw and not raw.startswith((" ", "	")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def _extract_targets_array_lines(*, recipe_body: str) -> list[str] | None:
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return None
    collected: list[str] = []
    closed = False
    for raw in recipe_body[start_match.end() :].splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            closed = True
            break
        collected.append(raw.strip())
    return collected if closed else None


def _wired_check_slugs(*, justfile_text: str) -> tuple[str, ...]:
    body = _extract_check_recipe_body(justfile_text=justfile_text)
    if body is None:
        return ()
    lines = _extract_targets_array_lines(recipe_body=body)
    if lines is None:
        return ()
    slugs: list[str] = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith(_CHECK_PREFIX):
            slugs.append(token)
    return tuple(slugs)


def classify_role_key_declarations(
    *, justfile_text: str, declared_keys: frozenset[str], layout_dependent: frozenset[str]
) -> RoleKeyDeclarationStatus:
    """Classify one consumer from its justfile wiring and declared config keys.

    `layout_dependent` is INJECTED rather than walked. Resolving it here would
    call `layout_dependent_check_slugs()`, which reads the filesystem, and that
    reach — invisible in this function's own body — is what ratified livespec
    v179 member 1 clause (d) disqualifies. Both callers already sit at an I/O
    boundary, so the walk belongs one frame out and this stays total.
    """
    wired = tuple(
        slug for slug in _wired_check_slugs(justfile_text=justfile_text) if slug in layout_dependent
    )
    if not wired:
        return RoleKeyDeclarationStatus(
            wired_layout_dependent_checks=(),
            missing_keys=(),
            excluded_reason="no layout-dependent checks wired",
        )
    return RoleKeyDeclarationStatus(
        wired_layout_dependent_checks=wired,
        missing_keys=tuple(sorted(REQUIRED_ROLE_KEYS - declared_keys)),
    )


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _status_for_repo(*, repo_root: Path) -> RoleKeyDeclarationStatus:
    justfile = repo_root / _JUSTFILE_NAME
    if not justfile.is_file():
        return RoleKeyDeclarationStatus(
            wired_layout_dependent_checks=(),
            missing_keys=(),
            excluded_reason="justfile not found; no check aggregate wired",
        )
    config = load_config(repo_root=repo_root)
    return classify_role_key_declarations(
        justfile_text=justfile.read_text(encoding="utf-8"),
        declared_keys=config.declared_keys,
        layout_dependent=frozenset(layout_dependent_check_slugs()),
    )


def _emit_status(*, status: RoleKeyDeclarationStatus, log: structlog.stdlib.BoundLogger) -> int:
    if status.is_excluded():
        log.info(
            "required role-key declaration check excluded",
            check_id=_CHECK_ID,
            status="excluded",
            reason=status.excluded_reason,
        )
        return 0
    if status.missing_keys:
        log.error(
            MISSING_KEYS_EVENT,
            check_id=_CHECK_ID,
            status="fail",
            missing_keys=status.missing_keys,
            wired_layout_dependent_checks=status.wired_layout_dependent_checks,
        )
        return 1
    return 0


def main() -> int:
    """CLI entry point for the repo-local required-role-key declaration check."""
    log = _configure_logger()
    try:
        status = _status_for_repo(repo_root=Path.cwd())
    except ConfigParseError as exc:
        log.exception(
            "consumer config parse failed",
            check_id=_CHECK_ID,
            status="fail",
            error=str(exc),
        )
        return 1
    return _emit_status(status=status, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
