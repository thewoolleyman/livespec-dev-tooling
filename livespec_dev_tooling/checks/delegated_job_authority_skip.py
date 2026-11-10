"""Report a delegated gate Job path that runs an authority member without the skip variable.

The delegated client keeps a member that reads an authorization held outside the
tree out of the gate Job by naming it under the repository's own skip variable
(`_gate_authority_skip`). That holds only when the recipe the Job actually runs
reads the variable. The pre-commit Job runs `check-pre-commit-gated-tree` in
place of the declared suite's last step, and the pre-push Job runs the declared
`gate_check_suite`; when either reaches an aggregate by a route that ignores the
variable, the member runs in a pod that holds no credential and correctly fails
closed, so every correct tree reads red. The failure is silent at the fleet
level, because bot pin bumps never go through the commit gate.

The check traces each enabled delegated path through the justfile recipes and
repository scripts the Job recipe reaches (`_delegated_job_routes`) and reports
every route that runs a declared authority member without honouring the skip
variable, naming the delegated path, the Job recipe and the member. It reads the
authority declarations and the skip variable from the same sources the delegated
client reads them from, so the two cannot disagree about which members leave the
Job.

WARN-DEFAULT, ARMED BY `LIVESPEC_FAIL_IF_DELEGATED_JOB_RUNS_AUTHORITY_MEMBERS`.
Unarmed, a finding is logged at warning level and the check exits 0. Arming it
in a consuming repository's severity-lever source is the consumer's decision,
made only once its own tree passes, so that wiring the check cannot turn red a
repository whose finding already has an owner.

THE NO-FINDING CASES, each deliberate. A repository enabling no delegated path or
declaring no authority member has nothing to judge. A repository that declares
authority members and has a `check` recipe but no recognised skip variable is
refused by the delegated client locally, before any Job exists, so there is no
Job to convict. A tree whose authority declarations cannot be read, or that has
no `check` recipe, IS reported, because the client then submits the Job without
skipping any member.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.pipeline import is_successful  # noqa: E402  — same.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — same.

from livespec_dev_tooling._delegated_job_routes import (  # noqa: E402  — same.
    job_recipe_name,
    unhonoured_routes,
)
from livespec_dev_tooling._gate_authority_skip import check_skip_variable  # noqa: E402  — same.
from livespec_dev_tooling._gate_remote_assembly import (  # noqa: E402  — same.
    declared_gate_check_suite,
)
from livespec_dev_tooling.check_authority import (  # noqa: E402  — same.
    repository_authority_members,
)
from livespec_dev_tooling.checks._tool_backed_surfaces import (  # noqa: E402  — same.
    extract_check_recipe_body,
)
from livespec_dev_tooling.config import (  # noqa: E402  — same.
    ConfigParseError,
    load_delegated_gate,
    load_delegated_pre_commit,
)

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_CHECK_ID = "delegated_job_authority_skip"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_DELEGATED_JOB_RUNS_AUTHORITY_MEMBERS"
_FAIL_EXIT = 1
_GATED_TREE_RECIPE = "check-pre-commit-gated-tree"
_JUSTFILE_NAME = "justfile"


@dataclass(frozen=True, kw_only=True)
class _DelegatedPath:
    """An enabled delegated path and the recipes its gate Job runs."""

    name: str
    job_recipes: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One thing the check reports, with the fields a reader needs to find it."""

    delegated_path: str
    detail: str
    job_recipe: str | None = None
    member: str | None = None
    route: tuple[str, ...] = ()


def _configure_logger() -> structlog.stdlib.BoundLogger:
    """Configure the check's structured stderr logger."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _delegated_paths(*, repo_root: Path) -> list[_DelegatedPath]:
    """The delegated paths this repository enables, with the recipes each Job runs.

    A malformed opt-in or an unreadable suite declaration leaves the path off the
    list, as the client does: no Job is submitted for it, so there is none to judge.
    """
    try:
        pre_commit = load_delegated_pre_commit(repo_root=repo_root) is True
        pre_push = load_delegated_gate(repo_root=repo_root) is True
    except ConfigParseError:
        return []
    declared = declared_gate_check_suite(repo_root=repo_root)
    if not (pre_commit or pre_push) or not is_successful(declared):
        return []
    entries = declared.unwrap()
    recipes = tuple(job_recipe_name(entry=entry) or "" for entry in entries)
    paths: list[_DelegatedPath] = []
    if pre_commit:
        paths.append(
            _DelegatedPath(name="pre-commit", job_recipes=(*recipes[:-1], _GATED_TREE_RECIPE))
        )
    if pre_push:
        paths.append(_DelegatedPath(name="pre-push", job_recipes=recipes))
    return paths


def _check_recipe_present(*, repo_root: Path) -> bool:
    """Whether the repository's justfile carries a readable `check` recipe."""
    try:
        text = (repo_root / _JUSTFILE_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return is_successful(extract_check_recipe_body(justfile_text=text))


def _findings(*, repo_root: Path, paths: list[_DelegatedPath]) -> list[_Finding]:
    """Judge every enabled delegated path, or report what could not be read."""
    resolved = repository_authority_members(repo_root=repo_root)
    if not is_successful(resolved):
        malformed = unsafe_perform_io(resolved.failure())
        return [
            _Finding(
                delegated_path=path.name,
                detail=(
                    "cannot read the authority declarations, so the delegated client would "
                    f"submit the Job without skipping any member: {malformed.target} "
                    f"declares {malformed.value!r}"
                ),
            )
            for path in paths
        ]
    members = unsafe_perform_io(resolved.unwrap())
    if not members:
        return []
    if not _check_recipe_present(repo_root=repo_root):
        return [
            _Finding(
                delegated_path=path.name,
                detail=(
                    "no `check` recipe in the justfile, so the delegated client would submit "
                    "the Job without skipping any member"
                ),
            )
            for path in paths
        ]
    variable = check_skip_variable(repo_root=repo_root)
    if variable is None:
        return []
    return [
        _Finding(
            delegated_path=path.name,
            job_recipe=route.job_recipe,
            member=route.member,
            route=route.route,
            detail=(
                f"the route {' -> '.join(route.route)} runs authority member {route.member} "
                f"without honouring the skip variable {variable}"
            ),
        )
        for path in paths
        for route in unhonoured_routes(
            repo_root=repo_root,
            job_recipes=path.job_recipes,
            members=members,
            skip_variable=variable,
        )
    ]


def main() -> int:
    """Report each unhonoured route; fail only when the severity lever is armed."""
    log = _configure_logger()
    repo_root = Path.cwd()
    paths = _delegated_paths(repo_root=repo_root)
    if not paths:
        return 0
    findings = _findings(repo_root=repo_root, paths=paths)
    armed = bool(os.environ.get(_FAIL_ENV_VAR))
    for finding in findings:
        emit = log.error if armed else log.warning
        emit(
            f"delegated {finding.delegated_path} path: {finding.detail}",
            check_id=_CHECK_ID,
            status="fail" if armed else "warn",
            delegated_path=finding.delegated_path,
            job_recipe=finding.job_recipe,
            member=finding.member,
            route=list(finding.route),
            severity_lever=_FAIL_ENV_VAR,
        )
    return _FAIL_EXIT if findings and armed else 0


if __name__ == "__main__":
    raise SystemExit(main())
