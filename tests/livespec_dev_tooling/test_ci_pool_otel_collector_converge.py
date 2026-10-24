"""Every `ci_pool` node's collector is converged by `ansible/ci-pool.yml`, per host.

WHY IT EXISTS (work-item livespec-dev-tooling-ool6ws, plan
kubernetes-node-observability, charter root cause 5). The three pool nodes'
collectors were installed by HAND-RUN scripts in `thewoolleyman/otel-collector`
(`scripts/install-ci-runner-host.sh` on poweredge,
`scripts/install-hp-factory-host.sh` on hp) and NOTHING in `ansible/ci-pool.yml`
named a collector. The fleet host guard refuses a by-hand host change, so those
installers can no longer be run at all: this role is now the only path by which
the merged configurations reach the nodes. `## Runner-pool node telemetry` says
it outright — every pool node's collector, its configuration, its unit, its
pinned binary and its ingest-key environment entry MUST be converged by
`ansible/ci-pool.yml`, and a hand-run installer MUST NOT be the deployment path.

WHAT IS RESOLVED AND WHY IT IS RESOLVED RATHER THAN RUN. `ci-pool.yml` reaches a
real cluster, so no test may apply it; and `ansible-playbook` is invoked through
`uvx` in this repository rather than imported, so neither Ansible nor Jinja is
importable in this suite (the package is deliberately dependency-free — see
`pyproject.toml`). What CAN be resolved off-host is exactly what the Definition
of Done asks about: the play's role entry and its gate, each host's variables as
the inventory's `host_vars` and the role's `defaults/main.yml` supply them, and
the unit those variables RENDER. So this file carries a tiny variable resolver
and a tiny template renderer, and two CONTROL tests keep both honest —
`test_the_template_stays_inside_the_vocabulary_this_renderer_resolves` fails the
moment the template grows a construct this renderer would resolve differently
from Jinja, and `test_the_resolution_fails_when_ci_pool_yml_omits_the_role` is
the negative control proving the play reading is load-bearing rather than
vacuous. A renderer that quietly disagreed with Jinja would be worse than none:
it would report a unit the host never gets.

WHAT IS DERIVED AND WHAT IS STATED. The `ci_pool` membership, the role's gate,
every variable and every rendered line are READ out of the committed tree. The
three hosts' collector SHAPES and the pinned binary's version and digest are
STATED, because the Definition of Done states them and a silent change to either
is the defect these tests exist to catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_CI_POOL_PLAY = _ANSIBLE / "ci-pool.yml"
_DEV_HOST_PLAY = _ANSIBLE / "dev-host.yml"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars"
_ROLE = _ANSIBLE / "roles" / "otel_collector"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_UNIT_TEMPLATE = _ROLE / "templates" / "otel-collector.service.j2"
_ROLE_DOC = _ROLE / "HOST_VARS.md"
_ANSIBLE_README = _ANSIBLE / "README.md"

# The dev host, which is also the control node. It stays on `config.yaml` and
# stays unhardened and unmanaged: its collector has always run as the login
# account with hostmetrics scraping the whole machine.
_DEV_HOST = "vps"

# The three pool nodes and the collector shape each one runs, from the
# Definition of Done. Each name is a file in `thewoolleyman/otel-collector`.
_POOL_CONFIG_FILES = {
    "poweredge-xubuntu": "config.ci-runner-host.yaml",
    "gmktec-xubuntu": "config.k3s-agent-host.yaml",
    "hp-xubuntu": "config.hp-factory.yaml",
}

# The dedicated unprivileged account every pool node's collector runs as. Never
# a human login: a pool node has no resident checkout to run out of and the
# collector must not inherit a human's cluster credential.
_SERVICE_USER = "otel-collector"

# The pinned binary. The digest is the one upstream publishes for the amd64
# release tarball in
# `opentelemetry-collector-releases_otelcol-contrib_checksums.txt` at v0.147.0
# (read 2026-10-24), which is the same pin both retired installers carried.
_BINARY_VERSION = "0.147.0"
_BINARY_SHA256 = "17cc9a8f2e44e80ceff0e0647aec18b28a6b1b17823040e362ddc4a9fd017ccc"
_BINARY_DEST = "/usr/local/bin/otelcol-contrib"
_UPSTREAM_RELEASES = (
    "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/"
)

# poweredge's two preconditions, owned by the collector repository's installer
# and asserted rather than written here: the non-secret host environment file
# the merged configuration reads `HONEYCOMB_API_ENDPOINT` from, and the scoped
# read-only ServiceAccount kubeconfig `otel-collector-identity.service` renders
# at every boot (the k3s datastore is a tmpfs, wiped each boot).
_POWEREDGE_HOST_ENV = "/etc/otel-collector/host.env"
_POWEREDGE_KUBECONFIG = "/etc/otel-collector/kubeconfig"
_POWEREDGE_ORDER_AFTER = ("k3s.service", "otel-collector-identity.service")

# The sandbox the two sibling shapes carry and the dev host deliberately does
# not: a dedicated system user that never had anything else can be confined,
# a login account scraping its own machine cannot.
_HARDENING = ("ProtectSystem=strict", "ProtectHome=true", "PrivateTmp=true")

_CONTROLLER_KEY = "HONEYCOMB_INGEST_KEY_LIVESPEC"

# Every module that WRITES on the target. The two refusals the Definition of
# Done requires to fire "before it writes anything" are resolved against this
# set, so a refusal placed after any of them fails here.
_WRITER_MODULES = (
    "ansible.builtin.copy:",
    "ansible.builtin.template:",
    "ansible.builtin.file:",
    "ansible.builtin.lineinfile:",
    "ansible.builtin.blockinfile:",
    "ansible.builtin.get_url:",
    "ansible.builtin.unarchive:",
    "ansible.builtin.user:",
    "ansible.builtin.group:",
    "ansible.builtin.systemd_service:",
)

_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)
_TAGS_LINE = re.compile(r"^      tags: (?P<tags>.+)$", re.MULTILINE)
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_INVENTORY_HOST = re.compile(r"^            (?P<host>[\w-]+):$", re.MULTILINE)

# The only two things a value in this tree's variable files may be, as far as
# this resolver is concerned: a scalar (possibly a `>-` folded one, possibly
# carrying `{{ }}` references) or a flat list of scalars. A nested mapping — and
# `host_vars` is full of them, for other roles — is skipped rather than guessed
# at, because every variable this role reads is one of the two.
_TOP_LEVEL_KEY = re.compile(r"^(?P<key>[a-z_][a-z0-9_]*):(?P<rest>.*)$")
_LIST_ITEM = re.compile(r"^  - (?P<item>.+)$")
_REFERENCE = re.compile(r"\{\{ (?P<name>[a-z_][a-z0-9_]*) \}\}")

# The renderer's whole grammar. Anything else in the template is a construct
# this file would resolve differently from Jinja.
_SUBSTITUTION = re.compile(r"\{\{ [a-z_][a-z0-9_]* \}\}")
_IF_TAG = re.compile(r"^\{% if (?P<name>[a-z_][a-z0-9_]*) %\}$")
_FOR_TAG = re.compile(r"^\{% for (?P<item>[a-z_][a-z0-9_]*) in (?P<sequence>[a-z_][a-z0-9_]*) %\}$")
_END_TAG = re.compile(r"^\{% end(?:if|for) %\}$")
_ANY_TAG = re.compile(r"\{%.*?%\}")
_ANY_SUBSTITUTION = re.compile(r"\{\{.*?\}\}")

# What a resolved variable may BE. Spelled as a closed union rather than
# `object` because the renderer below has to tell a sequence it may loop over
# from a scalar it may substitute, and a reader that cannot tell them apart
# would silently emit a Python repr into a systemd unit.
_Value = str | bool | tuple[str, ...]

# Supplied the way Ansible supplies them, so the renderer needs no fact-gathering.
_FACTS: dict[str, _Value] = {
    "ansible_managed": "Ansible managed",
}


# --- reading the committed variable files -----------------------------------


def _parse_variables(*, text: str) -> dict[str, _Value]:
    """Every top-level scalar or flat-list variable one variable file declares."""
    lines = text.split("\n")
    found: dict[str, _Value] = {}
    index = 0
    while index < len(lines):
        match = _TOP_LEVEL_KEY.match(lines[index])
        if match is None:
            index += 1
            continue
        key = match["key"]
        rest = match["rest"].strip()
        if rest.startswith(">"):
            folded, index = _folded_scalar(lines=lines, index=index + 1)
            found[key] = folded
            continue
        if rest == "":
            items, index = _flat_list(lines=lines, index=index + 1)
            if items is not None:
                found[key] = items
            continue
        found[key] = _scalar(text=rest)
        index += 1
    return found


def _folded_scalar(*, lines: list[str], index: int) -> tuple[str, int]:
    """A `>-` block's continuation lines, folded to one space-joined scalar."""
    collected: list[str] = []
    while index < len(lines) and (lines[index].startswith("  ") or lines[index].strip() == ""):
        if lines[index].strip() == "":
            break
        collected.append(lines[index].strip())
        index += 1
    return " ".join(collected), index


def _flat_list(*, lines: list[str], index: int) -> tuple[tuple[str, ...] | None, int]:
    """A `  - item` block's items, or `None` when the block is not a flat list."""
    items: list[str] = []
    while index < len(lines):
        item = _LIST_ITEM.match(lines[index])
        if item is None:
            break
        items.append(str(_scalar(text=item["item"].strip())))
        index += 1
    return (tuple(items) or None), index


def _scalar(*, text: str) -> _Value:
    """One inline value: an empty list, a boolean, or a quote-stripped string."""
    value = text.split(" #", 1)[0].strip()
    if value == "[]":
        return ()
    if value in ("true", "false"):
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _resolved(*, variables: dict[str, _Value]) -> dict[str, _Value]:
    """The same variables with every `{{ name }}` reference substituted."""
    merged: dict[str, _Value] = {**_FACTS, **variables}
    for _ in range(len(merged) + 1):
        pending = [key for key, value in merged.items() if _REFERENCE.search(str(value))]
        if not pending:
            return merged
        for key in pending:
            merged[key] = _REFERENCE.sub(
                lambda found: str(merged.get(found["name"], found.group(0))), str(merged[key])
            )
    raise AssertionError(f"a variable reference cycle in {sorted(variables)}")


def _variables(*, host: str) -> dict[str, _Value]:
    """One host's `otel_collector_*` variables: the role's defaults, then host_vars."""
    assert _DEFAULTS.is_file(), f"{_DEFAULTS.relative_to(_REPO_ROOT)} must be committed"
    merged = _parse_variables(text=_DEFAULTS.read_text(encoding="utf-8"))
    host_file = _HOST_VARS / f"{host}.yml"
    assert host_file.is_file(), (
        f"{host_file.relative_to(_REPO_ROOT)} must be committed: a pool node's collector "
        f"shape is a per-host value, and the play reads it from host_vars"
    )
    overrides = {
        key: value
        for key, value in _parse_variables(text=host_file.read_text(encoding="utf-8")).items()
        if key.startswith("otel_collector_")
    }
    return _resolved(variables={**merged, **overrides, "inventory_hostname": host})


# --- reading the committed plays and inventory ------------------------------


def _role_entry(*, play_text: str, role: str) -> tuple[str | None, str | None] | None:
    """One play's entry for `role`, as `(gate-or-None, tags-or-None)`, else `None`."""
    for match in _ROLE_ENTRY.finditer(play_text):
        if match["role"] != role:
            continue
        gate = _WHEN_LINE.search(match["body"])
        tags = _TAGS_LINE.search(match["body"])
        return (
            gate["expression"].strip() if gate else None,
            tags["tags"].strip() if tags else None,
        )
    return None


def _ci_pool_hosts() -> tuple[str, ...]:
    """Every host the inventory places in `ci_pool`, which is what the play targets."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is "
        f"what ci-pool.yml targets, and a play with no hosts converges nothing"
    )
    hosts = tuple(match["host"] for match in _INVENTORY_HOST.finditer(block["body"]))
    assert hosts, f"{_INVENTORY.name}: `ci_pool` must list at least one host"
    return hosts


def _assert_play_converges_the_collector(*, play_text: str, hosts: tuple[str, ...]) -> None:
    """The play runs `otel_collector` on EVERY named host, ungated and tagged.

    Lifted out of its test so the negative control can call it with a play text
    that omits the entry: an assertion nothing can make fail is not evidence.
    """
    entry = _role_entry(play_text=play_text, role="otel_collector")
    assert entry is not None, (
        "ansible/ci-pool.yml must carry an `otel_collector` role entry: the fleet host guard "
        "refuses a by-hand host change, so a pool node's collector reaches it through this "
        "play or through nothing at all"
    )
    gate, tags = entry
    assert gate is None, (
        f"the `otel_collector` entry must carry NO `when:` — every pool node reports, "
        f"whatever its cluster_role or factory posture (`## Runner-pool node telemetry`); "
        f"it carries {gate!r}, which would silence {len(hosts)} nodes down to a subset"
    )
    assert tags == "[otel_collector]", (
        f"the entry must be tagged `[otel_collector]` so an operator can converge the "
        f"collector alone; it carries {tags!r}"
    )


# --- the renderer -----------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class _Text:
    """One literal template line, whose `{{ name }}` references are substituted."""

    line: str


@dataclass(frozen=True, kw_only=True)
class _Conditional:
    """One `{% if name %}` block and the nodes it guards."""

    name: str
    body: tuple[_Node, ...]


@dataclass(frozen=True, kw_only=True)
class _Loop:
    """One `{% for item in sequence %}` block and the nodes it repeats."""

    item: str
    sequence: str
    body: tuple[_Node, ...]


_Node = _Text | _Conditional | _Loop


def _nodes(*, lines: list[str], index: int) -> tuple[tuple[_Node, ...], int]:
    """The template's nodes from `index` until an `end` tag or the end of input."""
    collected: list[_Node] = []
    while index < len(lines):
        line = lines[index]
        if _END_TAG.match(line.strip()) is not None:
            return tuple(collected), index + 1
        conditional = _IF_TAG.match(line.strip())
        if conditional is not None:
            body, index = _nodes(lines=lines, index=index + 1)
            collected.append(_Conditional(name=conditional["name"], body=body))
            continue
        loop = _FOR_TAG.match(line.strip())
        if loop is not None:
            body, index = _nodes(lines=lines, index=index + 1)
            collected.append(_Loop(item=loop["item"], sequence=loop["sequence"], body=body))
            continue
        collected.append(_Text(line=line))
        index += 1
    return tuple(collected), index


def _emit(*, nodes: tuple[_Node, ...], variables: dict[str, _Value]) -> list[str]:
    """One node list rendered against `variables`, as output lines."""
    out: list[str] = []
    for node in nodes:
        if isinstance(node, _Text):
            out.append(
                _SUBSTITUTION.sub(lambda found: str(variables[found.group(0)[3:-3]]), node.line)
            )
            continue
        if isinstance(node, _Conditional):
            if variables[node.name]:
                out.extend(_emit(nodes=node.body, variables=variables))
            continue
        sequence = variables[node.sequence]
        assert isinstance(sequence, tuple), (
            f"{node.sequence} resolves to {sequence!r}, which is not a sequence this "
            f"template may loop over"
        )
        for item in sequence:
            out.extend(_emit(nodes=node.body, variables={**variables, node.item: item}))
    return out


def _rendered_unit(*, host: str) -> str:
    """`templates/otel-collector.service.j2` as one host's converge writes it.

    `trim_blocks` is Ansible's own default for the `template` module, so a line
    holding nothing but a control tag contributes no blank line — which is why
    this renderer is line-based and consumes a tag line whole.
    """
    assert _UNIT_TEMPLATE.is_file(), "the otel_collector role ships no unit template"
    lines = _UNIT_TEMPLATE.read_text(encoding="utf-8").split("\n")
    nodes, _ = _nodes(lines=lines, index=0)
    return "\n".join(_emit(nodes=nodes, variables=_variables(host=host)))


def _directive(*, unit: str, name: str) -> list[str]:
    """Every value the rendered unit gives one directive, in unit order."""
    return [
        line.split("=", 1)[1]
        for line in unit.split("\n")
        if line.startswith(f"{name}=") and "=" in line
    ]


# --- reading the role's tasks -----------------------------------------------


def _task_blocks(*, body: str) -> list[str]:
    """One string per top-level `- name:` task; a nested task stays in its parent."""
    return [f"- name: {chunk}" for chunk in body.split("\n- name: ")[1:]]


def _tasks_text() -> str:
    assert _TASKS.is_file(), "the otel_collector role has no tasks/main.yml"
    return _TASKS.read_text(encoding="utf-8")


def _first_index(*, blocks: list[str], needle: str) -> int:
    """The index of the first task block carrying `needle`; -1 when none does."""
    for index, block in enumerate(blocks):
        if needle in block:
            return index
    return -1


def _first_writer_index(*, blocks: list[str]) -> int:
    """The index of the first task block that writes anything on the target."""
    indexes = [
        index
        for index, block in enumerate(blocks)
        if any(module in block for module in _WRITER_MODULES)
    ]
    assert indexes, "the role writes nothing on the target, which cannot be right"
    return min(indexes)


# --- the controls -----------------------------------------------------------


def test_the_template_stays_inside_the_vocabulary_this_renderer_resolves() -> None:
    """No filter, no test, no expression — a tag is one name, a substitution one name.

    Without this the renderer above is free to drift from Jinja, and a drifted
    renderer reports a unit the host never gets, which is worse than reporting
    nothing.
    """
    text = _UNIT_TEMPLATE.read_text(encoding="utf-8")
    for tag in _ANY_TAG.findall(text):
        assert (
            _IF_TAG.match(tag) is not None
            or _FOR_TAG.match(tag) is not None
            or _END_TAG.match(tag) is not None
        ), (
            f"the unit template carries the control tag {tag!r}, which this renderer cannot "
            f"evaluate faithfully. A tag must be `{{% if <name> %}}`, "
            f"`{{% for <name> in <name> %}}`, `{{% endif %}}` or `{{% endfor %}}`: neither "
            f"Ansible nor Jinja is importable in this suite, so a richer construct would be "
            f"resolved WRONG here and right on the host"
        )
    for substitution in _ANY_SUBSTITUTION.findall(text):
        assert _SUBSTITUTION.match(substitution) is not None, (
            f"the unit template carries the substitution {substitution!r}; it must be "
            f"`{{{{ <name> }}}}` with no filter and no expression, for the same reason"
        )


def test_the_resolvers_own_guards_refuse_rather_than_answer_wrongly() -> None:
    """Each way this file could answer a question it cannot answer, exercised.

    A resolver that answered anyway would be the quiet disagreement the module
    docstring warns about, so each of its three guards is held to REFUSING: a
    `{{ }}` reference cycle raises rather than looping or leaving the reference
    standing; an absent needle reads as -1, which every ordering assertion
    below rejects by requiring `0 <= index`, rather than as "before task 0";
    and a flat list that runs to the end of its file is still the list it is.
    """
    with pytest.raises(AssertionError, match="reference cycle"):
        _ = _resolved(variables={"first": "{{ second }}", "second": "{{ first }}"})
    assert _first_index(blocks=["- name: a", "- name: b"], needle="nothing names this") == -1
    # No trailing blank line, so the loop runs out of input rather than meeting
    # a non-item line -- which is the shape a host_vars file ending in a list
    # would have if its final newline were ever dropped.
    assert _parse_variables(text="otel_collector_env_from_controller:\n  - ONE\n  - TWO") == {
        "otel_collector_env_from_controller": ("ONE", "TWO")
    }


def test_the_resolution_fails_when_ci_pool_yml_omits_the_role() -> None:
    """The negative control: the play reading is load-bearing, not vacuous."""
    play_text = _CI_POOL_PLAY.read_text(encoding="utf-8")
    hosts = _ci_pool_hosts()
    without = re.sub(
        r"^    - role: otel_collector$\n(?:^      .*$\n)*", "", play_text, flags=re.MULTILINE
    )
    assert "otel_collector" not in without, "the control must actually remove the role entry"
    with pytest.raises(AssertionError):
        _assert_play_converges_the_collector(play_text=without, hosts=hosts)
    # And the same reading over the committed play passes, so the control is not
    # merely proving that an arbitrary mutation fails.
    _assert_play_converges_the_collector(play_text=play_text, hosts=hosts)


# --- the Definition of Done -------------------------------------------------


def test_the_ci_pool_play_converges_the_collector_on_every_pool_node() -> None:
    """Assertion 1: one ungated, tagged entry, after `ci_observability`."""
    play_text = _CI_POOL_PLAY.read_text(encoding="utf-8")
    hosts = _ci_pool_hosts()
    _assert_play_converges_the_collector(play_text=play_text, hosts=hosts)
    assert set(_POOL_CONFIG_FILES) <= set(hosts), (
        f"the three nodes this item converges must all be in `ci_pool`: "
        f"{sorted(_POOL_CONFIG_FILES)} against {sorted(hosts)}"
    )
    order = [match["role"] for match in _ROLE_ENTRY.finditer(play_text)]
    assert order.index("otel_collector") > order.index("ci_observability"), (
        f"the collector entry must follow `ci_observability`: that role installs the "
        f"node-local emitters whose spans this collector forwards;\norder={order}"
    )


def test_the_config_file_is_per_host_and_the_dev_host_keeps_config_yaml() -> None:
    """Assertion 2: the merged file is named by `otel_collector_config_file`."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert "otel_collector_config_file: config.yaml" in defaults, (
        f"the role must default `otel_collector_config_file` to `config.yaml`, so the dev "
        f"host's resolution is unchanged and only a pool node overrides it;\n{defaults}"
    )
    dev = _variables(host=_DEV_HOST)
    assert dev["otel_collector_config_file"] == "config.yaml", dev["otel_collector_config_file"]
    assert dev["otel_collector_config_url"] == (
        "https://raw.githubusercontent.com/thewoolleyman/otel-collector/main/config.yaml"
    ), dev["otel_collector_config_url"]
    for host, config_file in sorted(_POOL_CONFIG_FILES.items()):
        resolved = _variables(host=host)
        assert resolved["otel_collector_config_file"] == config_file, (
            f"{host} must read {config_file} — that is the shape its collector runs; "
            f"it resolves {resolved['otel_collector_config_file']!r}"
        )
        assert resolved["otel_collector_config_url"] == (
            f"https://raw.githubusercontent.com/thewoolleyman/otel-collector/main/{config_file}"
        ), resolved["otel_collector_config_url"]
    # One source of truth for the configuration: the URL is BUILT from the file
    # name, never spelled a second time.
    assert str(dev["otel_collector_config_url"]).count("otel-collector/") == 1, dev


def test_each_pool_hosts_host_vars_name_its_shape_and_the_service_user() -> None:
    """Assertion 3: three shapes, each running as the `otel-collector` account."""
    for host, config_file in sorted(_POOL_CONFIG_FILES.items()):
        resolved = _variables(host=host)
        assert resolved["otel_collector_config_file"] == config_file, host
        assert resolved["otel_collector_user"] == _SERVICE_USER, (
            f"{host}'s collector must run as the dedicated `{_SERVICE_USER}` account, never a "
            f"human login: a pool node has no resident checkout to run out of and the "
            f"collector must not inherit a human's cluster credential; it resolves "
            f"{resolved['otel_collector_user']!r}"
        )
        assert resolved["otel_collector_group"] == _SERVICE_USER, host
        assert resolved["otel_collector_manage_install"] is True, (
            f"{host} must set `otel_collector_manage_install: true`: the retired installer "
            f"was its only binary-and-user path and the host guard refuses re-running it"
        )
    # The dev host is the contrast, and the default: unmanaged, login account.
    dev = _variables(host=_DEV_HOST)
    assert dev["otel_collector_manage_install"] is False, dev["otel_collector_manage_install"]
    assert dev["otel_collector_user"] != _SERVICE_USER, dev["otel_collector_user"]


def test_a_pool_host_gets_the_service_user_and_the_pinned_verified_binary() -> None:
    """Assertion 4: the system user, and 0.147.0 verified, installed only when absent."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert f"otel_collector_binary_version: {_BINARY_VERSION}" in defaults, defaults
    assert f"otel_collector_binary_sha256: {_BINARY_SHA256}" in defaults, defaults
    assert f"otel_collector_binary: {_BINARY_DEST}" in defaults, defaults
    pool = _variables(host="poweredge-xubuntu")
    assert str(pool["otel_collector_binary_url"]).startswith(
        f"{_UPSTREAM_RELEASES}v{_BINARY_VERSION}/"
    ), pool["otel_collector_binary_url"]
    assert str(pool["otel_collector_binary_url"]).endswith(".tar.gz"), (
        f"the pinned download must be the upstream RELEASE TARBALL, which is what the "
        f"published checksums file digests; it resolves {pool['otel_collector_binary_url']!r}"
    )

    blocks = _task_blocks(body=_tasks_text())
    user = next(
        (block for block in blocks if "ansible.builtin.user:" in block),
        None,
    )
    assert user is not None, (
        "the role must create the collector's system user on a managed host: the retired "
        "installer was the only thing that did, and it can no longer be run"
    )
    for required in (
        'name: "{{ otel_collector_user }}"',
        "system: true",
        "create_home: false",
        "shell: /usr/sbin/nologin",
        "otel_collector_manage_install",
    ):
        assert required in user, f"the user task must carry {required!r}:\n{user}"

    download = next((block for block in blocks if "ansible.builtin.get_url:" in block), None)
    assert download is not None, "the role must fetch the pinned binary itself"
    assert 'checksum: "sha256:{{ otel_collector_binary_sha256 }}"' in download, (
        f"the fetch must verify the published digest — a download checked against a digest "
        f"computed from itself proves only internal consistency;\n{download}"
    )

    # Already at the pin: nothing runs. The whole install is gated on a version
    # READ, so a converged host is left exactly as it was found.
    tasks = _tasks_text()
    assert "otel_collector_binary_current" in tasks, (
        f"the role must decide whether the pinned version is already in place and gate the "
        f"download on that decision, so an already-installed {_BINARY_VERSION} is "
        f"untouched;\n{tasks}"
    )
    assert "when: not otel_collector_binary_current" in tasks, tasks


def test_a_dev_host_only_asserts_the_binary_and_gets_no_service_user() -> None:
    """Assertion 5: the unmanaged path is the refusal it has always been."""
    dev = _variables(host=_DEV_HOST)
    assert dev["otel_collector_manage_install"] is False, dev
    blocks = _task_blocks(body=_tasks_text())
    refusal = next(
        (
            block
            for block in blocks
            if "ansible.builtin.assert:" in block and "otel_collector_binary_stat" in block
        ),
        None,
    )
    assert refusal is not None, (
        "the role must still REFUSE a host that carries no collector binary and does not "
        "manage one: that refusal is the dev host's whole binary handling"
    )
    assert "when: not (otel_collector_manage_install | bool)" in refusal, (
        f"and it must be the UNMANAGED host's arm, so a pool node is not refused for a "
        f"binary this converge is about to install;\n{refusal}"
    )
    # Nothing that creates an account may run without the managed gate.
    for module in ("ansible.builtin.user:", "ansible.builtin.group:"):
        for block in blocks:
            if module not in block:
                continue
            assert "otel_collector_manage_install" in block, (
                f"an account task must be gated on `otel_collector_manage_install`: the dev "
                f"host's collector runs as the login account and must gain no system "
                f"user;\n{block}"
            )


def test_a_missing_controller_key_is_appended_and_an_existing_one_is_never_rewritten() -> None:
    """Assertion 6: append-only, from the control node's environment, under no_log."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert "otel_collector_env_from_controller: []" in defaults, (
        f"the role must default `otel_collector_env_from_controller` to the empty list, so "
        f"a host that opts out renders nothing;\n{defaults}"
    )
    for host in sorted(_POOL_CONFIG_FILES):
        resolved = _variables(host=host)
        assert resolved["otel_collector_env_from_controller"] == (_CONTROLLER_KEY,), (
            f"{host} must name {_CONTROLLER_KEY} so its ingest entry is rendered from the "
            f"credential wrapper rather than placed by hand; it resolves "
            f"{resolved['otel_collector_env_from_controller']!r}"
        )

    blocks = _task_blocks(body=_tasks_text())
    append = next(
        (
            block
            for block in blocks
            if "ansible.builtin.lineinfile:" in block
            and "otel_collector_env_from_controller" in block
        ),
        None,
    )
    assert append is not None, (
        "the role must APPEND a missing key to the environment file: hp's file already "
        "carries the agent-activity keys, so a create-only render would leave the ingest "
        "key absent for ever"
    )
    assert "no_log: true" in append, f"and it must never display the value:\n{append}"
    assert "insertafter: EOF" in append, append
    assert "regexp:" not in append, (
        f"the append must carry NO `regexp:` — a regexp makes lineinfile REPLACE the "
        f"matching line, which is exactly the rewrite of an existing key this forbids;\n"
        f"{append}"
    )
    assert "lookup('ansible.builtin.env'" in append, (
        f"and the value must come from the CONTROL NODE's environment, never from a value "
        f"committed here;\n{append}"
    )
    # Only the keys the file LACKS are appended, which is what keeps an
    # already-set key untouched.
    assert "rejectattr('rc', 'equalto', 0)" in append, (
        f"the loop must be the keys whose presence read FAILED, so a key the file already "
        f"sets is never passed to the append at all;\n{append}"
    )
    # The file itself is created only when absent, never overwritten.
    create = next(
        (
            block
            for block in blocks
            if "ansible.builtin.copy:" in block
            and "otel_collector_environment_path" in block
            and "force: false" in block
        ),
        None,
    )
    assert create is not None, (
        "the role must create the environment file 0600 root:root when it is absent, with "
        "`force: false` so an existing file is left exactly as it is"
    )
    assert 'mode: "0600"' in create, create
    assert "owner: root" in create and "group: root" in create, create


def test_an_unset_controller_variable_is_refused_by_name_before_any_write() -> None:
    """Assertion 7: the refusal names the variable, and precedes every write."""
    blocks = _task_blocks(body=_tasks_text())
    refusal = next(
        (
            block
            for block in blocks
            if "ansible.builtin.assert:" in block
            and "lookup('ansible.builtin.env'" in block
            and "otel_collector_env_from_controller" in block
        ),
        None,
    )
    assert refusal is not None, (
        "the role must refuse a key `otel_collector_env_from_controller` names that the "
        "control node's environment does not set: rendering an empty value would write a "
        "file the collector cannot start from and report success"
    )
    assert "otel_collector_env_from_controller names {{ item }}" in refusal, (
        f"and the refusal must NAME the variable it could not read, so an operator who "
        f"forgot the credential wrapper reads which key is missing;\n{refusal}"
    )
    assert "no_log" not in refusal, (
        f"the refusal must NOT be no_log: the message is the whole point of it, and it "
        f"carries a key NAME rather than a value;\n{refusal}"
    )
    index = _first_index(blocks=blocks, needle="otel_collector_env_from_controller names")
    writer = _first_writer_index(blocks=blocks)
    assert 0 <= index < writer, (
        f"the refusal must fire BEFORE anything is written (it is at task {index}, the "
        f"first write at task {writer}): a host left half-converged by a refusal is worse "
        f"than one refused untouched"
    )


def test_the_poweredge_unit_carries_its_env_file_kubeconfig_and_ordering() -> None:
    """Assertion 8: the CI-runner shape, and a dev host carrying none of it."""
    poweredge = _rendered_unit(host="poweredge-xubuntu")
    environment_files = _directive(unit=poweredge, name="EnvironmentFile")
    assert _POWEREDGE_HOST_ENV in environment_files, (
        f"poweredge's unit must name {_POWEREDGE_HOST_ENV}: the merged "
        f"config.ci-runner-host.yaml reads HONEYCOMB_API_ENDPOINT from it with no default, "
        f"so a collector without it does not start;\n{poweredge}"
    )
    assert environment_files.index(_POWEREDGE_HOST_ENV) < environment_files.index(
        "/etc/otel-collector/.env"
    ), (
        f"and the non-secret file must be listed FIRST, so a value in the secret file wins, "
        f"as the retired installer's unit had it;\n{poweredge}"
    )
    assert _directive(unit=poweredge, name="Environment") == [
        f"KUBECONFIG={_POWEREDGE_KUBECONFIG}"
    ], (
        f"poweredge's unit must point the collector at the scoped read-only ServiceAccount "
        f"kubeconfig, never the admin one (`## Runner-pool node telemetry` failure "
        f"contract);\n{poweredge}"
    )
    after = _directive(unit=poweredge, name="After")
    assert len(after) == 1, after
    for unit_name in _POWEREDGE_ORDER_AFTER:
        assert unit_name in after[0].split(), (
            f"poweredge's unit must order itself after {unit_name}: the k3s datastore is a "
            f"tmpfs wiped at every boot, so the ServiceAccount behind the kubeconfig is "
            f"re-created and re-rendered before this collector can authenticate;\n"
            f"After={after[0]}"
        )

    dev = _rendered_unit(host=_DEV_HOST)
    assert _directive(unit=dev, name="EnvironmentFile") == [
        "/etc/otel-collector/.env"
    ], f"the dev host's unit must name its one environment file and no other;\n{dev}"
    assert (
        _directive(unit=dev, name="Environment") == []
    ), f"the dev host's collector holds no cluster credential at all;\n{dev}"
    dev_after = _directive(unit=dev, name="After")
    for unit_name in _POWEREDGE_ORDER_AFTER:
        assert unit_name not in " ".join(dev_after), (
            f"and it must order itself after neither {unit_name} nor anything else a pool "
            f"node needs;\nAfter={dev_after}"
        )


def test_every_pool_nodes_unit_is_hardened_and_the_dev_hosts_is_not() -> None:
    """Assertion 9: the sandbox the two sibling shapes carry, on all three nodes."""
    for host in sorted(_POOL_CONFIG_FILES):
        unit = _rendered_unit(host=host)
        for directive in _HARDENING:
            assert directive in unit.split("\n"), (
                f"{host}'s unit must carry {directive}: its collector runs as a dedicated "
                f"system user that never had anything else, so it can be confined;\n{unit}"
            )
    dev = _rendered_unit(host=_DEV_HOST).split("\n")
    for directive in _HARDENING:
        assert directive not in dev, (
            f"the dev host's unit must carry NO {directive}: that collector has always run "
            f"as the login account with hostmetrics scraping the whole machine, so a "
            f"sandbox there is a behaviour change and not this converge's transcription"
        )


def test_a_declared_kubeconfig_that_is_absent_is_refused_by_path_before_any_write() -> None:
    """Assertion 10: the precondition is asserted, named, and asserted first."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert 'otel_collector_kubeconfig_path: ""' in defaults, (
        f"the role must default `otel_collector_kubeconfig_path` to empty, so a host that "
        f"holds no cluster identity declares none;\n{defaults}"
    )
    assert _variables(host="poweredge-xubuntu")["otel_collector_kubeconfig_path"] == (
        _POWEREDGE_KUBECONFIG
    )
    assert _variables(host=_DEV_HOST)["otel_collector_kubeconfig_path"] == ""

    blocks = _task_blocks(body=_tasks_text())
    refusal = next(
        (
            block
            for block in blocks
            if "ansible.builtin.assert:" in block and "otel_collector_kubeconfig_stat" in block
        ),
        None,
    )
    assert refusal is not None, (
        "the role must refuse a host whose declared kubeconfig is absent: writing the unit "
        "anyway installs a collector that starts, authenticates against nothing, and "
        "reports a silent node"
    )
    assert "{{ otel_collector_kubeconfig_path }} is not a regular file" in refusal, (
        f"and the refusal must NAME the path, so an operator reads which precondition the "
        f"identity converge has not met;\n{refusal}"
    )
    index = _first_index(blocks=blocks, needle="otel_collector_kubeconfig_stat")
    writer = _first_writer_index(blocks=blocks)
    assert 0 <= index < writer, (
        f"the kubeconfig read and its refusal must come BEFORE anything is written (read at "
        f"task {index}, first write at task {writer})"
    )
    # And never a fall-back to the admin kubeconfig.
    role_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(_ROLE.rglob("*")) if path.is_file()
    )
    assert "k3s.yaml" not in role_text, (
        f"the role must never name the admin kubeconfig: the collector reading every "
        f"kubelet holds a read-only cluster identity and nothing more;\n{role_text}"
    )


def test_the_role_documents_its_per_host_values_and_the_readme_names_the_pool_commands() -> None:
    """The per-host values are documented beside them, and the apply is committed."""
    assert _ROLE_DOC.is_file(), (
        "host_vars is GENERATED from each role's HOST_VARS.md, so a role with per-host "
        "values and no HOST_VARS.md loses them at the next regeneration"
    )
    doc = _ROLE_DOC.read_text(encoding="utf-8")
    for variable in (
        "otel_collector_config_file",
        "otel_collector_manage_install",
        "otel_collector_extra_environment_files",
        "otel_collector_kubeconfig_path",
        "otel_collector_unit_after",
        "otel_collector_hardened",
        "otel_collector_env_from_controller",
    ):
        assert variable in doc, f"HOST_VARS.md must document {variable}:\n{doc}"

    readme = _ANSIBLE_README.read_text(encoding="utf-8")
    for command in (
        "just ansible-drift ansible/ci-pool.yml --tags otel_collector",
        "just ansible-apply ansible/ci-pool.yml --tags otel_collector",
    ):
        assert command in readme, f"ansible/README.md must name `{command}`:\n{readme}"
    assert "with-livespec-env.sh -- just ansible-apply ansible/ci-pool.yml" in readme, (
        f"and it must name the credential wrapper, because the ingest key the converge "
        f"renders is projected into the control node's environment by it;\n{readme}"
    )
    # The dev host's own commands stay, unchanged by this item.
    assert "just ansible-apply ansible/dev-host.yml --tags otel_collector" in readme, readme
    assert _role_entry(
        play_text=_DEV_HOST_PLAY.read_text(encoding="utf-8"), role="otel_collector"
    ) == (None, "[otel_collector]"), "the dev host's entry must be unchanged"
