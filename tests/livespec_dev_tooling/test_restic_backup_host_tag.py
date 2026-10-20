"""The restic snapshot tag is this machine's inventory name, rendered by the role.

A machine is bound ONLY through the inventory's host groups and host variables
(livespec-dev-tooling-prdxxe). The backup runner the `restic_backup` role installs
carried `--host vps` as a literal, twice — on the `backup` and on the `forget` —
so the one machine the role has ever converged was named inside a shipped script.

THE TAG IS NOT COSMETIC, AND THAT IS WHY THIS IS RENDERED RATHER THAN DROPPED.
`restic --host` is the identity a snapshot is filed under and the identity
retention is keyed on, so the `forget` in the next line prunes exactly the
snapshots the `backup` in the previous line wrote. Change the tag and the host's
existing snapshots stop being its snapshots: the `forget --host <new>` matches
nothing, nothing is pruned, and the old chain is orphaned under a tag no run
writes to again. On the live VPS the inventory name IS `vps`, so rendering it
from `inventory_hostname` reproduces the existing tag byte for byte and the
retention history continues; a second host converging this role gets its own
tag instead of silently sharing the first one's.

The runner therefore became a TEMPLATE. It stays a runtime tool — it re-execs
through the 1Password wrapper and carries the operator subcommands — and the
role still syntax-checks what it renders before it lands, so a broken runner
never reaches the host.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "restic_backup"
_RUNNER_TEMPLATE = _ROLE / "templates" / "vps-restic-backup.sh.j2"
_RETIRED_RUNNER_FILE = _ROLE / "files" / "vps-restic-backup.sh"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars"

# The role variable the tag is read from, and the inventory fact it defaults to.
_HOST_TAG_VAR = "restic_backup_host_tag"
_TAG_REFERENCE = f"--host {{{{ {_HOST_TAG_VAR} }}}}"

# The live VPS's inventory name, and so the tag its existing snapshot chain and
# retention history are filed under. Read from the inventory below rather than
# trusted from here; this is the value that read must produce.
_VPS = "vps"


def _inventory_hosts() -> frozenset[str]:
    """Every machine the fleet inventory binds, read from its own `host_vars` stems."""
    stems = frozenset(path.stem for path in _HOST_VARS.glob("*.yml"))
    assert stems, "ansible/inventory/host_vars must bind at least one machine"
    return stems


def _runner_template() -> str:
    """The rendered-runner template, asserting its presence first.

    An absent file is the finding, so it is stated as an ASSERTION rather than
    left to surface as a `FileNotFoundError` from inside a reader — the technique
    `test_factory_kubeconfig_delivery.py` uses for the same reason: a test that
    dies before its first assertion proves only that a path is missing, not what
    the missing thing was supposed to do.
    """
    assert _RUNNER_TEMPLATE.is_file(), (
        "the restic runner must be a TEMPLATE: its `--host` tag is the machine's "
        "inventory name, which a copied file cannot carry"
    )
    return _RUNNER_TEMPLATE.read_text(encoding="utf-8")


def test_the_role_renders_the_runner_rather_than_copying_it() -> None:
    """A template, because the tag inside it is per-host data.

    `validate` is asserted with it: the installer's post-install `bash -n` moved
    into the task so a runner that does not parse never reaches the host, and a
    rendered file is exactly where that guard still matters.
    """
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    installing = [block for block in tasks.split("\n- name: ") if _RUNNER_TEMPLATE.name in block]

    assert _RUNNER_TEMPLATE.is_file(), "the role must ship the runner as a template"
    assert not _RETIRED_RUNNER_FILE.exists(), (
        "the copied runner must be GONE, not kept beside the template: two sources "
        "for one installed file is the drift this change exists to remove"
    )
    assert len(installing) == 1
    assert "ansible.builtin.template:" in installing[0]
    assert "validate: bash -n %s" in installing[0]


def test_both_restic_invocations_tag_with_the_rendered_host() -> None:
    """The `backup` and the `forget` must carry the SAME tag or retention breaks.

    They are asserted together, and counted, because a half-done change is the
    dangerous one: a `backup` under a new tag with a `forget` under the old prunes
    nothing it writes and the repository grows without bound, which no run reports
    because both commands succeed.

    Read as the `cmd_backup` body rather than line by line: the `backup` spans
    several lines on backslash continuations, so a per-line match would miss the
    half that matters while still looking like it had checked both.
    """
    template = _runner_template()
    body = template.split("\ncmd_backup() {\n", 1)[1].split("\n}\n", 1)[0]

    assert "restic backup " in body
    assert "restic forget " in body
    assert body.count(_TAG_REFERENCE) == 2
    assert template.count(_TAG_REFERENCE) == 2, (
        "the tag belongs to the scheduled backup and its prune and to nothing "
        "else: the operator subcommands pass restic's own --host through"
    )


def test_the_tag_defaults_to_this_machines_inventory_name() -> None:
    """`inventory_hostname` and nothing else — the fact the inventory already binds."""
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")

    assert re.search(
        rf'^{_HOST_TAG_VAR}: "\{{\{{ inventory_hostname \}}\}}"$', defaults, re.MULTILINE
    )


def test_the_vps_keeps_the_tag_its_existing_snapshots_carry() -> None:
    """The rendered value on the one converged host equals the literal it replaced.

    Two halves, because the tag's continuity rests on both: the role renders
    `inventory_hostname`, and that host's inventory name is `vps`. Asserting only
    the first would leave the claim "the history survives" resting on a reading of
    the inventory nobody made.
    """
    dev_hosts = _INVENTORY.read_text(encoding="utf-8").split("        dev_hosts:\n", 1)[1]
    first_member = re.search(r"^ {12}(?P<host>[\w.-]+):$", dev_hosts, re.MULTILINE)

    assert first_member is not None
    assert first_member["host"] == _VPS
    assert _VPS in _inventory_hosts()


def test_the_runner_template_names_no_machine_on_a_value_line() -> None:
    """Comments stay — they are provenance — and no value names a machine.

    The file and unit NAMES keep their `vps-` prefix: those are the paths the
    vps-info installers created, and they are references to a path rather than to
    a machine (ruled on livespec-dev-tooling-prdxxe). So this reads VALUES, which
    is where the binding actually lived.
    """
    hosts = _inventory_hosts()
    hits = [
        f"{number}:{host}"
        for number, raw in enumerate(_runner_template().splitlines(), start=1)
        if not raw.lstrip().startswith("#")
        for host in sorted(hosts)
        if re.search(rf"(?<![\w.-]){re.escape(host)}(?![\w-])", raw)
    ]

    assert hits == []
