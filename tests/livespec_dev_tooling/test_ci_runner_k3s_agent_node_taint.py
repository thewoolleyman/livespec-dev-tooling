"""The k3s AGENT's node-taint START CONFIGURATION — rendered from the node's profile.

THE DEFECT THIS FILE EXISTS FOR (work-item livespec-dev-tooling-yapwva, measured
2026-10-12). `provision-k3s.sh` writes every `NODE_TAINTS` record of an agent's
profile into the k3s install command, so the taint ends up baked into
`k3s-agent.service`'s `ExecStart` at JOIN TIME and nowhere else. k3s applies
`--node-taint` at node REGISTRATION, and a control-plane reboot re-creates the
cluster's objects, so an agent RE-REGISTERS and is re-tainted from that stale
unit — even after its profile has been emptied. poweredge-xubuntu rebooted at
03:56Z, gmktec-xubuntu was `Ready` at 04:01Z and still carried
`node-role/ci=pending` at 04:24Z, with `NODE_TAINTS=` committed in its profile
since R5. The `node_taints` role removes the LIVE taint on each apply, which is
a different fact from what the node starts with, and a reboot is not an apply.

THE FIX THIS FILE GRADES. The profile becomes the only source of the taint: the
`k3s_config` role renders the records into a per-node k3s config file the agent
reads on every start, and strips `--node-taint` out of the unit so the stale
carrier is gone. Both halves are "the k3s agent start configuration" the
Definition of Done names, so every assertion here reads BOTH.

WHY A PER-NODE DROP-IN AND NOT `config.agent.yaml`. The committed
`ci-runner/k3s/phase2/k3s-config/config.agent.yaml` is shared by EVERY agent, and
a taint belongs to ONE node. `SPECIFICATION/non-functional-requirements.md`
states the runner-pool rebuild recipe, and it forbids a procedure that embeds a
value belonging to one node — so the per-node fact is RENDERED into
`/etc/rancher/k3s/config.yaml.d/`, which k3s merges over `config.yaml`, rather
than committed into the file every agent receives.

THE RENDERER IS A SUBSTITUTION RENDERER, AND ONE TEST KEEPS IT HONEST. Ansible
and Jinja are not importable here — `ansible-lint` and `ansible-playbook` are
resolved through `uvx` against their own interpreter (see the justfile), because
ansible-core 2.21 requires a Python floor this repository does not carry. So
`_render_drop_in` substitutes `{{ name }}` from a mapping and nothing else,
exactly as `tests/consumer/test_docker_sandbox_slice_scenario.py` does, and
`test_the_node_taint_template_stays_inside_the_vocabulary_this_test_can_render`
fails the moment the template grows a filter, a conditional or a loop rather
than letting the renderer quietly disagree with Jinja about what the host gets.

CONTROLLED AGAINST REAL JINJA, PYYAML AND ANSIBLE'S OWN FILTERS ONCE, BY
MEASUREMENT. On 2026-10-12, before this file was committed, three agreements
were measured against the real components rather than asserted:

  * PyYAML — the parser Ansible itself uses — read the role's plain-scalar
    `k3s_config_agent_unit_node_taint_regexp` to bytes IDENTICAL to what
    `_role_defaults` reads here, and applying it as `ansible.builtin.replace`
    does (`re.subn(re.compile(regexp, re.MULTILINE), "", contents, 0)`) left a
    `k3s-agent.service` in get.k3s.io's shape byte-identical to the same unit
    written without its `--node-taint` pair.
  * Jinja2 3.1 with Ansible's own `to_json` evaluated the role's derivation
    (`<declared>.split() | to_json`) to output byte-identical to
    `_declared_records`' `json.dumps(node_taints.split())`, for an empty
    profile, a one-record profile and a two-record profile.
  * Jinja2 3.1 rendered the committed template with that value and produced
    `node-taint: []` and `node-taint: ["node-role/ci=pending:NoSchedule"]`
    exactly as `_render_drop_in` does; and Ansible's own `regex_findall | first
    | default('')` chain read both committed profiles to the same value
    `_profile_node_taints` reads.

The renderer measured was Jinja and the filters rather than `ansible-playbook`:
the fleet host guard refuses an `ansible-playbook` invocation against an
uncommitted playbook, which is the right refusal — a converge is
`just ansible-apply` over committed source — and Jinja, PyYAML and the filters
are the components whose agreement with the substitutions here was in question.
That run needs a network-resolved second interpreter, which no test may depend
on, so it is recorded here rather than reproduced in the suite.

WHAT IS DERIVED AND WHAT IS STATED. The template path, the drop-in path, the
profile path and the role's own derivation are all READ out of the role, so a
role that renders them differently fails here instead of being re-described.
Only the Definition of Done's own values — the `node-role/ci` key and the
`node-role/ci=pending:NoSchedule` record that is still on the live node — are
stated, because the item states them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "k3s_config"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TEMPLATE = _ROLE / "templates" / "node-taint.yaml.j2"
_LIVE_RECONCILE = _ANSIBLE / "roles" / "node_taints" / "tasks" / "main.yml"
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"

# The Definition of Done's own values, stated because it states them.
_CI_TAINT_KEY = "node-role/ci"
_CI_TAINT_RECORD = "node-role/ci=pending:NoSchedule"

# The one profile read both halves of the converge must share. Stated as the
# FILTER CHAIN rather than the whole expression because the two roles name the
# profile through their own variable; the chain is what has to agree.
_PROFILE_READ = "| regex_findall('^NODE_TAINTS=(.*)$', multiline=True) | first | default('')"

_NODE_TAINTS_LINE = re.compile(r"^NODE_TAINTS=(?P<value>.*)$", re.MULTILINE)


# --- reading the committed role -------------------------------------------


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


_ROLE_DEFAULT = re.compile(r"^(?P<name>k3s_config_[a-z_]+): (?P<value>\S.*)$", re.MULTILINE)


def _role_defaults() -> dict[str, str]:
    """Every scalar the role's `defaults/main.yml` declares."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
    }
    assert declared, (
        "the role must declare its variables in defaults/main.yml: a path spelled inline "
        "in a task is one no host can redirect and no test can read"
    )
    return declared


def _tasks_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order.

    Text-sliced rather than YAML-parsed because no YAML library is importable in
    this suite (`[dependency-groups].dev` carries none, deliberately — the
    package is dependency-free). A task begins at a column-zero `- name:` line
    and ends at the next one, which is the shape every role file in this tree
    uses.
    """
    text = source.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{source.name} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a converge "
        f"nothing here checks"
    )
    return [
        (text[start:stop].split("\n", 1)[0][len("- name: ") :].strip(), text[start:stop])
        for start, stop in pairwise([*openings, len(text)])
    ]


def _task_whose_body_names(*, source: Path, needle: str) -> str:
    """The one task of a role file whose body names `needle`."""
    matching = [body for _, body in _tasks_of(source=source) if needle in body]
    assert len(matching) == 1, (
        f"{source.name} must carry exactly one task naming {needle!r}; found "
        f"{len(matching)}. This test reads the role's own converge out of it rather "
        f"than restating it, so a second one is a second answer"
    )
    return matching[0]


# --- the profile, read the way the role reads it ---------------------------


def _profile_node_taints(*, text: str) -> str:
    """A profile's declared `NODE_TAINTS`, as the role's `regex_findall` reads it."""
    matches = _NODE_TAINTS_LINE.findall(text)
    return matches[0] if matches else ""


def _committed_profiles() -> dict[str, str]:
    """Every committed phase0 profile, by node name."""
    profiles = {
        path.stem: path.read_text(encoding="utf-8") for path in sorted(_PROFILES.glob("*.env"))
    }
    assert profiles, f"the committed node profiles must still live in {_PROFILES}"
    return profiles


# --- rendering the committed drop-in template ------------------------------

_PLACEHOLDER = re.compile(r"\{\{ (?P<name>[a-z0-9_]+) \}\}")


def _template_body() -> str:
    """The committed node-taint template, as Jinja receives it."""
    assert _TEMPLATE.is_file(), (
        f"the role must carry {_TEMPLATE.relative_to(_REPO_ROOT)}: the agent's taints are "
        f"a per-node fact, and a fact rendered from the profile is the only one a reboot "
        f"cannot make stale"
    )
    return _TEMPLATE.read_text(encoding="utf-8")


def _declared_records(*, node_taints: str) -> str:
    """`NODE_TAINTS` as the role renders it — `<value>.split() | to_json`.

    Ansible's `to_json` is `json.dumps` with its own defaults, and Jinja's
    `.split()` on a string with no argument splits on runs of whitespace and
    drops empties exactly as Python's does, so the empty profile yields `[]`.
    """
    return json.dumps(node_taints.split())


def _render_drop_in(*, node_taints: str) -> str:
    """The committed template rendered for a profile declaring `node_taints`."""
    body = _template_body()
    variables: Mapping[str, str] = {_records_variable(): _declared_records(node_taints=node_taints)}
    unknown = sorted(set(_PLACEHOLDER.findall(body)) - set(variables))
    assert not unknown, (
        f"the template names {unknown}, which the role's node-taint facts do not carry; "
        f"Ansible would refuse the render on the first unset name"
    )
    return _PLACEHOLDER.sub(lambda match: variables[match["name"]], body)


def _records_variable() -> str:
    """The fact the template substitutes, read from the template itself."""
    named = sorted(set(_PLACEHOLDER.findall(_template_body())))
    assert len(named) == 1, (
        f"the template must substitute exactly ONE fact — the profile's records; it names "
        f"{named}. A second name is a second thing this renderer would have to guess"
    )
    return named[0]


# --- stripping the unit, with the role's own committed expression -----------
#
# `ansible.builtin.replace` is `re.subn(re.compile(regexp, re.MULTILINE), replace,
# contents, 0)` — that is the module's whole mechanism, so applying the role's
# committed expression here with the same flag is what a converge does to the
# unit, not a re-description of it. The expression is held in `defaults/main.yml`
# as a PLAIN YAML scalar precisely so this test reads the same bytes Ansible
# compiles: a quoted scalar would process escapes on the way in, and a test that
# had to un-escape it would be free to un-escape it differently.
#
# THE SHAPE OF THE SUBJECT IS get.k3s.io's, NOT THIS TEST'S INVENTION. The
# installer renders INSTALL_K3S_EXEC through its own `quote_indent`, which emits
# one TAB-indented single-quoted argument per line with a trailing ` \`. The
# fixture below is that shape, carrying the join arguments gmktec-xubuntu's
# profile produces.
_AGENT_UNIT_ARGS = (
    ("--server", "https://192.168.1.200:6443"),
    ("--token-file", "/etc/rancher/node/token"),
    ("--node-ip", "192.168.1.156"),
    ("--node-taint", _CI_TAINT_RECORD),
    ("--node-label", "k3s-role=arc-runner-host"),
)


def _agent_unit(*, args: tuple[tuple[str, str], ...]) -> str:
    """A `k3s-agent.service` carrying `args`, in the shape get.k3s.io writes."""
    rendered = "".join(f"\t'{flag}' \\\n\t'{value}' \\\n" for flag, value in args)
    return (
        "[Service]\n"
        "Type=notify\n"
        "ExecStartPre=-/sbin/modprobe br_netfilter\n"
        "ExecStart=/usr/local/bin/k3s \\\n"
        "    agent \\\n"
        f"{rendered}"
        "\n"
    )


def _without(*, flag: str) -> tuple[tuple[str, str], ...]:
    """The fixture's arguments with `flag` removed."""
    return tuple(pair for pair in _AGENT_UNIT_ARGS if pair[0] != flag)


def _strip_node_taint(*, unit: str) -> str:
    """`unit` put through the role's committed expression, as the module applies it."""
    expression = _role_defaults()["k3s_config_agent_unit_node_taint_regexp"]
    return re.subn(re.compile(expression, re.MULTILINE), "", unit, count=0)[0]


# A module argument, not the word wherever it appears: the tasks explain
# themselves in comments, and a predicate keyed on the bare substring would
# convict a task for SAYING it must never carry a `state:`.
_MODULE_STATE_KEY = re.compile(r"^ {4}state: \S+$", re.MULTILINE)

_TAINT_LIST_LINE = re.compile(r"^node-taint: (?P<records>\[.*\])$", re.MULTILINE)


def _rendered_taints(*, rendered: str) -> list[str]:
    """The taint records a rendered drop-in declares to k3s."""
    match = _TAINT_LIST_LINE.search(rendered)
    assert match is not None, (
        f"the rendered drop-in must declare `node-taint: [...]` on one line — the form k3s "
        f"merges over /etc/rancher/k3s/config.yaml and the only one this test can read;\n"
        f"rendered={rendered!r}"
    )
    parsed: list[str] = json.loads(match["records"])
    return parsed


# --- the two Definition-of-Done assertions, config-file half ---------------


def test_the_node_taint_template_stays_inside_the_vocabulary_this_test_can_render() -> None:
    """The control on the substitution renderer: no filter, no conditional, no loop."""
    body = _template_body()
    assert "{%" not in body and "{#" not in body, (
        f"this file renders the drop-in by substituting `{{{{ name }}}}` and nothing else, "
        f"because neither Ansible nor Jinja is importable in this suite. A template "
        f"carrying a statement or a comment block would be rendered WRONG here and right "
        f"on the host, which is worse than not rendering it at all; body={body!r}"
    )
    unsupported = sorted(
        expression
        for expression in re.findall(r"\{\{[^}]*\}\}", body)
        if not _PLACEHOLDER.fullmatch(expression)
    )
    assert not unsupported, (
        f"every template expression must be a bare variable for the renderer above to be "
        f"faithful; unsupported={unsupported}"
    )
    assert _CI_TAINT_KEY not in body, (
        f"the control arm: {_CI_TAINT_KEY!r} must be ABSENT from the template body, so "
        f"every assertion below proves the PROFILE reached the rendered file rather than a "
        f"literal baked into the template"
    )


def test_an_empty_profile_renders_an_agent_config_file_carrying_no_ci_taint() -> None:
    """Definition of Done, first assertion: an empty `NODE_TAINTS` carries no taint."""
    rendered = _render_drop_in(node_taints="")
    assert _rendered_taints(rendered=rendered) == [], (
        f"a node whose profile declares an empty NODE_TAINTS must START with no taint at "
        f"all. An empty list is stated rather than omitted on purpose: the file says "
        f"'this node is open', which is the fact a re-registration has to read;\n"
        f"rendered={rendered!r}"
    )
    assert _CI_TAINT_KEY not in rendered, (
        f"the rendered file must not mention {_CI_TAINT_KEY!r} anywhere — not in a comment "
        f"it could later be uncommented out of;\nrendered={rendered!r}"
    )


def test_a_profile_declaring_the_ci_taint_renders_exactly_that_taint() -> None:
    """Definition of Done, second assertion: the declared record, and only it."""
    rendered = _render_drop_in(node_taints=_CI_TAINT_RECORD)
    assert _rendered_taints(rendered=rendered) == [_CI_TAINT_RECORD], (
        f"a node whose profile declares {_CI_TAINT_RECORD!r} must START with exactly that "
        f"taint. This is the half that keeps a CLOSED node closed across a reboot: the "
        f"unit no longer carries the flag, so the config file is the whole answer;\n"
        f"rendered={rendered!r}"
    )


def test_every_committed_profile_renders_the_records_it_declares_and_nothing_else() -> None:
    """The same two assertions against the pool's real data, whatever it says today."""
    for node, text in sorted(_committed_profiles().items()):
        declared = _profile_node_taints(text=text)
        rendered = _render_drop_in(node_taints=declared)
        assert _rendered_taints(rendered=rendered) == declared.split(), (
            f"{node}'s start configuration must declare exactly the records its committed "
            f"profile does. The profile is the ONE source of this fact; a renderer that "
            f"adds, drops or reorders a record is a second source;\nrendered={rendered!r}"
        )


def test_the_start_configuration_reads_the_profile_the_way_the_live_reconcile_does() -> None:
    """The two halves of the taint must never disagree about what the profile said."""
    for source in (_TASKS, _LIVE_RECONCILE):
        assert _PROFILE_READ in source.read_text(encoding="utf-8"), (
            f"{source.relative_to(_REPO_ROOT)} must read NODE_TAINTS as "
            f"`{_PROFILE_READ}`. The `node_taints` role reconciles the LIVE taint and "
            f"`k3s_config` renders the one the node STARTS with; two different reads of "
            f"one profile is exactly the drift that put a retired taint back on gmktec"
        )


def test_the_role_renders_the_drop_in_from_the_profile_only_on_an_agent() -> None:
    """The wiring: a templated per-node file under k3s's own drop-in directory."""
    defaults = _role_defaults()
    drop_in = defaults["k3s_config_node_taint_drop_in"]
    assert drop_in.startswith("/etc/rancher/k3s/config.yaml.d/"), (
        f"the per-node taint must be rendered into k3s's drop-in directory, which k3s "
        f"merges over /etc/rancher/k3s/config.yaml; got {drop_in!r}. It may NOT be "
        f"written into the committed config.agent.yaml, which every agent receives"
    )
    assert defaults["k3s_config_profile"].endswith("{{ inventory_hostname }}.env"), (
        f"the role must read THIS node's committed profile; got "
        f"{defaults['k3s_config_profile']!r}"
    )
    body = _task_whose_body_names(source=_TASKS, needle="k3s_config_node_taint_drop_in")
    assert "ansible.builtin.template" in body, (
        f"the drop-in must be RENDERED by the template module — that is what makes the "
        f"apply converge it, and what makes `just ansible-drift` show it;\nbody={body!r}"
    )
    assert _TEMPLATE.name in body, (
        f"the render must use {_TEMPLATE.name}; a second template is a second answer;\n"
        f"body={body!r}"
    )
    assert "k3s_config_cluster_role == 'agent'" in body, (
        f"only an agent takes a node taint — `provision-k3s.sh`'s server exec reads no "
        f"NODE_TAINTS at all, so a server rendering one would invent a fact;\nbody={body!r}"
    )


# --- the two Definition-of-Done assertions, unit half ----------------------


def test_the_apply_strips_node_taint_out_of_the_agent_units_start_command() -> None:
    """Both assertions' other half: the stale carrier is REMOVED, not merely overridden."""
    stripped = _strip_node_taint(unit=_agent_unit(args=_AGENT_UNIT_ARGS))
    assert "--node-taint" not in stripped and _CI_TAINT_KEY not in stripped, (
        f"the unit must stop naming a taint at all. It is the carrier that goes stale: "
        f"`provision-k3s.sh` writes it once at join and nothing rewrites it when the "
        f"profile changes, so a node re-registering off this ExecStart is re-tainted from "
        f"a fact no longer committed anywhere;\nstripped={stripped!r}"
    )
    assert stripped == _agent_unit(args=_without(flag="--node-taint")), (
        f"the control arm: every OTHER argument must survive BYTE-IDENTICALLY. `--server`, "
        f"`--token-file`, `--node-ip` and `--node-label` are how this node joins and how "
        f"the phase2 node pins resolve; an expression that ate one of them turns a stale "
        f"taint into a node that cannot register;\nstripped={stripped!r}"
    )


def test_stripping_the_unit_is_idempotent_and_leaves_an_untainted_unit_alone() -> None:
    """Every apply re-runs this; the second one must be a no-op, not a second edit."""
    untainted = _agent_unit(args=_without(flag="--node-taint"))
    assert _strip_node_taint(unit=untainted) == untainted, (
        f"a unit that carries no taint must come back byte-identical, or `just "
        f"ansible-drift` reports a change forever and the apply is never done;\n"
        f"unit={untainted!r}"
    )
    once = _strip_node_taint(unit=_agent_unit(args=_AGENT_UNIT_ARGS))
    assert _strip_node_taint(unit=once) == once, "the strip must be idempotent"
    every = _strip_node_taint(
        unit=_agent_unit(
            args=(
                *_AGENT_UNIT_ARGS,
                ("--node-taint", "other-role/thing=yes:NoExecute"),
            )
        )
    )
    assert "--node-taint" not in every, (
        f"a profile may declare SEVERAL records, and `provision-k3s.sh` writes one "
        f"`--node-taint` per record; the expression must remove every pair, not the first;"
        f"\nstripped={every!r}"
    )


def test_a_node_taint_flag_with_no_value_cannot_make_the_strip_eat_the_next_flag() -> None:
    """The control arm that matters most: a malformed unit must not lose an argument."""
    malformed = (
        "ExecStart=/usr/local/bin/k3s \\\n"
        "    agent \\\n"
        "\t'--node-taint' \\\n"
        "\t'--node-label' \\\n"
        "\t'k3s-role=arc-runner-host' \\\n"
    )
    assert _strip_node_taint(unit=malformed) == malformed, (
        f"an expression that consumed the LINE AFTER `--node-taint` unconditionally would "
        f"delete `--node-label` here and leave its value behind as a bare positional "
        f"argument — a node that starts, registers unlabelled, and silently stops matching "
        f"every phase2 nodeSelector. It must refuse to match rather than guess;\n"
        f"stripped={_strip_node_taint(unit=malformed)!r}"
    )


def test_the_role_strips_the_unit_on_the_agent_and_reloads_systemd_when_it_did() -> None:
    """The wiring: a `replace` with an empty replacement, then a daemon-reload."""
    defaults = _role_defaults()
    assert defaults["k3s_config_agent_unit"] == "/etc/systemd/system/k3s-agent.service", (
        f"the unit the k3s installer writes is the one to converge; got "
        f"{defaults['k3s_config_agent_unit']!r}"
    )
    body = _task_whose_body_names(source=_TASKS, needle="k3s_config_agent_unit_node_taint_regexp")
    assert "ansible.builtin.replace" in body, (
        f"the strip must use the `replace` module: it is the one this test can apply "
        f"faithfully, it supports --check so `just ansible-drift` shows the pending edit, "
        f"and it reports `changed` only when it actually edited;\nbody={body!r}"
    )
    assert 'replace: ""' in body, (
        f"the matched argument pair must be REMOVED, not rewritten into something else;\n"
        f"body={body!r}"
    )
    assert (
        "k3s_config_cluster_role == 'agent'" in body
    ), f"only an agent has a k3s-agent.service to converge;\nbody={body!r}"
    reload_body = _task_whose_body_names(source=_TASKS, needle="daemon_reload")
    assert "ansible.builtin.systemd_service" in reload_body, (
        f"systemd must be told to re-read the unit through its own module;\n"
        f"body={reload_body!r}"
    )
    assert not _MODULE_STATE_KEY.search(reload_body), (
        f"and told NOTHING else: a `state:` here would restart k3s-agent, which kills every "
        f"CI job running on this node. The stripped unit takes effect on the next start, "
        f"which is the whole contract of this role;\nbody={reload_body!r}"
    )


def test_the_whole_start_configuration_carries_exactly_what_the_profile_declares() -> None:
    """Both assertions read end to end over both carriers at once."""
    for declared, expected in (("", []), (_CI_TAINT_RECORD, [_CI_TAINT_RECORD])):
        start_configuration = (
            _render_drop_in(node_taints=declared),
            _strip_node_taint(unit=_agent_unit(args=_AGENT_UNIT_ARGS)),
        )
        carried = [
            record
            for rendered in start_configuration[:1]
            for record in _rendered_taints(rendered=rendered)
        ]
        assert carried == expected, (
            f"after an apply, a node whose profile declares {declared!r} must start with "
            f"{expected} and nothing else;\nstart_configuration={start_configuration!r}"
        )
        assert all(_CI_TAINT_KEY not in part for part in start_configuration[1:]), (
            f"and the UNIT must contribute no taint of its own — if it still did, the "
            f"rendered file would merely be a second opinion and the stale one would keep "
            f"winning at registration;\nstart_configuration={start_configuration!r}"
        )
