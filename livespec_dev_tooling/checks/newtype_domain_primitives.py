"""newtype_domain_primitives — canonical field names use `livespec/types.py` NewType.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-newtype-domain-primitives` row),
walks `schemas/dataclasses/*.py` (cycle 171 minimum-viable
scope) and verifies field annotations matching canonical
field names use the corresponding `livespec/types.py` NewType:

| field name      | required type   |
|-----------------|-----------------|
| check_id        | CheckId         |
| run_id          | RunId           |
| topic           | TopicSlug       |
| spec_root       | SpecRoot        |
| schema_id       | SchemaId        |
| template        | TemplateName    |
| author          | Author          |
| author_human    | Author          |
| author_llm      | Author          |
| version_tag     | VersionTag      |

Note: `template_root` (resolved directory) is `Path`, NOT
`TemplateName` — the field-name lookup is exact, so the
mapping isn't keyed on substring.

Subsequent cycles widen scope to function signatures across
all of `livespec/**`.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._role_key_gate import (  # noqa: E402
    ensure_declared_paths_contain_python,
    role_key_gate_exit_code,
)
from livespec_dev_tooling.config import iter_py_files, load_config  # noqa: E402

__all__: list[str] = []
_DATACLASSES_TREE_GATE_BUG = "dataclasses_tree unexpectedly empty after role-key gate"
_FIELD_TO_NEWTYPE: dict[str, str] = {
    "check_id": "CheckId",
    "run_id": "RunId",
    "topic": "TopicSlug",
    "spec_root": "SpecRoot",
    "schema_id": "SchemaId",
    "template": "TemplateName",
    "author": "Author",
    "author_human": "Author",
    "author_llm": "Author",
    "version_tag": "VersionTag",
}


def _annotation_terminal_name(*, annotation: ast.expr) -> str:
    # Peel `X | None` to X (PEP 604 union shape). The `| None` only
    # marks the field as optional; whether the inner type is the
    # required NewType is the actual check.
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left, right = annotation.left, annotation.right
        if isinstance(right, ast.Constant) and right.value is None:
            return _annotation_terminal_name(annotation=left)
        if isinstance(left, ast.Constant) and left.value is None:
            return _annotation_terminal_name(annotation=right)
    rendered = ast.unparse(annotation)
    head = rendered.split("[", maxsplit=1)[0]
    return head.rsplit(".", maxsplit=1)[-1]


def _find_offenders_in_class(*, cls: ast.ClassDef) -> list[tuple[int, str, str, str]]:
    """Return list of (lineno, field_name, actual_type, required_type)."""
    out: list[tuple[int, str, str, str]] = []
    for stmt in cls.body:
        if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
            continue
        field_name = stmt.target.id
        if field_name not in _FIELD_TO_NEWTYPE:
            continue
        required = _FIELD_TO_NEWTYPE[field_name]
        actual = _annotation_terminal_name(annotation=stmt.annotation)
        if actual != required:
            out.append((stmt.lineno, field_name, actual, required))
    return out


def _find_offenders(*, source: str) -> list[tuple[int, str, str, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out.extend(_find_offenders_in_class(cls=node))
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("newtype_domain_primitives")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    gate_exit = role_key_gate_exit_code(
        config=config,
        key="dataclasses_tree",
        value_is_empty=config.dataclasses_tree is None,
        log=log,
        check_id="newtype_domain_primitives",
    )
    if gate_exit is not None:
        return gate_exit
    dataclasses_tree = config.dataclasses_tree
    if dataclasses_tree is None:
        raise RuntimeError(_DATACLASSES_TREE_GATE_BUG)
    dataclasses_root = cwd / dataclasses_tree
    if not dataclasses_root.is_dir():
        log.error(
            "declared dataclasses_tree is not a directory",
            check_id="newtype_domain_primitives",
            role="dataclasses_tree",
            path=dataclasses_tree.as_posix(),
        )
        return 1
    # Composed AFTER the is_dir check rather than via `role_key_paths_exit_code`,
    # which bundles both: a non-directory would otherwise collapse into the
    # generic "resolves to no Python files" wording and lose the specific
    # diagnostic above. Keyed off the DECLARED PATHS, never off the count of
    # files actually inspected, per `contracts.md` §"Role keys".
    if not ensure_declared_paths_contain_python(
        repo_root=cwd,
        key="dataclasses_tree",
        paths=(dataclasses_tree,),
        log=log,
        check_id="newtype_domain_primitives",
    ):
        return 1
    offenders: list[tuple[Path, int, str, str, str]] = []
    for py_file in iter_py_files(root=dataclasses_root):
        source = py_file.read_text(encoding="utf-8")
        for lineno, field, actual, required in _find_offenders(source=source):
            offenders.append((py_file.relative_to(cwd), lineno, field, actual, required))
    if offenders:
        for path, lineno, field, actual, required in offenders:
            log.error(
                "canonical field name not using required NewType",
                file=str(path),
                line=lineno,
                field=field,
                actual_type=actual,
                required_type=required,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
