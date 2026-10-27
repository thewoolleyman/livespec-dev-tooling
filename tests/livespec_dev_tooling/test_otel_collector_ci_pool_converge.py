"""Every `ci_pool` node's collector is converged by `ansible/ci-pool.yml` — resolved, not assumed.

THE QUESTION THIS FILE ANSWERS (work-item livespec-dev-tooling-ool6ws, plan
`kubernetes-node-observability`, charter root cause 5). The three pool nodes'
collectors were installed by HAND-RUN scripts in `thewoolleyman/otel-collector`
— `scripts/install-ci-runner-host.sh` on poweredge, `scripts/install-hp-factory-host.sh`
on hp — and nothing in `ansible/ci-pool.yml` named a collector at all. The fleet
host guard refuses any by-hand host change, so those installers can no longer be
run: the `otel_collector` role is now the ONLY path by which the merged
configurations reach the nodes. The runner-pool node telemetry rules in
`SPECIFICATION/non-functional-requirements.md` already require exactly that —
every pool node's collector, its configuration, its unit, its pinned binary and
its ingest-key entry converged by `ansible/ci-pool.yml`, and a hand-run
installer forbidden as the deployment path.

WHY A RESOLVER AND A RENDER, AND NOT AN `ansible-playbook` RUN. The play reaches
real hosts: it mints credentials, mounts volumes and delegates kubectl. What CAN
be established off-host is the thing in question — which variables each host
resolves, and what unit those variables render. So this file reads the two
playbooks, the inventory, the role's `defaults/main.yml` and each host's
`host_vars`, resolves the role's variables per host, and renders
`templates/otel-collector.service.j2` through Jinja2 itself. Jinja2 is the engine
Ansible templates with, so the render here is the render there; a hand-rolled
substituter would be free to disagree, and a resolver that quietly disagrees with
the play is worse than no resolver because it reports a converge that does not
happen.

TWO PROPERTIES KEEP THAT RENDER FAITHFUL, and both are asserted rather than
assumed. The environment is built with `trim_blocks=True` and
`lstrip_blocks=False`, which are the `template` module's own defaults, so a
block tag on its own line emits nothing. And `StrictUndefined` is installed, so a
variable the committed tree does not declare raises here instead of rendering as
emptiness — which is the failure shape that would otherwise report a missing
`EnvironmentFile=` line as a deliberate absence.

THE TEMPLATE IS HELD TO PLAIN JINJA2 ON PURPOSE. Ansible adds filters Jinja does
not have, `bool` among them, so a template using one could not be rendered here
without this file re-implementing it — and a re-implemented filter is exactly the
quiet disagreement above. So the template's conditionals read their flags as
truthiness, and `test_every_committed_posture_flag_is_a_yaml_boolean_literal`
holds the committed tree to real YAML booleans, where truthiness and Ansible's
`bool` agree for every value. A string `"false"` is truthy in both engines; the
guard is that no declaration in this tree is a string.

EVERY STRUCTURAL CLAIM IS READ OFF CODE, NEVER OFF PROSE. The role's task files
and the unit template carry long comments about the trap each part exists to
close, and that prose necessarily NAMES the directives it is about — `no_log`,
`regexp`, `ProtectSystem=strict`, `k3s.service`. So `_task_blocks` strips comment
lines and `_directives` strips them from a render, and the assertions read those.
Skipping it fails in both directions at once: a presence claim passes on a
sentence merely mentioning the directive, and an absence claim fails on the
template's own explanation of why that host does not carry it — which is the
arm that can never be made to pass, however correct the tree.

WHAT IS DERIVED AND WHAT IS STATED. The role list, each entry's gate and tags,
the `ci_pool` membership, every variable and the template are all READ from the
committed tree. The EXPECTED per-host shapes are stated, because the Definition
of Done states them, and `vps`'s whole rendered directive set is stated because
"the dev host's unit is unchanged" is a claim that has to be written down for a
regression to fail against it.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_CI_POOL_PLAY = _ANSIBLE / "ci-pool.yml"
_DEV_HOST_PLAY = _ANSIBLE / "dev-host.yml"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars"
_README = _ANSIBLE / "README.md"
_ROLE = _ANSIBLE / "roles" / "otel_collector"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_BINARY_TASKS = _ROLE / "tasks" / "binary.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"
_UNIT_TEMPLATE = _ROLE / "templates" / "otel-collector.service.j2"

_ROLE_NAME = "otel_collector"
_DEV_HOST = "vps"
_POWEREDGE = "poweredge-xubuntu"
_GMKTEC = "gmktec-xubuntu"
_HP = "hp-xubuntu"
_CI_POOL = (_POWEREDGE, _GMKTEC, _HP)

# The collector shape each pool node runs, and the one `vps` keeps. These are the
# four files `thewoolleyman/otel-collector` carries at `cb42f5f`; the pool's three
# are what the retired hand-run installers copied to `/etc/otel-collector/config.yaml`.
_CONFIG_FILES = {
    _DEV_HOST: "config.yaml",
    _POWEREDGE: "config.ci-runner-host.yaml",
    _GMKTEC: "config.k3s-agent-host.yaml",
    _HP: "config.hp-factory.yaml",
}

# The dedicated system account every pool node's collector runs as, matching the
# two sibling units. `vps`'s collector has always run as the login account.
_SERVICE_ACCOUNT = "otel-collector"

# The pinned release and the sha256 of its upstream linux/amd64 tarball, as the
# Definition of Done names them. The three pool nodes are all x86_64.
_BINARY_VERSION = "0.147.0"
_BINARY_SHA256 = "17cc9a8f2e44e80ceff0e0647aec18b28a6b1b17823040e362ddc4a9fd017ccc"

# The ingest key every pool node's collector needs and that the control node
# carries under the credential wrapper.
_CONTROLLER_KEY = "HONEYCOMB_INGEST_KEY_LIVESPEC"

# The three directives the two sibling units carry and `vps`'s deliberately does
# not: its collector runs as the login account with `hostmetrics` scraping the
# whole machine, so a sandbox there is a behaviour change rather than a transcription.
_HARDENING = ("ProtectSystem=strict", "ProtectHome=true", "PrivateTmp=true")

# What poweredge's unit needs and no other host does: the installer-rendered
# non-secret environment file, the scoped read-only cluster identity, and the two
# units its start has to follow.
_POWEREDGE_HOST_ENV = "EnvironmentFile=/etc/otel-collector/host.env"
_POWEREDGE_KUBECONFIG = "Environment=KUBECONFIG=/etc/otel-collector/kubeconfig"
_POWEREDGE_AFTER_UNITS = ("k3s.service", "otel-collector-identity.service")

# `vps`'s whole rendered directive set, stated so a regression fails here. The
# claim the Definition of Done makes about this host is that the new variables
# leave its unit alone, and a membership test cannot fail on a line that appears.
_DEV_HOST_DIRECTIVES = (
    "[Unit]",
    "Description=otel-collector -- host OTel Collector on the dev host",
    "Documentation=https://github.com/thewoolleyman/otel-collector",
    "After=network-online.target docker.service",
    "Wants=network-online.target docker.service",
    "[Service]",
    "Type=simple",
    "User=ubuntu",
    "Group=ubuntu",
    "EnvironmentFile=/etc/otel-collector/.env",
    "ExecStart=/usr/local/bin/otelcol-contrib --config=/etc/otel-collector/config.yaml",
    "Restart=on-failure",
    "RestartSec=5",
    "NoNewPrivileges=true",
    "[Install]",
    "WantedBy=multi-user.target",
)

# The two commands the README has to carry for the pool, run under the credential
# wrapper because the controller variable the render reads is projected, not stored.
_CI_POOL_DRIFT = (
    "/usr/local/bin/with-livespec-env.sh -- "
    "just ansible-drift ansible/ci-pool.yml --tags otel_collector"
)
_CI_POOL_APPLY = (
    "/usr/local/bin/with-livespec-env.sh -- "
    "just ansible-apply ansible/ci-pool.yml --tags otel_collector"
)

# A `roles:` entry, its optional gate and its tags. Matched as text because no
# YAML library is importable in this suite: the package is dependency-free at
# RUNTIME and `[dependency-groups].dev` carries only what a check or a test
# cannot do without — Jinja2 is there because the render below has to be the
# host's render, and a YAML parser would buy nothing the committed shapes this
# tree declares do not already give a reader.
_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)
_TAGS_LINE = re.compile(r"^      tags: \[(?P<tags>[^]]*)\]$", re.MULTILINE)
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_INVENTORY_HOST = re.compile(r"^            (?P<host>[\w-]+):$", re.MULTILINE)

# Every value shape a role variable may be declared in, in this tree. The reader
# below refuses anything else rather than skipping it: a shape it cannot parse is
# a variable it would resolve as absent, and `StrictUndefined` would then blame
# the template for a hole this file dug.
_KEY = r"otel_collector_[a-z0-9_]+"
_SCALAR = re.compile(rf"^(?P<key>{_KEY}):[ ](?P<value>\S.*)$")
_FOLDED = re.compile(rf"^(?P<key>{_KEY}):[ ]>-$")
_OPEN = re.compile(rf"^(?P<key>{_KEY}):$")
_LIST_ITEM = re.compile(r"^  - (?P<item>\S.*)$")
_CONTINUATION = re.compile(r"^  (?P<text>\S.*)$")
_ANY_KEY = re.compile(rf"^(?P<key>{_KEY}):")

_TRUE = "true"
_FALSE = "false"

# `{{ ansible_managed }}` is the template's first line; the value is the control
# node's, not the role's, so a stand-in stands in for it.
_ANSIBLE_MANAGED = "Ansible managed"

# How many passes the variable resolution gets before it is declared cyclic. The
# committed tree's deepest chain is three (`config_url` over `config_file`, and
# `config_path` over `etc_dir`), so a bound well above it catches a cycle without
# turning one into a hang.
_RESOLUTION_PASSES = 10

# Every module this role writes with. Used to locate the FIRST write in
# `tasks/main.yml`, so the two refusals the Definition of Done orders "before it
# writes anything" can be held to that order. `include_tasks` is a write because
# the file it pulls in installs a binary and creates an account.
_WRITING_MODULES = (
    "ansible.builtin.copy:",
    "ansible.builtin.file:",
    "ansible.builtin.get_url:",
    "ansible.builtin.include_tasks:",
    "ansible.builtin.lineinfile:",
    "ansible.builtin.systemd_service:",
    "ansible.builtin.template:",
    "ansible.builtin.unarchive:",
    "ansible.builtin.user:",
)


# --- reading the committed playbooks and inventory --------------------------


def _task_blocks(*, body: str) -> list[str]:
    """Each `- name:`-introduced task of a role file, COMMENTS STRIPPED, in file order.

    The stripping is the load-bearing half. These files carry long prose about
    the trap each task exists to close, and that prose names the very directives
    the assertions below look for — `no_log`, `regexp`, a module, a `when`. A
    reader that matched the whole block would report a task as carrying a
    parameter its OWN COMMENT merely discusses, which fails in both directions:
    an assertion that something is present passes on a mention of it, and an
    assertion that something is absent fails on a warning about it.
    """
    return [
        "\n".join(
            line for line in f"- name: {chunk}".splitlines() if not line.lstrip().startswith("#")
        )
        for chunk in body.split("\n- name: ")[1:]
    ]


def _role_entries(*, play_text: str) -> list[tuple[str, str | None, tuple[str, ...]]]:
    """Every `roles:` entry of a play, as `(role, gate-or-None, tags)` in play order."""
    entries: list[tuple[str, str | None, tuple[str, ...]]] = []
    for match in _ROLE_ENTRY.finditer(play_text):
        gate = _WHEN_LINE.search(match["body"])
        tags = _TAGS_LINE.search(match["body"])
        entries.append(
            (
                match["role"],
                gate["expression"].strip() if gate else None,
                tuple(part.strip() for part in tags["tags"].split(",")) if tags else (),
            )
        )
    return entries


def _ci_pool_hosts() -> tuple[str, ...]:
    """Every host the inventory lists in `ci_pool`, which is what `ci-pool.yml` targets."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is "
        f"what `ci-pool.yml` targets, and a play with no hosts converges nothing"
    )
    return tuple(match["host"] for match in _INVENTORY_HOST.finditer(block["body"]))


# --- reading the role's variables -------------------------------------------


def _parse_scalar(*, raw: str) -> object:
    """One declared scalar as the value Ansible would hand the template.

    `true` and `false` become real booleans, because the template's conditionals
    read their flags as truthiness and a string `"false"` is truthy. `[]` is the
    empty list the default for a per-host list has to be.
    """
    text = raw.strip()
    if text == "[]":
        return []
    if text in (_TRUE, _FALSE):
        return text == _TRUE
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _role_variables(*, text: str, source: str) -> dict[str, object]:
    """Every `otel_collector_*` variable one committed YAML file declares.

    The FOLDED shape is tried before the plain scalar, and the order is not
    cosmetic: `key: >-` is itself a `key: <value>` line, so a scalar-first
    reader resolves the variable to the literal string `>-` and discards the
    indented value underneath it. A URL or a description read that way does not
    raise — it renders, into a unit carrying `>-` where a path belongs.
    """
    found: dict[str, object] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        folded = _FOLDED.match(line)
        if folded is not None:
            parts: list[str] = []
            while index < len(lines) and _CONTINUATION.match(lines[index]) is not None:
                parts.append(lines[index].strip())
                index += 1
            found[folded["key"]] = " ".join(parts)
            continue
        scalar = _SCALAR.match(line)
        if scalar is not None:
            found[scalar["key"]] = _parse_scalar(raw=scalar["value"])
            continue
        opened = _OPEN.match(line)
        if opened is not None:
            items: list[object] = []
            while index < len(lines) and _LIST_ITEM.match(lines[index]) is not None:
                item = _LIST_ITEM.match(lines[index])
                assert item is not None
                items.append(_parse_scalar(raw=item["item"]))
                index += 1
            found[opened["key"]] = items
            continue
        assert _ANY_KEY.match(line) is None, (
            f"{source} declares `{line.strip()}` in a shape this reader cannot parse. A "
            f"variable it cannot read is one it resolves as ABSENT, and the render's "
            f"StrictUndefined would then blame the template for a hole this reader dug — so "
            f"the shape is refused here instead. Declare it as a scalar, a `>-` folded "
            f"scalar, `[]`, or a `  - ` list"
        )
    return found


def _declared_variables() -> dict[str, dict[str, object]]:
    """The role's defaults and each relevant host's overrides, unresolved."""
    declared = {
        "defaults": _role_variables(
            text=_DEFAULTS.read_text(encoding="utf-8"), source=str(_DEFAULTS.name)
        )
    }
    for host in (_DEV_HOST, *_CI_POOL):
        path = _HOST_VARS / f"{host}.yml"
        assert path.is_file(), (
            f"{path.relative_to(_REPO_ROOT)} must be committed: a value that genuinely varies "
            f"by machine lives in host_vars, so a role never has to ask which host it is on"
        )
        declared[host] = _role_variables(text=path.read_text(encoding="utf-8"), source=path.name)
    return declared


def _environment() -> jinja2.Environment:
    """A Jinja2 environment configured as the `template` module configures its own."""
    return jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )


def _resolved(*, host: str) -> dict[str, object]:
    """One host's role variables, with every `{{ }}` reference resolved.

    Ansible resolves a variable's references lazily at use, so a default written
    over another default — `otel_collector_config_url` over
    `otel_collector_config_file` — picks up the HOST's override. Repeated passes
    to a fixed point is that same lazy resolution, done eagerly.
    """
    declared = _declared_variables()
    return _to_fixed_point(
        variables={**declared["defaults"], **declared[host]},
        source=f"defaults/main.yml or host_vars/{host}.yml",
    )


def _to_fixed_point(*, variables: dict[str, object], source: str) -> dict[str, object]:
    """Render every `{{ }}`-bearing value against the mapping until it stops changing.

    BOUNDED, and the bound is the point: two variables that reference each other
    never converge, they oscillate, so an unbounded loop would HANG the suite
    rather than fail it — and a hanging gate reaches no verdict at all, which is
    neither a pass nor a refusal. `test_the_variable_resolution_refuses_a_cycle`
    is the control that this bound is reached and reported.
    """
    environment = _environment()
    for _ in range(_RESOLUTION_PASSES):
        rendered = {
            key: (
                environment.from_string(value).render(**variables)
                if isinstance(value, str) and "{{" in value
                else value
            )
            for key, value in variables.items()
        }
        if rendered == variables:
            return variables
        variables = rendered
    raise AssertionError(
        f"the role's variables did not reach a fixed point in {_RESOLUTION_PASSES} passes, so "
        f"a `{{{{ }}}}` reference cycle is declared somewhere in {source}"
    )


def _rendered_unit(*, host: str) -> str:
    """`templates/otel-collector.service.j2` as this host's apply would write it."""
    template = _environment().from_string(_UNIT_TEMPLATE.read_text(encoding="utf-8"))
    return template.render(ansible_managed=_ANSIBLE_MANAGED, **_resolved(host=host))


def _directives(*, unit: str) -> tuple[str, ...]:
    """A rendered unit's directive and section lines — its comments are prose.

    The template's header explains the four postures by NAMING the directives
    each one carries and the dev host deliberately does not, so a reader matching
    the whole rendered file would find `k3s.service` and `ProtectSystem=strict`
    in every host's output — including the one host whose unit must carry
    neither. An absence claim read off prose is the one that cannot be made to
    fail.
    """
    return tuple(line for line in unit.splitlines() if line.strip() and not line.startswith("#"))


def _rendered_directives(*, host: str) -> str:
    """One host's rendered unit as its directives alone, for a presence or absence claim."""
    return "\n".join(_directives(unit=_rendered_unit(host=host)))


# --- the controls on the readers --------------------------------------------


def test_the_variable_resolution_refuses_a_cycle_rather_than_hanging() -> None:
    """A path written in terms of itself GROWS every pass, so the bound has to bite.

    `otel_collector_etc_dir: "{{ otel_collector_etc_dir }}/x"` is the realistic
    footgun — a plausible edit, and one that never converges: each pass
    substitutes the previous value and appends, so the string lengthens for ever.
    A resolver that looped until nothing changed would not FAIL on it, it would
    HANG, and a gate that reaches no verdict is neither a pass nor a refusal.

    (Note that a bare mutual reference, `{"a": "{{ b }}", "b": "{{ a }}"}`, does
    NOT exercise this: it settles after one pass into `{"a": "{{ a }}"}`, which
    renders to itself. The bound is reached by divergence, not by cycling.)
    """
    with pytest.raises(AssertionError, match="did not reach a fixed point"):
        _ = _to_fixed_point(variables={"a": "{{ a }}/x"}, source="a probe")


def test_the_first_write_reader_reports_no_write_in_a_task_list_that_has_none() -> None:
    """The reader that orders the refusals must not read "no write" as "write at 0".

    The two ordering assertions below pass when a refusal's position is LOWER
    than the first write's. Were a writer-less list to answer 0, every such
    assertion would fail on a correct file; were the writer set to go stale and
    stop matching, the answer has to be past the end rather than at the start —
    so the no-write answer is the length, and this is the control on it.
    """
    read_only = ["- name: Look at something\n  ansible.builtin.stat:\n    path: /x\n"]
    assert _first_write_index(blocks=read_only) == len(read_only), (
        "a task list carrying no write must answer past its end, so an ordering claim over "
        "it cannot pass by accident"
    )


def test_every_committed_posture_flag_is_a_yaml_boolean_literal() -> None:
    """The render reads the flags as truthiness, so a string declaration would lie.

    `"false"` is truthy in Jinja and false to Ansible's `bool` filter. The
    template deliberately uses no `bool` — Jinja has no such filter, so a
    template that did could not be rendered here without this file
    re-implementing it, and a re-implemented filter is free to disagree with the
    one on the host. Holding every committed declaration to a real YAML boolean
    is what makes the two engines agree instead.
    """
    declared = _declared_variables()
    flags = ("otel_collector_manage_install", "otel_collector_hardened")
    for source, variables in declared.items():
        for flag in flags:
            if flag not in variables:
                continue
            assert isinstance(variables[flag], bool), (
                f"{source} declares {flag} as {variables[flag]!r}, which is not a YAML "
                f"boolean. The unit template branches on this value's TRUTHINESS, and every "
                f'non-empty string is truthy — so a quoted `"false"` would render the '
                f"hardened shape while reading as the opposite"
            )
    assert any(flag in declared["defaults"] for flag in flags), (
        f"{_DEFAULTS.name} must declare {flags} so a host that overrides neither resolves to "
        f"the posture it already has; declared={sorted(declared['defaults'])}"
    )


# --- the play wiring --------------------------------------------------------


def test_ci_pool_applies_the_collector_role_to_every_pool_node_ungated() -> None:
    """Assertion 1: in `ci-pool.yml`'s roles, with no gate, tagged, after `ci_observability`.

    "Every host of the `ci_pool` group" is DERIVED from the inventory rather than
    assumed, so a fourth pool node added there is a node this assertion already
    covers — which is the property the telemetry section's "a node that joins the
    cluster is reported with no per-node configuration edit" depends on.
    """
    assert _ci_pool_hosts() == _CI_POOL, (
        f"the inventory's `ci_pool` group is {_ci_pool_hosts()}, and this file states the pool "
        f"as {_CI_POOL}. A node added to the group needs its collector shape declared in its "
        f"own host_vars before the ungated role below can converge it, so the two must be "
        f"reconciled together rather than drifting apart silently"
    )
    entries = _role_entries(play_text=_CI_POOL_PLAY.read_text(encoding="utf-8"))
    names = [role for role, _, _ in entries]
    assert _ROLE_NAME in names, (
        f"{_CI_POOL_PLAY.name} must apply the `{_ROLE_NAME}` role: the fleet host guard refuses "
        f"the collector repository's hand-run installers, so this play is the ONLY path by "
        f"which a merged collector configuration reaches a pool node, and a play that never "
        f"names a collector converges none. Roles today: {names}"
    )
    role, gate, tags = next(entry for entry in entries if entry[0] == _ROLE_NAME)
    assert gate is None, (
        f"the `{role}` entry carries `when: {gate}`. Every node the cluster lists must have its "
        f"collector converged whatever its `cluster_role` or factory posture, so this entry "
        f"takes no gate — a gated one would leave a silent node indistinguishable from a quiet one"
    )
    assert tags == (_ROLE_NAME,), (
        f"the `{role}` entry must carry `tags: [{_ROLE_NAME}]` so an operator can converge the "
        f"collector alone; got {tags}"
    )
    assert names.index(_ROLE_NAME) > names.index("ci_observability"), (
        f"`{_ROLE_NAME}` must run after `ci_observability`, which installs the node-local OTLP "
        f"emitters this collector receives from; order today: {names}"
    )
    assert names[-1] == "sandbox_image_prune", (
        f"`sandbox_image_prune` must stay LAST: arming its timer prunes this node's containerd "
        f"on the spot, so it follows every role that could still install a manifest pinning an "
        f"image; order today: {names}"
    )


def test_removing_the_role_from_the_play_is_what_the_first_assertion_fails_on() -> None:
    """The negative control: with the entry deleted, the play applies no collector.

    Without it the assertion above could be passing on something other than the
    committed entry — a role name that appears in a comment, say — and would go
    on passing after the entry was dropped.
    """
    committed = _CI_POOL_PLAY.read_text(encoding="utf-8")
    without = _ROLE_ENTRY.sub(
        lambda match: "" if match["role"] == _ROLE_NAME else match.group(0), committed
    )
    assert without != committed, (
        f"the control could not remove the `{_ROLE_NAME}` entry from {_CI_POOL_PLAY.name}, so "
        f"it is not measuring anything"
    )
    names = [role for role, _, _ in _role_entries(play_text=without)]
    assert _ROLE_NAME not in names, (
        f"with its `roles:` entry deleted the play still resolves `{_ROLE_NAME}`, so the "
        f"assertion above is reading something other than the entry; resolved={names}"
    )


def test_the_dev_host_play_still_applies_the_role_it_applied_before() -> None:
    """The regression arm on the other play: `vps` keeps converging its own collector."""
    entries = _role_entries(play_text=_DEV_HOST_PLAY.read_text(encoding="utf-8"))
    role, gate, tags = next(
        (entry for entry in entries if entry[0] == _ROLE_NAME), ("", "absent", ())
    )
    assert (role, gate, tags) == (_ROLE_NAME, None, (_ROLE_NAME,)), (
        f"{_DEV_HOST_PLAY.name} must keep applying `{_ROLE_NAME}`, ungated and tagged: the pool "
        f"work must not move the dev host's collector off its converge; got {(role, gate, tags)}"
    )


# --- the per-host configuration -------------------------------------------


def test_the_configuration_is_read_from_the_file_each_host_names() -> None:
    """Assertions 2 and 3: one variable names the shape, and `vps` still resolves `config.yaml`."""
    defaults = _declared_variables()["defaults"]
    assert defaults.get("otel_collector_config_file") == _CONFIG_FILES[_DEV_HOST], (
        f"{_DEFAULTS.name} must default `otel_collector_config_file` to "
        f"`{_CONFIG_FILES[_DEV_HOST]}`, so a host written before the variable existed resolves "
        f"to the shape it already runs; got {defaults.get('otel_collector_config_file')!r}"
    )
    for host, config_file in _CONFIG_FILES.items():
        resolved = _resolved(host=host)
        assert resolved["otel_collector_config_file"] == config_file, (
            f"{host} must name `{config_file}` as its collector shape; got "
            f"{resolved['otel_collector_config_file']!r}"
        )
        url = resolved["otel_collector_config_url"]
        assert isinstance(url, str) and url.endswith(f"/{config_file}"), (
            f"{host}'s otel_collector_config_url must read that file out of "
            f"thewoolleyman/otel-collector rather than a second source of truth; got {url!r}"
        )
        assert "raw.githubusercontent.com/thewoolleyman/otel-collector/" in url, url


def test_each_pool_node_runs_its_collector_as_the_service_account() -> None:
    """Assertion 3's second half: the dedicated system user, on all three nodes."""
    for host in _CI_POOL:
        resolved = _resolved(host=host)
        assert resolved["otel_collector_user"] == _SERVICE_ACCOUNT, resolved
        assert resolved["otel_collector_group"] == _SERVICE_ACCOUNT, resolved
        unit = _rendered_directives(host=host)
        assert f"User={_SERVICE_ACCOUNT}" in unit, unit
        assert f"Group={_SERVICE_ACCOUNT}" in unit, unit
    dev_host = _resolved(host=_DEV_HOST)
    assert dev_host["otel_collector_user"] == "ubuntu", (
        f"{_DEV_HOST}'s collector has always run as the login account, with hostmetrics "
        f"scraping the whole machine; moving it to a system user is a behaviour change, not "
        f"this transcription; got {dev_host['otel_collector_user']!r}"
    )


# --- the pinned binary and the service account ------------------------------


def test_a_pool_node_creates_the_account_and_installs_the_pinned_binary() -> None:
    """Assertion 4: the install path exists, is pinned, is verified, and is version-gated."""
    assert _BINARY_TASKS.is_file(), (
        f"{_BINARY_TASKS.relative_to(_REPO_ROOT)} must be committed: provisioning the collector "
        f"binary — read the installed version, download, verify, extract, install, clean up — is "
        f"one gated concern, reached only on a host that declares "
        f"`otel_collector_manage_install`, and a dev host must not reach it at all"
    )
    defaults = _declared_variables()["defaults"]
    assert defaults.get("otel_collector_manage_install") is False, (
        f"{_DEFAULTS.name} must default `otel_collector_manage_install` to false, so the dev "
        f"host keeps asserting the binary rather than installing one; got "
        f"{defaults.get('otel_collector_manage_install')!r}"
    )
    assert defaults.get("otel_collector_binary_version") == _BINARY_VERSION, defaults
    assert defaults.get("otel_collector_binary_sha256") == _BINARY_SHA256, defaults

    tasks = _TASKS.read_text(encoding="utf-8")
    include = next(
        (block for block in _task_blocks(body=tasks) if "ansible.builtin.include_tasks:" in block),
        "",
    )
    assert (
        "binary.yml" in include
    ), f"{_TASKS.name} must include the binary provisioning file; included today:\n{include}"
    assert "when: otel_collector_manage_install | bool" in include, (
        f"that include must be gated on `otel_collector_manage_install`, which is what makes "
        f"the dev host install no binary and create no account;\n{include}"
    )

    binary = _BINARY_TASKS.read_text(encoding="utf-8")
    blocks = _task_blocks(body=binary)
    account = next((block for block in blocks if "ansible.builtin.user:" in block), "")
    assert "system: true" in account, account
    assert "create_home: false" in account, account
    assert "/usr/sbin/nologin" in account, account
    assert f"name: {_SERVICE_ACCOUNT}" in account or "otel_collector_user" in account, account

    download = next((block for block in blocks if "ansible.builtin.get_url:" in block), "")
    assert 'checksum: "sha256:{{ otel_collector_binary_sha256 }}"' in download, (
        f"the tarball must be verified against the pinned sha256 as it is downloaded, so a "
        f"substituted archive is refused before anything is extracted;\n{download}"
    )
    install = next(
        (
            block
            for block in blocks
            if 'dest: "{{ otel_collector_binary }}"' in block and "mode:" in block
        ),
        "",
    )
    assert 'mode: "0755"' in install and "owner: root" in install, install

    # An already-installed 0.147.0 is left alone: every step that downloads,
    # extracts or installs is gated on a fact derived from the version the host
    # reports, so a converged node runs none of them and reports no change.
    gated = [block for block in blocks if "otel_collector_binary_install_needed" in block]
    assert any("ansible.builtin.set_fact:" in block for block in gated), (
        f"{_BINARY_TASKS.name} must decide `otel_collector_binary_install_needed` from the "
        f"version the host REPORTS, so an already-installed {_BINARY_VERSION} is untouched;\n"
        f"{binary}"
    )
    for block in blocks:
        if not any(module in block for module in ("get_url:", "unarchive:")):
            continue
        assert "when: otel_collector_binary_install_needed" in block, (
            f"this task downloads or extracts on every apply, so a converged node is reported "
            f"as changed and the pin buys nothing:\n{block}"
        )
    for block in blocks:
        if "ansible.builtin.command:" not in block:
            continue
        assert "changed_when: false" in block, (
            f"the version read is a READ; without `changed_when: false` it reports a change of "
            f"its own on an already-matching host:\n{block}"
        )


def test_a_dev_host_still_only_asserts_the_binary_it_never_installs() -> None:
    """Assertion 5: the refusal survives, and it is withheld where the role installs."""
    tasks = _TASKS.read_text(encoding="utf-8")
    refusal = next(
        (
            block
            for block in _task_blocks(body=tasks)
            if "otel_collector_binary_stat.stat.exists" in block
        ),
        "",
    )
    assert refusal, (
        f"{_TASKS.name} must keep refusing a host that carries no collector binary: on the dev "
        f"host the pinned download belongs to the collector repository's own installers, and a "
        f"converge that silently proceeded would install a unit nothing can start"
    )
    assert "when: not (otel_collector_manage_install | bool)" in refusal, (
        f"that refusal must be withheld where the role installs the binary itself — on a "
        f"rebuilt pool node the binary is legitimately absent at the first apply;\n{refusal}"
    )
    assert (
        _resolved(host=_DEV_HOST)["otel_collector_manage_install"] is False
    ), f"{_DEV_HOST} must resolve `otel_collector_manage_install` false"
    for host in _CI_POOL:
        assert _resolved(host=host)["otel_collector_manage_install"] is True, (
            f"{host} must resolve `otel_collector_manage_install` true: its collector was "
            f"installed by a hand-run script the fleet host guard now refuses, so this role is "
            f"the only thing left that can place the binary"
        )


# --- the ingest-key environment entry ---------------------------------------


def _first_write_index(*, blocks: list[str]) -> int:
    """The position of the first task in `tasks/main.yml` that writes anything."""
    for index, block in enumerate(blocks):
        if any(module in block for module in _WRITING_MODULES):
            return index
    return len(blocks)


def test_the_role_appends_each_ingest_key_the_environment_file_lacks() -> None:
    """Assertion 6: appended under `no_log`, created 0600 root:root, never rewritten."""
    for host in _CI_POOL:
        keys = _resolved(host=host)["otel_collector_env_from_controller"]
        assert keys == [_CONTROLLER_KEY], (
            f"{host} must name {_CONTROLLER_KEY} in `otel_collector_env_from_controller`: the "
            f"control node carries it under the credential wrapper, and nothing on the node "
            f"does; got {keys!r}"
        )
    assert _declared_variables()["defaults"].get("otel_collector_env_from_controller") == [], (
        f"{_DEFAULTS.name} must default `otel_collector_env_from_controller` to `[]`, so a host "
        f"that names none has its environment file provisioned outside the role, as the dev "
        f"host's is"
    )

    tasks = _TASKS.read_text(encoding="utf-8")
    append = next(
        (block for block in _task_blocks(body=tasks) if "ansible.builtin.lineinfile:" in block), ""
    )
    assert append, (
        f"{_TASKS.name} must APPEND a missing `KEY=value` line rather than create the file only "
        f"when absent: hp's `/etc/otel-collector/.env` already carries the agent-activity keys, "
        f"so a create-only render would leave the ingest key off the one host that has a file"
    )
    assert (
        "no_log: true" in append
    ), f"the appended line carries a credential, so the task must be `no_log: true`;\n{append}"
    assert "create: true" in append, append
    assert 'mode: "0600"' in append and "owner: root" in append and "group: root" in append, append
    assert "lookup('ansible.builtin.env'" in append, (
        f"the value must be read from the CONTROL NODE's environment, which is where the "
        f"credential wrapper projects it;\n{append}"
    )
    assert "regexp:" not in append, (
        f"a `regexp:` makes `lineinfile` REWRITE the matching line, so a key the file already "
        f"sets would be overwritten with the control node's value;\n{append}"
    )
    assert "rejectattr('rc', 'equalto', 0)" in append, (
        f"the append must run only for a key the file does NOT already set, read with `grep "
        f"--quiet`, so an existing key is never rewritten;\n{append}"
    )


def test_the_role_refuses_an_unset_controller_variable_before_any_write() -> None:
    """Assertion 7: named, and refused ahead of every write the role makes."""
    blocks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
    refusals = [
        index
        for index, block in enumerate(blocks)
        if "ansible.builtin.assert:" in block
        and "lookup('ansible.builtin.env'" in block
        and "otel_collector_env_from_controller" in block
    ]
    assert refusals, (
        f"{_TASKS.name} must refuse a key `otel_collector_env_from_controller` names that the "
        f"control node's environment does not set. Without it the apply writes an environment "
        f"line with an EMPTY value and the collector starts and exports nothing — a silent "
        f"node, which is the one failure the dead-man trigger cannot tell from a quiet one"
    )
    refusal = blocks[refusals[0]]
    assert "otel_collector_env_from_controller" in refusal and "{{ item }}" in refusal, (
        f"the refusal must NAME the variable it could not read, so an operator who forgot the "
        f"credential wrapper is told which one;\n{refusal}"
    )
    assert refusals[0] < _first_write_index(blocks=blocks), (
        f"the refusal stands at position {refusals[0]} and the first write at "
        f"{_first_write_index(blocks=blocks)}. A refusal after a write leaves the host half "
        f"converged, which is the state a re-run cannot distinguish from a fresh host"
    )


def test_the_role_asserts_the_rendered_kubeconfig_after_converging_its_identity() -> None:
    """The scoped cluster identity is checked after its managed render can run."""
    blocks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
    refusals = [
        index
        for index, block in enumerate(blocks)
        if "ansible.builtin.assert:" in block and "otel_collector_kubeconfig_path" in block
    ]
    assert refusals, (
        f"{_TASKS.name} must refuse a host whose `otel_collector_kubeconfig_path` is set and "
        f"whose file is absent. poweredge's collector reads every kubelet through that scoped "
        f"read-only identity; absent it the unit starts, fails to authenticate, and reports "
        f"nothing about any node"
    )
    refusal = blocks[refusals[0]]
    assert "{{ otel_collector_kubeconfig_path }}" in refusal, (
        f"the refusal must NAME the path it could not find, so an operator is told which file "
        f"the role was meant to render;\n{refusal}"
    )
    flushes = [
        index
        for index, block in enumerate(blocks)
        if "ansible.builtin.meta: flush_handlers" in block
    ]
    assert flushes and refusals[0] > flushes[-1], (
        f"the kubeconfig assertion must be a post-check after the identity handlers flush: "
        f"assertion={refusals[0]}, flushes={flushes}"
    )
    assert _resolved(host=_POWEREDGE)["otel_collector_kubeconfig_path"] == (
        "/etc/otel-collector/kubeconfig"
    ), _resolved(host=_POWEREDGE)
    for host in (_DEV_HOST, _GMKTEC, _HP):
        assert _resolved(host=host)["otel_collector_kubeconfig_path"] == "", (
            f"{host}'s collector reads no kubelet, so it must name no kubeconfig — a path set "
            f"here would make the role refuse a file nothing needs"
        )


def test_cluster_identity_artifacts_follow_the_configured_collector_ref() -> None:
    """The CI runner alone fetches and converges its three identity inputs."""
    defaults = _declared_variables()["defaults"]
    assert defaults.get("otel_collector_cluster_identity") is False, defaults

    for host, expected in {
        _POWEREDGE: True,
        _GMKTEC: False,
        _HP: False,
        _DEV_HOST: False,
    }.items():
        assert _resolved(host=host)["otel_collector_cluster_identity"] is expected, host

    artifacts = (
        (
            "otel_collector_identity_rbac_url",
            "k8s/otel-collector-rbac.yaml",
            "/usr/local/lib/otel-collector/otel-collector-rbac.yaml",
            'mode: "0644"',
        ),
        (
            "otel_collector_identity_render_script_url",
            "scripts/render-k8s-identity.sh",
            "/usr/local/lib/otel-collector/render-k8s-identity.sh",
            'mode: "0755"',
        ),
        (
            "otel_collector_identity_unit_url",
            "systemd/otel-collector-identity.ci-runner-host.service",
            "/etc/systemd/system/otel-collector-identity.service",
            'mode: "0644"',
        ),
    )
    poweredge = _resolved(host=_POWEREDGE)
    blocks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
    for variable, source, destination, mode in artifacts:
        url = poweredge.get(variable)
        assert isinstance(url, str) and url.endswith(f"/{source}"), (variable, url)
        assert f"/{poweredge['otel_collector_config_ref']}/" in url, (variable, url)
        fetches = [
            block
            for block in blocks
            if "lookup('ansible.builtin.url'" in block and variable in block
        ]
        assert len(fetches) == 1, (variable, fetches)
        installs = [block for block in blocks if destination in block]
        assert len(installs) == 1, (destination, installs)
        install = installs[0]
        assert "ansible.builtin.copy:" in install and mode in install, install
        assert "owner: root" in install and "group: root" in install, install
        assert "otel_collector_cluster_identity | bool" in install, install
        assert "Run the collector cluster identity" in install, install
        assert "Restart the collector onto its managed configuration" in install, install

    handlers = _task_blocks(body=_HANDLERS.read_text(encoding="utf-8"))
    names = [block.splitlines()[0].removeprefix("- name: ") for block in handlers]
    reload_index = names.index("Reload systemd for the managed collector units")
    identity_index = names.index("Run the collector cluster identity")
    restart_index = names.index("Restart the collector onto its managed configuration")
    assert reload_index < identity_index < restart_index, names
    identity_handler = handlers[identity_index]
    assert 'name: "{{ otel_collector_identity_unit_name }}"' in identity_handler
    assert "state: started" in identity_handler
    assert "otel_collector_identity_unit_stat.stat.exists" in identity_handler


# --- the rendered unit ------------------------------------------------------


def test_the_rendered_unit_for_poweredge_carries_what_only_poweredge_needs() -> None:
    """Assertion 8: the host environment file, the scoped identity, and the start order."""
    poweredge = _rendered_directives(host=_POWEREDGE)
    assert _POWEREDGE_HOST_ENV in poweredge, (
        f"poweredge's unit must name the installer-rendered non-secret environment file, "
        f"listed BEFORE the secret one so a value in `.env` wins;\n{poweredge}"
    )
    assert poweredge.index(_POWEREDGE_HOST_ENV) < poweredge.index(
        "EnvironmentFile=/etc/otel-collector/.env"
    ), poweredge
    assert _POWEREDGE_KUBECONFIG in poweredge, poweredge
    after = next(line for line in poweredge.splitlines() if line.startswith("After="))
    for unit in _POWEREDGE_AFTER_UNITS:
        assert unit in after.split("=", 1)[1].split(), (
            f"poweredge's `{after}` must order the collector after `{unit}`: the k3s datastore "
            f"is a tmpfs wiped at every boot, so the ServiceAccount behind its kubeconfig is "
            f"re-created and the kubeconfig re-rendered before the collector can authenticate"
        )

    dev_host = _rendered_directives(host=_DEV_HOST)
    for absent in (_POWEREDGE_HOST_ENV, _POWEREDGE_KUBECONFIG, *_POWEREDGE_AFTER_UNITS):
        assert absent not in dev_host, (
            f"{_DEV_HOST}'s rendered unit carries `{absent}`, which belongs to the pool's "
            f"cluster-reading collector. This host reads no kubelet and runs no k3s;\n{dev_host}"
        )


def test_the_rendered_unit_for_every_pool_node_is_sandboxed_and_the_dev_hosts_is_not() -> None:
    """Assertion 9: the three hardening directives, on the pool only."""
    for host in _CI_POOL:
        unit = _rendered_directives(host=host)
        for directive in _HARDENING:
            assert directive in unit, (
                f"{host}'s rendered unit must carry `{directive}`, as the two sibling units in "
                f"the collector repository do: this collector runs as a dedicated system user "
                f"that never had anything else, so the sandbox costs it nothing;\n{unit}"
            )
    dev_host = _rendered_directives(host=_DEV_HOST)
    for directive in _HARDENING:
        assert directive not in dev_host, (
            f"{_DEV_HOST}'s rendered unit carries `{directive}`. Its collector runs as the login "
            f"account with hostmetrics scraping the whole machine, so a sandbox here is a "
            f"behaviour change and belongs to its own decision, not to this converge;\n{dev_host}"
        )


def test_the_dev_hosts_rendered_unit_is_the_unit_it_already_runs() -> None:
    """The regression arm: every new variable leaves `vps`'s rendered output alone."""
    assert _directives(unit=_rendered_unit(host=_DEV_HOST)) == _DEV_HOST_DIRECTIVES, (
        f"the new per-host variables must leave {_DEV_HOST}'s rendered unit untouched, so the "
        f"pool work cannot restart a collector it was not about.\n"
        f"expected: {_DEV_HOST_DIRECTIVES}\n"
        f"rendered: {_directives(unit=_rendered_unit(host=_DEV_HOST))}"
    )


# --- the operator's commands ------------------------------------------------


def test_the_readme_carries_the_pools_drift_and_apply_commands() -> None:
    """The converge an operator runs, under the wrapper that projects the ingest key."""
    readme = _README.read_text(encoding="utf-8")
    for command in (_CI_POOL_DRIFT, _CI_POOL_APPLY):
        assert command in readme, (
            f"{_README.name} must carry `{command}`. The apply reads the ingest key from the "
            f"CONTROL NODE's environment, which only the credential wrapper projects — a bare "
            f"`just ansible-apply` refuses at the preflight, naming a variable the operator has "
            f"no reason to think is missing"
        )
