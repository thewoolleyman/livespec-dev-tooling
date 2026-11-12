"""Ensure every Ansible-driving test module is declared gate-Job-only.

The declaration keeps an agent's foreground pytest from starting an
``ansible-playbook`` process on the dev host. This repository-only check lives
outside ``checks/`` because other consumers need not carry Ansible tests.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatchcase
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_gate_job_only_tests  # noqa: E402

__all__: list[str] = ["undeclared_gate_job_only_modules"]


_MARKER = "ansible-playbook"


def _matching_test_modules(*, repo_root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted((repo_root / "tests").rglob("test_*.py"))
        if _MARKER in path.read_text(encoding="utf-8")
    )


def undeclared_gate_job_only_modules(*, repo_root: Path) -> tuple[str, ...]:
    globs = load_gate_job_only_tests(repo_root=repo_root)
    return tuple(
        path.relative_to(repo_root).as_posix()
        for path in _matching_test_modules(repo_root=repo_root)
        if not any(
            fnmatchcase(path.relative_to(repo_root).as_posix(), pattern) for pattern in globs
        )
    )


def main() -> int:
    """Emit one finding for each Ansible-driving test absent from the declaration."""
    log = structlog.get_logger("ansible_test_gate_job_only")
    missing = undeclared_gate_job_only_modules(repo_root=Path.cwd())
    for module in missing:
        log.error(
            "Ansible-driving test module matches no gate_job_only_tests glob",
            module=module,
            hint="add a matching [tool.livespec_dev_tooling].gate_job_only_tests glob",
        )
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
