"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario

    "converging the Fabro sandbox envelope never restarts dockerd outside a drained window"

together with the "Sandbox resource envelope" paragraph of the
`## Fabro factory host provisioning` section of
`SPECIFICATION/non-functional-requirements.md`, which that scenario exercises.

WHY THE SCENARIO IS ANSWERED FROM THE ROLE AND NOT FROM A HOST. Its three Thens are
claims about what a converge DOES: the limits a unit carries, the keys a merge keeps,
and the restart that must not happen. The first is answered by rendering the committed
slice template; the second by evaluating the committed merge expression against a
`daemon.json` that already holds keys the role does not own; the third by reading every
executable task of the role and proving that the daemon service is named ONLY inside
tasks the operator has to select by tag. None of the three needs — or is improved by —
reaching `hp-xubuntu`, and the third could not be answered from a host at all: "dockerd
was not restarted" is a claim about every converge, not about one.

THE RENDERER IS A SUBSTITUTION RENDERER, AND ONE TEST KEEPS IT HONEST. Ansible and
Jinja are not importable here — `ansible-lint` and `ansible-playbook` are resolved
through `uvx` against their own interpreter (see the justfile), because ansible-core
2.21 requires a Python floor this repository does not carry. So `_render_unit`
substitutes `{{ name }}` from a mapping and nothing else, exactly as the sibling
`test_fabro_instance_axes_scenario` does, and
`test_the_slice_template_stays_inside_the_vocabulary_this_test_can_render` fails the
moment the template grows a filter, a conditional or a loop rather than letting the
renderer quietly disagree with Jinja about what the host gets.

CONTROLLED AGAINST REAL JINJA ONCE, BY MEASUREMENT. On 2026-10-11, before this file was
committed, Jinja2 3.1 rendered the committed slice template with the role's committed
defaults and produced output BYTE-IDENTICAL to what `_render_unit` produces here. The
renderer measured was Jinja2 itself rather than `ansible-playbook`: the fleet host guard
refuses an `ansible-playbook` invocation against an uncommitted playbook, which is the
right refusal — a converge is `just ansible-apply` over committed source — and Jinja is
the component whose agreement with the substitution above was in question. That run needs
a network-resolved second interpreter, which no test may depend on, so it is recorded
here rather than reproduced in the suite.

WHAT IS DERIVED AND WHAT IS STATED. The slice name, the three limits, the daemon
service, the merge's base fact and the drained-restart tag are all READ out of the role,
so a role that renders or gates them differently fails here instead of being
re-described. Only the Definition of Done's own values — the default limits `22G`/`24G`/
`1400%` and the slice name `fabro-sandbox.slice` — are stated, because the Definition of
Done states them and a test that derived them from the file it is checking would assert
nothing.

CONTROL ARMS. Every positive arm is paired. The limits arm proves the three values are
ABSENT from the template body, so a template with the numbers inline cannot pass by
accident. The merge arm proves the fixture config is non-empty and does not already
carry `cgroup-parent`, and that the merge's base is the fact slurped from the host rather
than a literal. The restart arm proves at least one daemon-restarting task EXISTS — a
role with no restart path would otherwise satisfy "never restarts" trivially — and that
the gate predicate REFUSES a synthetic ungated restart. The pending-restart arm evaluates
the role's own condition both ways: pending against a daemon that has not loaded the
slice, not pending against one that has.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "docker_sandbox_slice"
_TEMPLATE = _ROLE / "templates" / "fabro-sandbox.slice.j2"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"
_PLAY = _ANSIBLE / "fabro-hosts.yml"

# The Definition of Done's values, stated because it states them.
_ROLE_NAME = "docker_sandbox_slice"
_SLICE_NAME = "fabro-sandbox.slice"
_DEFAULT_LIMITS = {
    "docker_sandbox_slice_memory_high": "22G",
    "docker_sandbox_slice_memory_max": "24G",
    "docker_sandbox_slice_cpu_quota": "1400%",
}
# The systemd directive each limit variable renders into, which is what the scenario's
# first Then is about ("the memory and CPU limits named by the role variables").
_LIMIT_DIRECTIVES = {
    "docker_sandbox_slice_memory_high": "MemoryHigh",
    "docker_sandbox_slice_memory_max": "MemoryMax",
    "docker_sandbox_slice_cpu_quota": "CPUQuota",
}

# Ansible's own built-in value for `ansible_managed`, which the unit's first line
# renders. The control arm asserts `ansible.cfg` declares no override, so this constant
# cannot silently stop describing what a converge writes.
_ANSIBLE_MANAGED = "Ansible managed"
_ANSIBLE_CFG = _ANSIBLE / "ansible.cfg"

# A `daemon.json` that already holds keys this role does not own — the scenario's Given.
# Shapes rather than one flat string on purpose: a merge that stringified or flattened
# the host's configuration would keep the key names and lose the values.
_FOREIGN_DAEMON_CONFIG: dict[str, object] = {
    "data-root": "/var/lib/docker",
    "log-driver": "json-file",
    "log-opts": {"max-size": "100m", "max-file": "3"},
    "default-address-pools": [{"base": "172.80.0.0/16", "size": 24}],
    "live-restore": True,
}

# The `## ` sections the "Documented beside the values" paragraph requires of an INTERIM
# control: its operator procedure, its rollback and the condition under which it retires.
_REQUIRED_DOC_HEADINGS = (
    "## The drained restart",
    "## Rollback",
    "## Expiry",
)


# --- reading the committed role -------------------------------------------


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


_ROLE_DEFAULT = re.compile(
    r"^(?P<name>docker_sandbox_slice_[a-z_]+): (?P<value>\S+)$", re.MULTILINE
)


def _role_defaults() -> dict[str, str]:
    """Every scalar the role's `defaults/main.yml` declares."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
    }
    assert declared, (
        "the role must declare its variables in defaults/main.yml: the spec section "
        "requires the slice's limits to be read from role variables, and a limit spelled "
        "inline in the template is not one"
    )
    return declared


def _tasks_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order.

    Text-sliced rather than YAML-parsed because no YAML library is importable in this
    suite (`[dependency-groups].dev` carries none, deliberately — the package is
    dependency-free). A task begins at a column-zero `- name:` line and ends at the next
    one, which is the shape every role file in this tree uses.
    """
    if not source.is_file():
        return []
    text = source.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{source.name} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a restart path "
        f"nothing here checks"
    )
    parsed: list[tuple[str, str]] = []
    for start, stop in pairwise([*openings, len(text)]):
        body = text[start:stop]
        parsed.append((body.split("\n", 1)[0][len("- name: ") :].strip(), body))
    return parsed


def _task_named(*, name: str) -> str:
    """One task of the role's `tasks/main.yml`, from its `- name:` to the next task."""
    matching = [body for task_name, body in _tasks_of(source=_TASKS) if task_name == name]
    assert len(matching) == 1, (
        f"the role must still carry exactly one task {name!r}; this test reads the role's "
        f"own merge and its pending-restart condition out of it rather than restating "
        f"them, so a renamed task is a test that has stopped checking anything"
    )
    return matching[0]


def _executable_tasks() -> list[tuple[str, str]]:
    """Every task the role can run — its tasks AND its handlers.

    Handlers are included because a handler that restarts the daemon is a restart path
    exactly as a task is, and the one notifying it would be the converge the scenario
    forbids.
    """
    return [*_tasks_of(source=_TASKS), *_tasks_of(source=_HANDLERS)]


# --- rendering the committed slice template -------------------------------

_HEADER_COMMENT = re.compile(r"\A\{#.*?-#\}\n", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{ (?P<name>[a-z_]+) \}\}")


def _template_body() -> str:
    """The committed slice template with its leading Jinja comment stripped, as Jinja strips it."""
    text = _TEMPLATE.read_text(encoding="utf-8")
    body = _HEADER_COMMENT.sub("", text)
    assert body != text, (
        "the template's explanatory header must remain a `{#- ... -#}` comment, so the "
        "rendered unit carries only directives systemd reads and this test can compare it "
        "with what a host receives"
    )
    return body


def _render_unit(*, variables: Mapping[str, str]) -> str:
    """The committed slice template rendered for the role's own variables."""
    body = _template_body()
    unknown = sorted(set(_PLACEHOLDER.findall(body)) - set(variables))
    assert not unknown, (
        f"the template names {unknown}, which the role's variables do not carry; Ansible "
        f"would refuse the render on the first unset name"
    )
    return _PLACEHOLDER.sub(lambda match: variables[match["name"]], body)


def _line_starting(*, rendered: str, prefix: str) -> str:
    """The one line of a rendered unit beginning with `prefix`."""
    matching = [line for line in rendered.splitlines() if line.startswith(prefix)]
    assert (
        len(matching) == 1
    ), f"the rendered slice must carry exactly one {prefix!r} line; found {len(matching)}"
    return matching[0]


# --- the role's daemon.json merge, read and evaluated ---------------------

_MERGE_TASK = "Write cgroup-parent into the daemon configuration, preserving every other key"
_MERGE_EXPRESSION = re.compile(
    r"content: \"\{\{ (?P<base>[a-z_]+) \| "
    r"combine\(\{'(?P<key>[a-z-]+)': (?P<value>[a-z_]+)\}\) \| to_nice_json \}\}"
)


def _merge() -> tuple[str, str, str]:
    """The role's merge, as `(base fact, the key it owns, the variable holding its value)`."""
    match = _MERGE_EXPRESSION.search(_task_named(name=_MERGE_TASK))
    assert match is not None, (
        f"the role must write daemon.json as `<base> | combine({{'<key>': <value>}}) | "
        f"to_nice_json`, the only form this test can evaluate. Any other form — a literal "
        f"dict, a template file, a line-wise edit — either drops the host's own keys or "
        f"keeps them in a way nothing here can check;\nbody={_task_named(name=_MERGE_TASK)!r}"
    )
    return match["base"], match["key"], match["value"]


def _merged(*, existing: Mapping[str, object]) -> dict[str, object]:
    """`existing` put through the role's own merge, evaluated the way Jinja's `combine` does."""
    _, key, value_variable = _merge()
    variables = {**_role_defaults()}
    assert value_variable in variables, (
        f"the role merges {key!r} from {value_variable!r}, which is not a role variable; "
        f"the spec section requires the slice to be named by one"
    )
    return {**existing, key: variables[value_variable]}


# --- the role's restart gate, read and evaluated --------------------------

# The `never` tag makes Ansible skip a task unless it is specifically requested; the
# `ansible_run_tags` condition is what makes the skip hold even when the operator selects
# the ROLE's own tag, which `roles:`-level tagging adds to every task in the role and
# which `never` alone does not survive.
_NEVER_TAG = "never"
_TAGS_LINE = re.compile(r"^  tags: \[(?P<tags>[^\]]+)\]$", re.MULTILINE)
_RUN_TAGS_CONDITION = re.compile(
    r"^  when: \"'(?P<tag>[a-z_]+)' in ansible_run_tags\"$", re.MULTILINE
)
# A task that names the daemon SERVICE — by its value or by the variable holding it — and
# asks systemd for a state is a task that can stop or replace dockerd. BOTH spellings are
# matched because the role names the service through its variable, as the spec section
# requires of every host-specific value, so a predicate keyed on the literal alone would
# read the role's one restart path as no restart path at all. The read-only `docker info`
# preflight names the CLI and neither spelling, so it is not caught here — which is why
# the predicate keys on the service rather than on the word "docker".
_DAEMON_SERVICE_VARIABLE = "docker_sandbox_slice_daemon_service"
_STATE_REQUEST = re.compile(r"^    state: (?P<state>\w+)$", re.MULTILINE)
_SAFE_STATES = frozenset({"started", "reloaded"})


def _restart_tag() -> str:
    """The drained-restart tag, read from the role's own gated tasks."""
    tags = {
        tag.strip()
        for _, body in _executable_tasks()
        for match in _TAGS_LINE.finditer(body)
        for tag in match["tags"].split(",")
    } - {_NEVER_TAG}
    assert len(tags) == 1, (
        f"the role must gate its drained restart behind exactly ONE operator-selected "
        f"tag; found {sorted(tags)}. Two tags is two levers, and the spec section allows "
        f"the restart only one"
    )
    return tags.pop()


def _restarts_the_daemon(*, body: str, daemon_service: str) -> bool:
    """Whether a task body can stop or replace this host's container daemon."""
    if daemon_service not in body and _DAEMON_SERVICE_VARIABLE not in body:
        return False
    return any(match["state"] not in _SAFE_STATES for match in _STATE_REQUEST.finditer(body))


def _gated_on_the_operators_tag(*, body: str, tag: str) -> bool:
    """Whether a task runs ONLY when the operator selected the drained-restart tag."""
    tagged = any(
        {entry.strip() for entry in match["tags"].split(",")} >= {_NEVER_TAG, tag}
        for match in _TAGS_LINE.finditer(body)
    )
    conditioned = any(match["tag"] == tag for match in _RUN_TAGS_CONDITION.finditer(body))
    return tagged and conditioned


# --- the role's pending-restart record, read and evaluated ----------------

_PENDING_TASK = "Record that a drained daemon restart is pending"
_PENDING_CONDITION = re.compile(r"^  when: (?P<left>[a-z_]+) != (?P<right>[a-z_]+)$", re.MULTILINE)
_LOADED_PARENT_FACT = re.compile(
    r"^    (?P<fact>[a-z_]+): \"\{\{ (?P<base>[a-z_]+)\['(?P<key>[a-z-]+)'\]"
    r" \| default\(''\) \}\}\"$",
    re.MULTILINE,
)
_LOADED_PARENT_TASK = "Hold the cgroup parent that configuration already names"


def _restart_is_pending(*, existing: Mapping[str, object]) -> bool:
    """The role's own pending-restart verdict for a host whose daemon.json is `existing`."""
    condition = _PENDING_CONDITION.search(_task_named(name=_PENDING_TASK))
    assert condition is not None, (
        f"the role must record the pending restart under a `when: <a> != <b>` condition, "
        f"the only form this test can evaluate;\nbody={_task_named(name=_PENDING_TASK)!r}"
    )
    fact = _LOADED_PARENT_FACT.search(_task_named(name=_LOADED_PARENT_TASK))
    assert fact is not None, (
        f"the role must hold the cgroup parent its daemon.json already names as "
        f"`<fact>: \"{{{{ <base>['<key>'] | default('') }}}}\"`, the only form this test "
        f"can evaluate;\nbody={_task_named(name=_LOADED_PARENT_TASK)!r}"
    )
    values = {
        **_role_defaults(),
        fact["fact"]: str(existing.get(fact["key"], "")),
    }
    for side in (condition["left"], condition["right"]):
        assert side in values, (
            f"the pending-restart condition reads {side!r}, which is neither a role "
            f"variable nor the fact holding the host's loaded cgroup parent; a condition "
            f"resting on a name this test cannot resolve is one it cannot evaluate"
        )
    return values[condition["left"]] != values[condition["right"]]


# --- the play and the document --------------------------------------------


def _hp_xubuntu_play() -> str:
    """The `fabro-hosts.yml` play that targets the sandbox host."""
    text = _PLAY.read_text(encoding="utf-8")
    start = text.find("- name: Fabro sandbox host\n")
    assert start >= 0, "ansible/fabro-hosts.yml must still carry the Fabro sandbox host play"
    remainder = text.find("\n- name: ", start + 1)
    return text[start:] if remainder < 0 else text[start:remainder]


def _doc_section(*, heading: str) -> str:
    """One `##` section of the role's HOST_VARS.md."""
    text = _ROLE_DOC.read_text(encoding="utf-8")
    start = text.find(f"{heading}\n")
    assert start >= 0, (
        f"the role's HOST_VARS.md must carry a {heading!r} section: the spec section "
        f"requires an INTERIM control to carry its operator procedure, its rollback and "
        f"the condition under which it is retired"
    )
    remainder = text.find("\n## ", start + len(heading))
    return text[start:] if remainder < 0 else text[start:remainder]


# --- the scenario ----------------------------------------------------------


def test_the_slice_template_stays_inside_the_vocabulary_this_test_can_render() -> None:
    """The control on the substitution renderer: no filter, no conditional, no loop."""
    body = _template_body()
    assert "{%" not in body and "{#" not in body, (
        f"this file renders the slice by substituting `{{{{ name }}}}` and nothing else, "
        f"because neither Ansible nor Jinja is importable in this suite. A template "
        f"carrying a statement or a second comment block would be rendered WRONG here and "
        f"right on the host, which is worse than not rendering it at all; body={body!r}"
    )
    expressions = re.findall(r"\{\{[^}]*\}\}", body)
    unsupported = sorted(
        expression for expression in expressions if not _PLACEHOLDER.fullmatch(expression)
    )
    assert not unsupported, (
        f"every template expression must be a bare variable for the renderer above to be "
        f"faithful; unsupported={unsupported}"
    )
    assert "ansible_managed" not in _ANSIBLE_CFG.read_text(encoding="utf-8"), (
        f"this test renders the banner as {_ANSIBLE_MANAGED!r}, Ansible's built-in value. "
        f"An `ansible_managed` override in ansible.cfg would make every assertion about "
        f"the unit's first line describe something no host receives"
    )


def test_the_slice_carries_the_memory_and_cpu_limits_the_role_variables_name() -> None:
    """The first Then: the slice's limits are the role variables', and only the variables'."""
    defaults = _role_defaults()
    assert {name: defaults.get(name) for name in _DEFAULT_LIMITS} == _DEFAULT_LIMITS, (
        f"the role's defaults must be the envelope the Definition of Done names — a host "
        f"that overrides one does so in host_vars, but the fleet default is the measured "
        f"one for a 30 GB / 16-core factory; defaults={defaults}"
    )
    rendered = _render_unit(variables={**defaults, "ansible_managed": _ANSIBLE_MANAGED})
    for variable, directive in sorted(_LIMIT_DIRECTIVES.items()):
        assert _line_starting(rendered=rendered, prefix=f"{directive}=") == (
            f"{directive}={defaults[variable]}"
        ), (
            f"the slice's {directive} MUST equal {variable}. A slice whose limits do not "
            f"come from the role variables is an envelope no host can resize, and the "
            f"resize is the whole point of an interim control;\nrendered={rendered!r}"
        )
        assert defaults[variable] not in _template_body(), (
            f"the control arm: {defaults[variable]!r} must be ABSENT from the template "
            f"body, so the {directive} line above proves the VARIABLE reached it rather "
            f"than a literal that happens to match today's default"
        )
    assert defaults["docker_sandbox_slice_name"] == _SLICE_NAME, (
        f"the slice the role installs and names in daemon.json is "
        f"{_SLICE_NAME!r}; got {defaults['docker_sandbox_slice_name']!r}"
    )
    assert _TEMPLATE.name == _SLICE_NAME + ".j2", (
        "the template must render the unit the role's cgroup-parent names; a unit "
        "installed under any other name leaves dockerd pointing at a slice that carries "
        "no limits, which systemd creates implicitly and silently"
    )


def test_converging_keeps_every_daemon_json_key_the_host_held_and_adds_cgroup_parent() -> None:
    """The second Then: `cgroup-parent` names the slice, and every foreign key survives."""
    base, key, _ = _merge()
    assert key == "cgroup-parent", (
        f"the role owns exactly one daemon.json key, `cgroup-parent`; it merges {key!r}. "
        f"A role that writes a second key is a role whose blast radius is larger than the "
        f"envelope it was authorized to install"
    )
    assert "cgroup-parent" not in _FOREIGN_DAEMON_CONFIG, (
        "the Given is a daemon.json that does NOT yet name the slice; a fixture that "
        "already carried the key would make the assertion below pass without a merge"
    )
    assert _FOREIGN_DAEMON_CONFIG, "the Given is a NON-EMPTY daemon.json of foreign keys"
    holder = _task_named(name="Hold the daemon configuration this host already carries")
    assert base in holder and "from_json" in holder, (
        f"the merge's base {base!r} must be the fact holding what this host's daemon.json "
        f"ALREADY carries, parsed from the file. A base that is a literal, an empty "
        f"mapping or the role's own idea of the configuration preserves nothing, and "
        f"every assertion below would still pass;\nbody={holder!r}"
    )
    merged = _merged(existing=_FOREIGN_DAEMON_CONFIG)
    assert merged["cgroup-parent"] == _SLICE_NAME, (
        f"daemon.json MUST name the slice as the daemon's default cgroup parent; "
        f"merged={merged}"
    )
    for foreign_key, value in sorted(_FOREIGN_DAEMON_CONFIG.items()):
        assert merged[foreign_key] == value, (
            f"daemon.json MUST keep {foreign_key!r} exactly as the host held it. This "
            f"host's daemon serves the sccache-redis cache and the Fabro sandboxes "
            f"together; a dropped key reconfigures a daemon the role was asked only to "
            f"give a default cgroup parent;\nmerged={merged}"
        )
    assert (
        json.loads(json.dumps(merged)) == merged
    ), f"the merged configuration must be JSON the daemon can parse; merged={merged}"


def test_no_converge_path_restarts_the_daemon_without_the_operators_drained_restart_tag() -> None:
    """The third Then's first half: every restart path is behind the operator's own tag."""
    daemon_service = _role_defaults()["docker_sandbox_slice_daemon_service"]
    tag = _restart_tag()
    restarting = [
        (name, body)
        for name, body in _executable_tasks()
        if _restarts_the_daemon(body=body, daemon_service=daemon_service)
    ]
    assert restarting, (
        f"the role MUST carry a restart path for {daemon_service}: `cgroup-parent` is not "
        f"reloadable, so a role that only writes it leaves the operator with no mechanism "
        f"at all and the envelope never takes effect. 'Never restarts' must be true of a "
        f"role that CAN restart, or the scenario proves nothing"
    )
    for name, body in restarting:
        assert _gated_on_the_operators_tag(body=body, tag=tag), (
            f"task {name!r} can stop or replace {daemon_service} and is not gated on the "
            f"operator's {tag!r} tag. A `never` tag alone is NOT enough: `roles:`-level "
            f"tagging in fabro-hosts.yml puts the role's own tag on every task here, and "
            f"`--tags {_ROLE_NAME}` then selects a `never`-tagged task — which is a "
            f"converge killing every sandbox run on the host;\nbody={body!r}"
        )
    ungated = (
        "- name: Restart the container daemon\n"
        "  ansible.builtin.systemd_service:\n"
        '    name: "{{ docker_sandbox_slice_daemon_service }}"\n'
        "    state: restarted\n"
    )
    assert _restarts_the_daemon(body=ungated, daemon_service=daemon_service)
    assert not _gated_on_the_operators_tag(body=ungated, tag=tag), (
        "the control arm: the gate predicate must REFUSE an ungated restart, or its "
        "verdict above says nothing about the role"
    )


def test_the_pending_restart_is_recorded_for_a_daemon_that_has_not_loaded_the_slice() -> None:
    """The third Then's second half, evaluated both ways against the role's own condition."""
    assert _restart_is_pending(existing=_FOREIGN_DAEMON_CONFIG), (
        "a host whose daemon.json did not name the slice has a daemon running WITHOUT the "
        "envelope, so the converge MUST record the restart as pending: the record is the "
        "only thing standing between a write that takes effect on the next restart and an "
        "operator who never learns one is owed"
    )
    assert not _restart_is_pending(
        existing={**_FOREIGN_DAEMON_CONFIG, "cgroup-parent": _SLICE_NAME}
    ), (
        "the control arm: a host whose daemon.json ALREADY names the slice has no restart "
        "owed, and a role that records one every converge is a role whose pending marker "
        "means nothing"
    )
    pending = _task_named(name=_PENDING_TASK)
    marker = _role_defaults()["docker_sandbox_slice_pending_restart_marker"]
    assert "docker_sandbox_slice_pending_restart_marker" in pending, (
        f"the pending restart must be recorded at {marker}, a durable file on the host: a "
        f"message in a play recap is gone the moment the terminal scrolls, and the next "
        f"drift read is where the operator will look;\nbody={pending!r}"
    )


def test_the_play_includes_the_role_for_the_sandbox_host_under_its_own_tag() -> None:
    """The role reaches hp-xubuntu the way the spec section requires: through the play."""
    play = _hp_xubuntu_play()
    assert "hosts: hp-xubuntu" in play, "this is the play that targets the sandbox host"
    entry = re.search(
        rf"^    - role: {_ROLE_NAME}\n      tags: \[(?P<tags>[^\]]+)\]$", play, re.MULTILINE
    )
    assert entry is not None, (
        f"ansible/fabro-hosts.yml MUST include {_ROLE_NAME} for hp-xubuntu under its own "
        f"tag. A role the play does not include is a control installed by hand, which the "
        f"spec section requires be treated as drift rather than an exception;\nplay={play!r}"
    )
    assert [tag.strip() for tag in entry["tags"].split(",")] == [_ROLE_NAME], (
        f"the role's play tag must be its own name alone, as every sibling entry's is; "
        f"got {entry['tags']!r}"
    )
    assert _restart_tag() != _ROLE_NAME, (
        "the drained-restart tag must differ from the role's play tag, or selecting the "
        "role selects the restart"
    )


def test_the_role_documents_its_variables_the_procedure_the_rollback_and_the_expiry() -> None:
    """ "Documented beside the values", plus the three an interim control also owes."""
    document = _ROLE_DOC.read_text(encoding="utf-8")
    for name, value in sorted(_role_defaults().items()):
        assert f"`{name}`" in document, (
            f"{name} is a variable the role reads and the document does not name. An "
            f"undocumented variable is one an operator discovers by reading the role, "
            f"which is the drift this document exists to prevent"
        )
        assert value in document, (
            f"the document must name what {name} defaults to; the role defaults it to "
            f"{value!r}, which the document does not mention"
        )
    for heading in _REQUIRED_DOC_HEADINGS:
        section = _doc_section(heading=heading)
        assert len(section.split()) > 20, (
            f"{heading!r} must carry the procedure it names, not a stub: this control is "
            f"interim, and the operator reading it is the one holding a drained window "
            f"open;\nsection={section!r}"
        )
    restart_section = _doc_section(heading=_REQUIRED_DOC_HEADINGS[0])
    assert _restart_tag() in restart_section, (
        f"the drained-restart procedure must name the tag that performs it; the role gates "
        f"on {_restart_tag()!r}, which the section does not mention"
    )
    assert "Kubernetes" in _doc_section(heading="## Expiry"), (
        "the expiry condition is the Kubernetes sandbox backend enforcing per-run limits; "
        "an interim control whose document does not say what ends it is a permanent one"
    )
