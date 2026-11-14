"""The merge-queue rules of `branch_protection_alignment`.

Split from the check module, which sits in the LLOC soft band. Per the
`branch_protection_alignment` check contract in this repository's
SPECIFICATION/contracts.md (v225), five rules apply only to a repository whose
owner is an `Organization`:

- a QUEUE-REQUIRED repository (its name is in the check's
  `QUEUE_REQUIRED_REPOSITORIES`) whose active default-branch rulesets carry no
  `merge_queue` rule fails `merge_queue_absent`;
- a `merge_queue` rule building fewer than 2 entries fails
  `merge_queue_concurrency_below_floor`;
- a `merge_queue` rule whose `merge_method` is not `REBASE` fails
  `merge_queue_method_not_rebase`;
- on a queue-required repository, every active default-branch ruleset must
  carry the recovery `Integration` named by `recovery_bypass_integration_id`
  as its ONLY bypass actor, and classic protection must keep `enforce_admins`
  on with no push `restrictions`; anything else, or an undeclared key, fails
  `merge_queue_bypass_path`;
- a repository whose workflows route `merge_group` to gating self-hosted
  capacity (the guarded exception of `self_hosted_routing`) must hold the
  strictest fork-PR approval setting, or fails `fork_approval_below_strictest`.

On a personal-account repository none of them fire. Every forge read goes
through `budgeted_gh.gh_read`; an unreadable owner type or fork-PR approval
setting takes the check's graceful-skip path, while an unreadable ruleset
fails `ruleset_unreadable`, because the classic read before it proved scope.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.budgeted_gh import gh_read  # noqa: E402
from livespec_dev_tooling.checks._branch_protection_api import _RequiredContexts  # noqa: E402
from livespec_dev_tooling.checks._branch_protection_queue_rules import (  # noqa: E402
    only_recovery_bypass,
    queue_parameter_code,
    rule_objects,
    uses_guarded_merge_group,
)
from livespec_dev_tooling.checks._config_load import load_config_or_report  # noqa: E402

__all__: list[str] = ["merge_queue_exit_code"]

_ORGANIZATION = "Organization"
_STRICTEST_FORK_APPROVAL = "all_external_contributors"
_WORKFLOWS_DIR = Path(".github/workflows")
_CHECK_ID = "branch_protection_alignment"


@dataclass(frozen=True, kw_only=True)
class _Inputs:
    """What the merge-queue rules read besides the forge."""

    protection: _RequiredContexts
    admins_enabled: bool
    queue_required_names: frozenset[str]
    recovery_app_id: int | None
    gating_labels: tuple[str, ...]
    workflows_dir: Path


def _read_json(*, args: list[str]) -> object:
    """One forge read's parsed body, or None when the read failed."""
    completed = gh_read(args=args)
    return json.loads(completed.stdout) if completed.returncode == 0 else None


def _read_object(*, path: str) -> dict[str, object]:
    """One forge object, or an empty object when it could not be read."""
    parsed = _read_json(args=["api", path])
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}


def _ruleset_bypass_code(
    *, log: structlog.stdlib.BoundLogger, base: str, ruleset_ids: list[int], recovery_app_id: int
) -> int:
    """Hold each active ruleset to the single recovery-Integration bypass."""
    code = 0
    for ruleset_id in ruleset_ids:
        actors = _read_object(path=f"{base}/rulesets/{ruleset_id}").get("bypass_actors")
        if not isinstance(actors, list):
            log.error(
                "could not read the bypass list of an active default-branch ruleset; "
                "refusing to report a merge queue this run did not verify",
                failure_mode="ruleset_unreadable",
                detail=f"ruleset {ruleset_id} has no readable bypass list",
            )
            return 4
        if not only_recovery_bypass(
            actors=cast("list[object]", actors), recovery_app_id=recovery_app_id
        ):
            log.error(
                "an active default-branch ruleset lets an actor other than the "
                "recovery App bypass the merge queue",
                failure_mode="merge_queue_bypass_path",
                ruleset_id=ruleset_id,
            )
            code = 4
    return code


def _bypass_code(
    *, log: structlog.stdlib.BoundLogger, inputs: _Inputs, ruleset_ids: list[int]
) -> int:
    """The queue is the only path to the default branch but the recovery App."""
    protection = inputs.protection
    base = f"repos/{protection.owner_repo}"
    restrictions = f"{base}/branches/{protection.branch}/protection/restrictions"
    code = 0
    if gh_read(args=["api", restrictions]).returncode == 0 or not inputs.admins_enabled:
        log.error(
            "classic protection leaves a path to the default branch around the merge queue",
            failure_mode="merge_queue_bypass_path",
            hint="set enforce_admins and remove every push restriction exception",
        )
        code = 4
    if inputs.recovery_app_id is None:
        log.error(
            "recovery_bypass_integration_id is not declared, so the recovery App "
            "cannot be told from any other bypass actor",
            failure_mode="merge_queue_bypass_path",
            hint="declare recovery_bypass_integration_id in [tool.livespec_dev_tooling]",
        )
        return 4
    return max(
        code,
        _ruleset_bypass_code(
            log=log, base=base, ruleset_ids=ruleset_ids, recovery_app_id=inputs.recovery_app_id
        ),
    )


def _queue_required_code(*, log: structlog.stdlib.BoundLogger, inputs: _Inputs) -> int:
    """The four rules a queue-required repository is held to."""
    protection = inputs.protection
    rules_path = f"repos/{protection.owner_repo}/rules/branches/{protection.branch}?per_page=100"
    pages = _read_json(args=["api", "--paginate", "--slurp", rules_path])
    rules = rule_objects(pages=cast("list[object]", pages)) if isinstance(pages, list) else None
    if rules is None:
        log.error(
            "could not read the default branch's active ruleset rules; "
            "refusing to report a merge queue this run did not verify",
            failure_mode="ruleset_unreadable",
            detail=f"rules read of {rules_path} was not a list of rule pages",
        )
        return 4
    queues = [rule for rule in rules if rule.get("type") == "merge_queue"]
    code = 0
    if not queues:
        log.error(
            "a queue-required repository's default branch does not require the merge queue",
            failure_mode="merge_queue_absent",
            hint="add a merge_queue rule to an active ruleset on the default branch",
        )
        code = 4
    for rule in queues:
        code = max(code, queue_parameter_code(log=log, rule=rule))
    ruleset_ids = sorted({i for r in rules if type(i := r.get("ruleset_id")) is int})
    return max(code, _bypass_code(log=log, inputs=inputs, ruleset_ids=ruleset_ids))


def _fork_approval_code(*, log: structlog.stdlib.BoundLogger, owner_repo: str) -> int:
    """A guarded `merge_group` repository must hold the strictest fork-PR approval."""
    path = f"repos/{owner_repo}/actions/permissions/fork-pr-contributor-approval"
    policy = _read_object(path=path).get("approval_policy")
    if not isinstance(policy, str):
        log.warning(
            "could not read the fork-PR approval setting; skipping its rule",
            hint="check gh auth status; the read needs repository admin scope",
        )
        return 0
    if policy != _STRICTEST_FORK_APPROVAL:
        log.error(
            "a repository using the guarded merge_group exception does not require "
            "approval for every external contributor's fork PR",
            failure_mode="fork_approval_below_strictest",
            approval_policy=policy,
        )
        return 4
    return 0


def _graded_exit_code(*, log: structlog.stdlib.BoundLogger, inputs: _Inputs) -> int:
    """The exit code the merge-queue rules owe: `4` or `0`.

    The owner is read only when a rule could apply, so a repository that is
    neither queue-required nor using the guarded exception costs no read.
    """
    owner_repo = inputs.protection.owner_repo
    queue_required = owner_repo.rsplit("/", 1)[-1] in inputs.queue_required_names
    guarded = uses_guarded_merge_group(
        workflows_dir=inputs.workflows_dir, gating_labels=inputs.gating_labels
    )
    if not (queue_required or guarded):
        return 0
    owner = _read_object(path=f"repos/{owner_repo}").get("owner")
    owner_type = cast("dict[str, object]", owner).get("type") if isinstance(owner, dict) else None
    if not isinstance(owner_type, str):
        log.warning(
            "could not read the repository owner's type; skipping the merge-queue rules",
            hint="check gh auth status",
        )
        return 0
    if owner_type != _ORGANIZATION:
        return 0
    codes = [0]
    if queue_required:
        codes.append(_queue_required_code(log=log, inputs=inputs))
    if guarded:
        codes.append(_fork_approval_code(log=log, owner_repo=owner_repo))
    return max(codes)


def merge_queue_exit_code(
    *,
    log: structlog.stdlib.BoundLogger,
    cwd: Path,
    protection: _RequiredContexts,
    admins_enabled: bool,
    queue_required_names: frozenset[str],
) -> int:
    """The merge-queue rules' exit code, or `1` when the consumer config is malformed.

    The config is read here because only these rules need it: the recovery
    App id and the consumer's gating self-hosted labels.
    """
    loaded = load_config_or_report(repo_root=cwd, log=log, check_id=_CHECK_ID)
    if not is_successful(loaded):
        return 1
    config = unsafe_perform_io(loaded.unwrap())
    inputs = _Inputs(
        protection=protection,
        admins_enabled=admins_enabled,
        queue_required_names=queue_required_names,
        recovery_app_id=config.recovery_bypass_integration_id,
        gating_labels=config.gating_self_hosted_labels,
        workflows_dir=cwd / _WORKFLOWS_DIR,
    )
    return _graded_exit_code(log=log, inputs=inputs)
