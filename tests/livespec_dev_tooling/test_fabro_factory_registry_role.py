"""`ansible/fabro-hosts.yml` renders the Fabro factory registry from the inventory.

Covers the scenario in `SPECIFICATION/scenarios.md` stating that the fabro-hosts
play renders the factory registry from the inventory's factory names, together with
the Fabro factory registry clause of `SPECIFICATION/non-functional-requirements.md`
that scenario exercises. Work-item `livespec-dev-tooling-txadim`; plan
`petri-factory-on-gmktec`, epic `bd-ib-fyozyd`.

WHY THE ROLE IS RUN AND NOT READ. Every claim the scenario makes is a claim about
what Jinja RESOLVES: a factory name is turned into an address by reaching through
`hostvars` into another host's `fabro_server_instances`, picking the mapping whose
`unit_name` matches, and prefixing its `canonical_host`. Whether `selectattr` finds
that mapping, whether a blank `canonical_host` survives a `trim`, and whether the
refusal fires before the write are decided by those semantics and by Ansible's
task ordering — not by what the file says. So the committed role runs, under the
same `ansible-core` pin `just ansible-apply` uses, exactly as the sibling
`test_fabro_hosts_target_units` runs this play's instance selector. No host is
reached: the synthetic dev hosts connect locally and the factory hosts are never
connected to at all, because only their inventory variables are read.

WHY `--check`, AND WHAT THE REPORT TASK IS. The role's own write task is
`/etc/livespec/fabro-factories.json`, root-owned — a real converge of the machine
this suite runs on. `--check` makes the role's `file` and `copy` tasks compute and
change nothing, and the test's own report task carries `check_mode: false` so it
alone writes, under `tmp_path`. Its `content` is not a transcription: it is READ
out of the committed install task, so the bytes asserted below are rendered from
the committed expression. `ansible_become: false` on the synthetic dev hosts
overrides the role's task-level `become: true` (measured on ansible-core 2.21.4:
a connection variable overrides the keyword), so the run needs no privilege.

WHAT IS STATED RATHER THAN RUN, AND WHY. Two Thens are not about resolution. The
file's OWNERSHIP is the install task's `owner`/`group`/`mode`, which `--check`
declines to apply and a non-root CI container could not apply anyway; it is read
off the committed task. And "a `--tags` run that runs no rendering task leaves the
file unchanged" is a claim about SELECTION, so it is answered by running
`ansible-playbook --list-tasks` over the committed play both ways — a real run of
the committed file that reaches no host — rather than by re-describing the tag.

CONTROL ARMS. The refusal arms are paired with a valid registry that must NOT
refuse, and each asserts the install task never appeared, against the valid arm
which proves it does. The address arm asserts the bare `canonical_host` is not the
value, so a role that forgot the scheme cannot pass. The removal arm re-points one
factory and drops another, and asserts the dropped name AND the previous address
are both absent from the second render rather than merely that the new one is
present.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAYBOOK = _ANSIBLE / "fabro-hosts.yml"
_LEGACY_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_GROUP_VARS = _ANSIBLE / "inventory" / "group_vars" / "dev_hosts.yml"
_ROLE_NAME = "fabro_factory_registry"
_ROLE = _ANSIBLE / "roles" / _ROLE_NAME
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

_REGISTRY_PATH = "/etc/livespec/fabro-factories.json"
_INSTALL_TASK = "Install this host's Fabro factory registry"
_RESOLVED_FACT = "fabro_factory_registry_resolved"
_TIMEOUT_SECONDS = 600
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# The synthetic fleet. TWO dev hosts, because "refuses before writing on ANY host"
# is a claim about the play and not about one machine; three factory hosts, because
# the scenario re-points a factory onto a third.
_DEV_HOSTS = ("dev-one", "dev-two")
_INSTANCES: Mapping[str, list[dict[str, str]]] = {
    "factory-one": [
        {"unit_name": "fabro-server", "canonical_host": "factory-one.tailnet.example:32276"},
        {"unit_name": "fabro-server-org", "canonical_host": "factory-one.tailnet.example:32277"},
    ],
    "factory-two": [
        {"unit_name": "fabro-server", "canonical_host": "factory-two.tailnet.example:32276"},
    ],
    "factory-three": [
        {"unit_name": "fabro-server", "canonical_host": "factory-three.tailnet.example:32276"},
        {"unit_name": "fabro-server-blank", "canonical_host": "   "},
    ],
}
_DOCKER_HOST = "ssh://operator@factory-one.tailnet.example"

# The scenario's first Given: `legacy` on one host WITH a docker_host, `petri` on
# another WITHOUT one.
_DECLARED: dict[str, dict[str, str]] = {
    "legacy": {
        "host": "factory-one",
        "unit_name": "fabro-server",
        "docker_host": _DOCKER_HOST,
    },
    "petri": {"host": "factory-two", "unit_name": "fabro-server"},
}

# The five <invalid> examples, each as the whole registry it is declared in.
_INVALID_REGISTRIES: dict[str, dict[str, dict[str, str]]] = {
    "blank-name": {"   ": {"host": "factory-one", "unit_name": "fabro-server"}},
    "unknown-host": {"legacy": {"host": "factory-absent", "unit_name": "fabro-server"}},
    "unknown-unit": {"legacy": {"host": "factory-one", "unit_name": "fabro-server-absent"}},
    "blank-canonical-host": {
        "legacy": {"host": "factory-three", "unit_name": "fabro-server-blank"}
    },
    "blank-docker-host": {
        "legacy": {"host": "factory-one", "unit_name": "fabro-server", "docker_host": "  "}
    },
}


# --- reading the committed role -------------------------------------------


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _read(*, path: Path) -> str:
    """One committed file, asserting its presence first.

    An absent file is the finding, so it is stated as an ASSERTION rather than left to
    surface as a `FileNotFoundError` from inside a reader — a test that dies before its
    first assertion proves only that a path is missing, not what the missing thing does.
    """
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: nothing else renders "
        f"{_REGISTRY_PATH}, so a dispatching host without it resolves no factory"
    )
    return path.read_text(encoding="utf-8")


def _install_task() -> str:
    """The committed task body that writes the registry, named rather than described."""
    text = _read(path=_TASKS)
    body = re.search(
        rf"^- name: {re.escape(_INSTALL_TASK)}\n(?P<body>(?:(?!^- name: ).*\n)*)",
        text,
        re.MULTILINE,
    )
    assert body is not None, (
        f"{_TASKS} must declare a task named {_INSTALL_TASK!r}: it is the only task that "
        f"writes {_REGISTRY_PATH}, so a test that cannot find it is checking nothing"
    )
    return body["body"]


def _install_key(*, key: str) -> str:
    """One scalar of the install task, with the YAML author's quoting removed."""
    found = re.search(rf"^    {re.escape(key)}: (?P<value>\S.*)$", _install_task(), re.MULTILINE)
    assert found is not None, f"the {_INSTALL_TASK!r} task must declare `{key}:`"
    value = found["value"].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].replace("\\n", "\n").replace('\\"', '"')
    return value


# --- running the committed role -------------------------------------------


def _write_fixture(
    *, root: Path, registry: object | None, per_host: Mapping[str, object] | None = None
) -> Path:
    """One synthetic inventory: two dev hosts, three factory hosts, one registry.

    `per_host` overrides the registry for one dev host. The specification forbids
    declaring `fabro_factory_registry` anywhere but the group's vars, and that is
    exactly why this seam exists only here: making the two dev hosts DISAGREE is the
    only way to put the play in the state the refusal rule is about — one host whose
    registry resolves beside one whose does not — and the rule says neither may write.
    """
    inventory = root / "inventory"
    (inventory / "host_vars").mkdir(parents=True)
    (inventory / "group_vars").mkdir(parents=True)
    dev = {host: {"ansible_connection": "local", "ansible_become": False} for host in _DEV_HOSTS}
    factories = {host: {} for host in _INSTANCES}
    (inventory / "hosts.yml").write_text(
        json.dumps(
            {
                "all": {
                    "children": {
                        "dev_hosts": {"hosts": dev},
                        "factory_hosts": {"hosts": factories},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    for host, instances in _INSTANCES.items():
        (inventory / "host_vars" / f"{host}.json").write_text(
            json.dumps({"fabro_server_instances": instances}), encoding="utf-8"
        )
    if registry is not None:
        (inventory / "group_vars" / "dev_hosts.json").write_text(
            json.dumps({"fabro_factory_registry": registry}), encoding="utf-8"
        )
    for host, override in (per_host or {}).items():
        (inventory / "host_vars" / f"{host}.json").write_text(
            json.dumps({"fabro_factory_registry": override}), encoding="utf-8"
        )
    return inventory / "hosts.yml"


def _play(*, reports: Path) -> str:
    """The test's play: the committed role, then the report task that writes the bytes."""
    return json.dumps(
        [
            {
                "hosts": "dev_hosts",
                "gather_facts": False,
                "roles": [{"role": _ROLE_NAME, "tags": [_ROLE_NAME]}],
                "tasks": [
                    {
                        "name": "Report the registry this run would write",
                        "ansible.builtin.copy": {
                            "content": _install_key(key="content"),
                            "dest": f"{reports}/{{{{ inventory_hostname }}}}.json",
                            "mode": "0644",
                        },
                        "check_mode": False,
                    }
                ],
            }
        ]
    )


def _ansible(*, cwd: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """`ansible-playbook` at the pinned version, with the committed roles on its path."""
    return subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=os.environ | {"ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"), "ANSIBLE_NOCOWS": "1"},
    )


def _converge(
    *,
    tmp_path: Path,
    registry: object | None,
    name: str = "run",
    per_host: Mapping[str, object] | None = None,
) -> tuple[int, str, dict[str, str]]:
    """Converge the committed role over the synthetic fleet; return code, output, renders."""
    root = tmp_path / name
    reports = root / "reports"
    reports.mkdir(parents=True)
    hosts = _write_fixture(root=root, registry=registry, per_host=per_host)
    play = root / "play.yml"
    play.write_text(_play(reports=reports), encoding="utf-8")
    done = _ansible(cwd=root, argv=["-i", str(hosts), "--check", "--diff", str(play)])
    rendered = {path.stem: path.read_text(encoding="utf-8") for path in reports.glob("*.json")}
    return done.returncode, done.stdout + done.stderr, rendered


# The bytes the role's OWN install task would write, lifted out of its `--diff`
# output. The report task renders the committed `content` expression, but it is
# still the test's task; this is the role's, and the two must agree exactly.
_INSTALL_DIFF = re.compile(
    rf"^\+\+\+ after: {re.escape(_REGISTRY_PATH)}\n@@[^\n]*\n(?P<body>(?:\+.*\n)+)",
    re.MULTILINE,
)


def _would_write(*, output: str) -> list[str]:
    """Every host's `--check --diff` rendering of the registry, as file content."""
    return [
        "".join(f"{line[1:]}\n" for line in block["body"].splitlines())
        for block in _INSTALL_DIFF.finditer(output)
    ]


# --- the scenario ---------------------------------------------------------


def test_each_declared_factory_resolves_to_its_instances_https_address(*, tmp_path: Path) -> None:
    code, output, rendered = _converge(tmp_path=tmp_path, registry=_DECLARED)
    assert code == 0, output
    assert sorted(rendered) == sorted(
        _DEV_HOSTS
    ), f"every dev host must render the registry, not just one: {output}"
    for host, text in rendered.items():
        entries = json.loads(text)
        assert sorted(entries) == [
            "legacy",
            "petri",
        ], f"{host} must hold exactly one entry per declared factory name: {text}"
        legacy_host = _INSTANCES["factory-one"][0]["canonical_host"]
        assert entries["legacy"]["server"] == f"https://{legacy_host}"
        assert (
            entries["legacy"]["server"] != legacy_host
        ), "the scheme is not optional: the Dispatcher dials the server value as a URL"
        petri_host = _INSTANCES["factory-two"][0]["canonical_host"]
        assert entries["petri"]["server"] == f"https://{petri_host}"
        assert entries["legacy"]["docker_host"] == _DOCKER_HOST
        assert (
            "docker_host" not in entries["petri"]
        ), f"a factory whose mapping declares no docker_host must carry none: {text}"


def test_the_role_would_write_exactly_the_bytes_the_report_task_renders(*, tmp_path: Path) -> None:
    code, output, rendered = _converge(tmp_path=tmp_path, registry=_DECLARED, name="bytes")
    assert code == 0, output
    would = _would_write(output=output)
    assert len(would) == len(
        _DEV_HOSTS
    ), f"the role's own install task must report a rendering per dev host:\n{output}"
    for host, text in sorted(rendered.items()):
        assert text in would, (
            f"what the role would write to {_REGISTRY_PATH} on {host} must be exactly what "
            f"the committed content expression renders; got {would!r} against {text!r}"
        )


def test_an_inventory_that_declares_no_registry_renders_the_empty_object(*, tmp_path: Path) -> None:
    code, output, rendered = _converge(tmp_path=tmp_path, registry=None)
    assert code == 0, output
    assert rendered, f"the role must still render the file on every dev host: {output}"
    for host, text in rendered.items():
        assert json.loads(text) == {}, f"{host} must hold the empty object: {text}"


def test_a_converge_drops_every_entry_the_inventory_no_longer_declares(*, tmp_path: Path) -> None:
    first_code, first_output, first = _converge(
        tmp_path=tmp_path, registry={**_DECLARED, "retired": _DECLARED["petri"]}, name="before"
    )
    assert first_code == 0, first_output
    was = json.loads(first["dev-one"])
    assert sorted(was) == ["legacy", "petri", "retired"], first["dev-one"]

    second_code, second_output, second = _converge(
        tmp_path=tmp_path,
        registry={"petri": {"host": "factory-three", "unit_name": "fabro-server"}},
        name="after",
    )
    assert second_code == 0, second_output
    now = json.loads(second["dev-one"])
    assert sorted(now) == ["petri"], f"a dropped name must be gone, not merged: {second['dev-one']}"
    assert now["petri"]["server"] == f"https://{_INSTANCES['factory-three'][0]['canonical_host']}"
    assert (
        was["petri"]["server"] not in second["dev-one"]
    ), f"the previous address must be gone from the rendered file: {second['dev-one']}"


def test_the_rendered_file_is_root_owned_and_world_readable() -> None:
    assert _install_key(key="dest") == _REGISTRY_PATH
    assert _install_key(key="owner") == "root"
    assert _install_key(key="group") == "root"
    assert _install_key(key="mode") == "0644", "the Dispatcher reads this file as its own user"
    assert "become: true" in _install_task(), "a root-owned file needs the privilege to write it"
    body = _install_task()
    assert "ansible.builtin.copy:" in body, (
        "the registry must be written WHOLE, so that an entry the inventory no longer "
        "declares cannot survive; lineinfile or blockinfile would merge instead"
    )
    assert f"{{{{ {_RESOLVED_FACT} | to_nice_json }}}}" in body


# --- the refusal ----------------------------------------------------------


@pytest.mark.parametrize("case", sorted(_INVALID_REGISTRIES))
def test_an_unresolvable_factory_refuses_before_the_registry_is_written(
    *, tmp_path: Path, case: str
) -> None:
    code, output, rendered = _converge(
        tmp_path=tmp_path, registry=_INVALID_REGISTRIES[case], name=case
    )
    assert code != 0, f"an unresolvable factory must fail the play, not render a guess:\n{output}"
    assert (
        _INSTALL_TASK not in output
    ), f"the refusal must come before the registry is written on any host:\n{output}"
    assert rendered == {}, f"no host may render a registry from a refused inventory: {output}"
    assert "fabro_factory_registry" in output, output


def test_one_host_that_cannot_resolve_stops_the_write_on_the_host_that_can(
    *, tmp_path: Path
) -> None:
    code, output, rendered = _converge(
        tmp_path=tmp_path,
        registry=_DECLARED,
        per_host={"dev-one": _INVALID_REGISTRIES["unknown-host"]},
        name="mixed",
    )
    assert code != 0, f"a registry one host cannot resolve must fail the play:\n{output}"
    assert rendered == {}, (
        "the refusal is before the write on ANY host, so the host whose own registry "
        f"resolved perfectly well must not have rendered one either: {sorted(rendered)}"
    )
    assert _INSTALL_TASK not in output, output


def test_a_resolvable_inventory_reaches_the_write_the_refusals_must_not(*, tmp_path: Path) -> None:
    code, output, _ = _converge(tmp_path=tmp_path, registry=_DECLARED, name="control")
    assert code == 0, output
    assert (
        _INSTALL_TASK in output
    ), f"the control arm must reach the write task, or the refusal arms prove nothing:\n{output}"


# --- the committed play and inventory -------------------------------------


def _list_tasks(*, tags: list[str] | None) -> str:
    argv = ["-i", str(_LEGACY_INVENTORY), "--list-tasks", str(_PLAYBOOK)]
    if tags is not None:
        argv += ["--tags", ",".join(tags)]
    done = _ansible(cwd=_REPO_ROOT, argv=argv)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def test_the_dev_host_play_runs_the_rendering_and_a_narrowed_run_does_not() -> None:
    assert _INSTALL_TASK in _list_tasks(
        tags=None
    ), "ansible/fabro-hosts.yml must render the registry on the dev_hosts group"
    assert _INSTALL_TASK not in _list_tasks(tags=["gha_runner"]), (
        "a run narrowed by --tags past the rendering must run no rendering task, which is "
        "what leaves an existing registry file unchanged"
    )


def test_the_committed_inventory_declares_a_registry_that_resolves(*, tmp_path: Path) -> None:
    declaration = _read(path=_GROUP_VARS)
    assert (
        "fabro_factory_registry:" in declaration
    ), f"{_GROUP_VARS} is the one place the registry may be declared"
    reports = tmp_path / "committed"
    reports.mkdir()
    play = tmp_path / "committed.yml"
    play.write_text(_play(reports=reports), encoding="utf-8")
    done = _ansible(
        cwd=_REPO_ROOT,
        argv=[
            "-i",
            str(_LEGACY_INVENTORY),
            "--check",
            "-e",
            json.dumps({"ansible_become": False}),
            str(play),
        ],
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, output
    rendered = [json.loads(path.read_text(encoding="utf-8")) for path in reports.glob("*.json")]
    assert rendered, f"the dev_hosts group must have rendered the committed registry: {output}"
    for entries in rendered:
        assert sorted(entries) == ["legacy", "petri"], entries
        for name, entry in entries.items():
            assert entry["server"].startswith("https://"), (name, entry)


def test_the_role_documents_the_variable_it_reads() -> None:
    assert "fabro_factory_registry | default({})" in _read(path=_DEFAULTS), (
        "an inventory that declares no registry must render the empty object, so the "
        "role's default for the registry is the empty mapping. It rides the entries "
        "expression rather than a `fabro_factory_registry:` default, which ansible-lint's "
        "var-naming[no-role-prefix] refuses for a role of that name; the BEHAVIOUR is "
        "asserted by running the role in "
        "test_an_inventory_that_declares_no_registry_renders_the_empty_object"
    )
    doc = _read(path=_ROLE_DOC)
    for token in ("fabro_factory_registry", "`host`", "`unit_name`", "`docker_host`", "`{}`"):
        assert token in doc, f"{_ROLE_DOC} must document {token}"
