"""The local gate concurrency limit is provisioned, never set by hand.

Covers the provisioning clause of
`SPECIFICATION/non-functional-requirements.md` section "Local gate concurrency
limit": a host's limit MUST be provisioned through a committed converge, never
set by hand, and removing that one committed setting MUST return the host to no
limit.

WHY THIS IS A SELF-APPLICATION TEST AND NOT A MODULE TEST. The reading half of
the feature is a pytest plugin and is asserted beside it; the half asserted
here is that the number ever reaches a host at all, and by the committed route.
Nothing a module can observe distinguishes a host whose limit was converged
from one where somebody wrote the file by hand — the plugin reads the same
bytes either way — so the only place that distinction can be enforced is the
committed converge itself.

AND WHY THE ROLLBACK IS A SEPARATE ASSERTION. "Removing the setting returns the
host to no limit" is not implied by "setting it works": a role that only ever
WROTE the limit file would satisfy the first clause and leave a host pinned at
the last number it was given for ever, with the declaration that put it there
already deleted from the tree. The removing twin is what makes the deletion a
rollback, so it is asserted in its own right.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "local_gate_slots"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_DEV_HOST_PLAY = _ANSIBLE / "dev-host.yml"
_DEV_HOSTS_GROUP_VARS = _ANSIBLE / "inventory" / "group_vars" / "dev_hosts.yml"

# The role's own name, as the play includes it and as every one of its variables
# is prefixed. Spelled once because all four assertions below are about the same
# role and a rename that updated only some of them would read as a pass.
_ROLE_NAME = "local_gate_slots"
_LIMIT_VAR = f"{_ROLE_NAME}_limit"

# The measured limit for this group, per the sizing recorded in the role's
# HOST_VARS.md: 18 cores, about four cores per gate aggregate, about six cores
# left for sessions and the Fabro servers.
_DEV_HOST_LIMIT = 3

# Read as TEXT rather than parsed: stdlib `tomllib` lands in 3.11 and PyYAML is
# not a dependency of this library, which is deliberately dependency-free. Every
# other inventory assertion in this suite reads text for the same reason.
_SCALAR = r"^{name}:[ \t]*(?P<value>\S+)[ \t]*$"


def _declared(*, path: Path, name: str) -> str | None:
    """The value one top-level scalar variable carries, or `None` for none."""
    found = re.search(
        _SCALAR.format(name=re.escape(name)),
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return None if found is None else found.group("value")


def _task_names_with(*, fragment: str) -> list[str]:
    """Every task of the role whose `when:` carries `fragment`."""
    body = _ROLE_TASKS.read_text(encoding="utf-8")
    tasks = re.split(r"^- name: ", body, flags=re.MULTILINE)[1:]
    return [one.splitlines()[0] for one in tasks if fragment in one]


def test_the_limit_is_declared_by_a_committed_converge_the_dev_host_play_runs() -> None:
    """The number reaches a host through the committed tree and nothing else.

    Both halves are asserted, because either alone is satisfied by a tree that
    cannot converge anything: a role no play includes never runs, and a play
    that includes a role nothing declares a limit for converges a host to the
    role's default of no limit.
    """
    assert _ROLE_TASKS.is_file(), (
        f"ansible/roles/{_ROLE_NAME}/tasks/main.yml must exist: the ratified "
        f"clause requires a host's limit to be provisioned through a committed "
        f"converge, never set by hand"
    )
    assert f"role: {_ROLE_NAME}" in _DEV_HOST_PLAY.read_text(encoding="utf-8"), (
        f"ansible/dev-host.yml must include the {_ROLE_NAME} role, or the "
        f"committed converge never runs on the host it is written for"
    )
    assert _declared(path=_DEV_HOSTS_GROUP_VARS, name=_LIMIT_VAR) == str(_DEV_HOST_LIMIT), (
        f"the dev_hosts group must declare {_LIMIT_VAR}: {_DEV_HOST_LIMIT}, "
        f"which is the measured limit for an 18-core host running gate "
        f"aggregates of about four cores each"
    )


def test_removing_the_one_committed_setting_returns_a_host_to_no_limit() -> None:
    """The rollback is the deletion, which needs the role's default to be no limit.

    `0` is the role default AND the role's spelling of "no limit", which is what
    makes a deleted declaration a return to no limit rather than a fall-back to
    some other number. The removing tasks are what carry that out on the host;
    without them the default would be a value nothing acted on.
    """
    assert _declared(path=_ROLE_DEFAULTS, name=_LIMIT_VAR) == "0", (
        f"the role default for {_LIMIT_VAR} must be 0 — no limit — so that "
        f"deleting a host's declaration IS the rollback"
    )

    removing = _task_names_with(fragment=f"{_LIMIT_VAR} | int == 0")
    setting = _task_names_with(fragment=f"{_LIMIT_VAR} | int > 0")
    assert removing, (
        "the role must carry tasks that run when the limit is zero: a role that "
        "only ever WROTE the limit would leave a host pinned at the last number "
        "it was given, with the declaration that put it there already deleted"
    )
    assert setting, "and tasks that run when it is not, or nothing provisions it"
    assert len(removing) >= 2, (
        f"every artifact the setting half installs must have a removing twin, "
        f"and the setting half installs more than one, got {removing}"
    )
