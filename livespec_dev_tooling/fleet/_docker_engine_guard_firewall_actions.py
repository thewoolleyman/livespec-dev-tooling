"""What the Docker engine install guard DOES to the guarded host's firewall.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Publish" (the snapshot) and
"Host actions" (footprint, footprint removal, FORWARD restore).
Governing design: `docs/docker-engine-guard-design.md` Mechanism 4.

The PLAN lives next door in `_docker_engine_guard_firewall.py` and is
pure; this module is the half that runs commands through the one timed
runner. The split is the reason a footprint can be decided against
recorded output at all.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_firewall import (
    FAMILIES,
    FORWARD_POLICY_SNAPSHOT,
    SNAPSHOT_TABLES,
    FirewallTable,
    FootprintPlan,
    chain_argv,
    delete_argv,
    parse_table,
    plan_footprint,
    save_argv,
    snapshot_name,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "DELETE_CHAIN",
    "FIREWALL_TIMEOUT_SECONDS",
    "FLUSH_CHAIN",
    "FORWARD_CHAIN",
    "read_current_table",
    "read_snapshot_table",
    "remove_footprint",
    "write_firewall_snapshot",
]

# The two whole-chain verbs, in the order they have to be issued: a chain
# still holding rules cannot be deleted.
FLUSH_CHAIN: Final[str] = "-F"
DELETE_CHAIN: Final[str] = "-X"

# Long enough for the xtables lock a reconciler may hold mid-sync (the
# design measures k3s's own sweeps at 4 within 300 seconds), short enough
# that one stuck table cannot consume a whole rollback phase's budget.
FIREWALL_TIMEOUT_SECONDS: Final[int] = 30

FORWARD_CHAIN: Final[str] = "FORWARD"

# The one table the FORWARD chain lives in. Named rather than left
# implicit so every emitted argv says which table it means.
_POLICY_TABLE: Final[str] = "filter"


def write_firewall_snapshot(*, destination: Path, runner: GuardCommandRunner) -> None:
    """Record both families' tables, and both FORWARD policies, under `destination`.

    This is the only copy a rollback ever compares against, so it is
    taken before the first package step and never retaken. Each policy is
    derived from the family's own `filter` dump rather than read with a
    second command: two reads could land either side of a reconciler's
    sweep and record a policy the stored rules never had.
    """
    destination.mkdir(parents=True, exist_ok=True)
    policies: dict[str, str] = {}
    for family in FAMILIES:
        for table in SNAPSHOT_TABLES:
            dump = runner(
                argv=save_argv(family=family, table=table),
                timeout_seconds=FIREWALL_TIMEOUT_SECONDS,
            ).stdout
            _ = (destination / snapshot_name(family=family, table=table)).write_text(
                dump, encoding="utf-8"
            )
            if table == _POLICY_TABLE:
                policies[family] = parse_table(dump=dump).policies[FORWARD_CHAIN]
    _ = (destination / FORWARD_POLICY_SNAPSHOT).write_text(
        json.dumps(policies, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_current_table(*, runner: GuardCommandRunner, family: str, table: str) -> FirewallTable:
    """One family's one table as it stands right now."""
    return parse_table(
        dump=runner(
            argv=save_argv(family=family, table=table),
            timeout_seconds=FIREWALL_TIMEOUT_SECONDS,
        ).stdout
    )


def read_snapshot_table(*, snapshot: Path, family: str, table: str) -> FirewallTable:
    """The same table as the run's `before/` directory recorded it."""
    return parse_table(
        dump=(snapshot / snapshot_name(family=family, table=table)).read_text(encoding="utf-8")
    )


def apply_footprint_plan(
    *, runner: GuardCommandRunner, family: str, table: str, plan: FootprintPlan
) -> None:
    """Issue one table's plan: every `-D`, then every `-F`, then every `-X`."""
    for rule in plan.delete_rules:
        _ = runner(
            argv=delete_argv(family=family, table=table, rule=rule),
            timeout_seconds=FIREWALL_TIMEOUT_SECONDS,
        )
    for verb in (FLUSH_CHAIN, DELETE_CHAIN):
        for chain in plan.delete_chains:
            _ = runner(
                argv=chain_argv(family=family, table=table, verb=verb, chain=chain),
                timeout_seconds=FIREWALL_TIMEOUT_SECONDS,
            )


def remove_footprint(*, runner: GuardCommandRunner, snapshot: Path) -> tuple[str, ...]:
    """Take Docker's footprint off both families, table by table.

    The walk order is the families' order and then the tables', so a
    report of what happened reads the same way twice. Residual reporting
    and the repeat passes the specification requires arrive with the next
    assertion; this pass is the single sweep they repeat.
    """
    for family in FAMILIES:
        for table in SNAPSHOT_TABLES:
            apply_footprint_plan(
                runner=runner,
                family=family,
                table=table,
                plan=plan_footprint(
                    current=read_current_table(runner=runner, family=family, table=table),
                    snapshot=read_snapshot_table(snapshot=snapshot, family=family, table=table),
                ),
            )
    return ()
