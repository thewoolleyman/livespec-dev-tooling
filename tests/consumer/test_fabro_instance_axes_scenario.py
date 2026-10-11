"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario

    "a Fabro instance that names its own binary and home renders a unit that runs them"

together with the `## Fabro factory host provisioning` section of
`SPECIFICATION/non-functional-requirements.md`, whose "One instance per mapping"
paragraph that scenario exercises.

WHY THIS TEST RENDERS THE UNIT RATHER THAN READING THE TEMPLATE. The scenario's
Then is about the rendered OUTPUT — a unit whose `ExecStart` runs one binary and
whose `Environment=HOME` is one directory — and a template read cannot answer it:
the pre-axis template produced both lines from `fabro_server_host_home`, so the
interesting question is what the variables RESOLVE to, which lives in the role's
`set_fact` and not in the template at all. So this file renders the committed
template with the facts the committed role resolves from the committed host_vars,
and asserts on the bytes.

THE RENDERER IS A SUBSTITUTION RENDERER, AND ONE TEST KEEPS IT HONEST. Ansible
and Jinja are not importable here — `ansible-lint` and `ansible-playbook` are
resolved through `uvx` against their own interpreter (see the justfile), because
ansible-core 2.21 requires a Python floor this repository does not carry. So
`_render_unit` substitutes `{{ name }}` from a mapping and nothing else. That is
faithful ONLY while the template stays inside that vocabulary, which is why
`test_the_unit_template_stays_inside_the_vocabulary_this_test_can_render` exists:
it fails the moment the template grows a filter, a conditional or a loop, rather
than letting the renderer quietly disagree with Jinja about what the host gets.

THE RENDERER WAS CONTROLLED AGAINST REAL JINJA ONCE, BY MEASUREMENT. On
2026-10-11, before this file was committed, ansible-core 2.21.4 rendered the
committed template through `ansible-playbook` for all three of `hp-xubuntu`'s
instances, resolving `binary_path` and `home_env` with the role's own
expressions. Its `fabro-server` unit came out byte-identical to `_PRE_AXIS_UNIT`
below, and its `fabro-server-candidate` unit carried
`ExecStart=/home/cwoolley/.fabro-candidate/bin/fabro …` and
`Environment=HOME=/home/cwoolley/.fabro-candidate`. That run is not reproduced in
the suite — it needs a network-resolved second interpreter, which no test may
depend on — so it is recorded here as the evidence that the substitution above
agrees with the renderer the host actually uses.

WHY THE PRE-AXIS UNIT IS A FROZEN CAPTURE. "byte-identical to the unit the role
rendered before the axes existed" names an artifact that stops existing the moment
the axes land, so the only way to assert it is to have captured it. `_PRE_AXIS_UNIT`
below is that capture: the template at `c5e39a11` rendered for `hp-xubuntu`'s fleet
instance, taken before `binary_path` and `home_env` were added. A later, deliberate
change to the unit updates this capture in the same commit as the template — that
is the capture doing its job, not the test obstructing it.

WHAT IS DERIVED AND WHAT IS STATED. The axis names, their default expressions, the
set of axes the uniqueness preflight guards and the required-key list are all READ
out of the role, so a role that resolves an axis differently fails here instead of
being re-described. Only values that identify this one instance — the candidate's
unit name, port and state root — are stated, because the Definition of Done states
them and a test that derived them from the file it is checking would assert nothing.

CONTROL ARMS. Every positive arm is paired: the byte-identity arm first proves the
fleet instance really does omit both axes (otherwise it would be asserting about an
instance that uses them); the per-instance arm proves the shared binary and the host
home are GONE from the two lines it checks, not merely that the new values appear
somewhere; and the preflight arm refuses a list that repeats each guarded axis in
turn, so a predicate that accepted everything could not pass.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_server"
_TEMPLATE = _ROLE / "templates" / "fabro-server.service.j2"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"
_INVENTORY = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"
_ANSIBLE_CFG = _ANSIBLE / "ansible.cfg"
_NON_FUNCTIONAL = _REPO_ROOT / "SPECIFICATION" / "non-functional-requirements.md"

# The two axes this slice adds, and the section of the role's HOST_VARS.md that
# the "Documented beside the values" paragraph requires them to appear in.
_AXES = ("binary_path", "home_env")
_AXIS_DOC_HEADING = "## Optional per-instance axes"

# The hp-xubuntu instances this scenario is about: the fleet instance, which omits
# both axes, and the candidate instance the fabro-currency cutover moves production
# onto, which names both. These values are the Definition of Done's, not the file's.
_FLEET_UNIT = "fabro-server"
_CANDIDATE_UNIT = "fabro-server-candidate"
_CANDIDATE_PORT = "32278"
_CANDIDATE_HOME = "/home/cwoolley/.fabro-candidate"

# Ansible's own built-in value for `ansible_managed`, which the unit's first line
# renders. The control test below asserts `ansible.cfg` declares no override, so
# this constant cannot silently stop describing what a converge writes.
_ANSIBLE_MANAGED = "Ansible managed"

# `hp-xubuntu`'s fleet unit as the role rendered it BEFORE `binary_path` and
# `home_env` existed: `templates/fabro-server.service.j2` at c5e39a11, substituted
# with that host's committed host_vars and the role's own defaults. The scenario's
# first Then is byte-identity with this.
_PRE_AXIS_UNIT = """\
# Ansible managed
[Unit]
Description=Fabro dark-factory server and web console (fabro-server)
Documentation=https://github.com/thewoolleyman/fabro
After=network-online.target docker.service tailscaled.service
Wants=network-online.target docker.service tailscaled.service

[Service]
Type=simple
User=cwoolley
Group=cwoolley
Environment=HOME=/home/cwoolley
# Cold SlateDB warmup under host load can exceed the verifier's default 60s
# budget, which makes ExecStartPost fail, which makes Restart=always kill a
# half-booted server -- a self-reinforcing crash loop that does not recover.
# Observed on vps 2026-08-17 (killed run fabro-run-01M06K2HZ6YNG6BWJ03HP696PT,
# exit 137). See bd-ib-l3nptz.2 and bd-ib-l3nptz.15.
Environment=FABRO_WEB_VERIFY_ATTEMPTS=300
# Supplied to ExecStartPost's verifier so ONE shared verifier script serves
# every host. Without this the script falls back to its vps-shaped default and
# each host needs its own forked copy.
Environment=FABRO_CANONICAL_HOST=hp-xubuntu.perch-rudd.ts.net:32276
# The verifier probes THIS instance's loopback port, not the fleet default.
Environment=FABRO_BASE_URL=http://127.0.0.1:32276
EnvironmentFile=/home/cwoolley/.fabro/storage/server.env
# OAuth-only posture: the agent's model auth is CLAUDE_CODE_OAUTH_TOKEN,
# injected into the sandbox per dispatch. An API key in the SERVER env bills
# API cost and can leak into the sandbox.
UnsetEnvironment=ANTHROPIC_API_KEY OPENAI_API_KEY
WorkingDirectory=/home/cwoolley/repos/livespec-orchestrator-beads-fabro
# --storage-dir and --config are passed EXPLICITLY even for the default
# instance, where they equal Fabro's built-ins: an instance that relied on the
# defaults would silently share the fleet server's state.
ExecStart=/home/cwoolley/.fabro/bin/fabro server start --foreground --bind 127.0.0.1:32276 --web --no-upgrade-check --storage-dir /home/cwoolley/.fabro/storage --config /home/cwoolley/.fabro/settings.toml
ExecStartPost=/usr/local/libexec/fabro-server-verify-web
Restart=always
RestartSec=5
TimeoutStopSec=90

[Install]
WantedBy=multi-user.target
"""

# --- reading the committed role and host_vars ------------------------------

_LIST_ENTRY = re.compile(r"^ {2}- (?P<key>[a-z_]+): (?P<value>.+)$")
_MAPPING_ENTRY = re.compile(r"^ {4}(?P<key>[a-z_]+): (?P<value>.+)$")
_HOST_SCALAR = re.compile(r"^(?P<name>fabro_server_host_[a-z]+): (?P<value>\S+)$", re.MULTILINE)
_ROLE_DEFAULT = re.compile(r"^(?P<name>fabro_server_[a-z_]+): (?P<value>\S+)$", re.MULTILINE)
_SET_FACT_ENTRY = re.compile(
    r'^ {4}(?P<fact>fabro_server_[a-z_]+): "(?P<expression>\{\{ .+ \}\})"$', re.MULTILINE
)
_INSTANCE_EXPRESSION = re.compile(
    r"^\{\{ fabro_server_instance\.(?P<key>[a-z_]+)" r"(?: \| default\((?P<fallback>.+)\))? \}\}$"
)
_REQUIRED_KEY = re.compile(r"^ {6}- (?P<key>[a-z_]+)$", re.MULTILINE)
# The instance list's own opening line, and the first line at column zero AFTER
# it — which is where one host's block stops in both the role's HOST_VARS.md and
# the generated inventory file. The search must start past the opening line, or
# that line is its own terminator and the block reads as empty.
_INSTANCES_LINE = "\nfabro_server_instances:\n"
_COLUMN_ZERO = re.compile(r"^\S", re.MULTILINE)
_GUARDED_AXIS = re.compile(r"map\(attribute='(?P<axis>[a-z_]+)'")
_BACKTICKED = re.compile(r"`(?P<name>[a-z_]+)`")


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _task_body(*, name: str) -> str:
    """One task of the role's `tasks/main.yml`, from its `- name:` to the next task."""
    text = _TASKS.read_text(encoding="utf-8")
    opening = f"- name: {name}\n"
    start = text.find(opening)
    assert start >= 0, (
        f"the role must still carry the task {name!r}; this test reads the role's own "
        f"resolution and preflight out of it rather than restating them, so a renamed "
        f"task is a test that has stopped checking anything"
    )
    remainder = text.find("\n- name: ", start + len(opening))
    return text[start:] if remainder < 0 else text[start:remainder]


def _host_block(*, source: Path) -> str:
    """The `fabro_server` values of ONE host, bounded so a second host's cannot leak in.

    `HOST_VARS.md` carries a block per host, `hp-xubuntu` first; the generated
    inventory file carries that host's alone. An unbounded scan would read `vps`'s
    service account into `hp-xubuntu`'s render and still pass every assertion
    below, which is the quietest way for this test to stop testing the host it
    names. So both readers are bounded to the first block, whichever file they
    are given.
    """
    text = source.read_text(encoding="utf-8")
    start = text.find("fabro_server_host_user:")
    assert start >= 0, (
        f"{source.name} must declare the host's fabro_server service account; without it "
        f"there is no host block to read"
    )
    opening = text.find(_INSTANCES_LINE, start)
    assert opening >= 0, (
        f"{source.name}'s host block must declare fabro_server_instances; the role reads "
        f"nothing else from this host"
    )
    terminator = _COLUMN_ZERO.search(text, opening + len(_INSTANCES_LINE))
    assert terminator is not None, (
        f"{source.name}'s instance list must be followed by a line at column zero — the "
        f"fence closing the document's code block, or the next role's section in the "
        f"generated inventory. Without one this reader cannot tell where the host stops, "
        f"and a second host's values would reach this host's render"
    )
    return text[start : terminator.start()]


def _instances(*, source: Path) -> list[dict[str, str]]:
    """Every `fabro_server_instances` mapping exactly as `source` commits it.

    One parser serves both the role's `HOST_VARS.md` (the source the maintainer
    edits) and `inventory/host_vars/hp-xubuntu.yml` (generated from it, kept in
    lockstep by hand), so the two can be held against each other.
    """
    parsed: list[dict[str, str]] = []
    collecting = False
    for line in _host_block(source=source).splitlines():
        if line.rstrip() == "fabro_server_instances:":
            collecting = True
            continue
        if not collecting:
            continue
        if not line.strip():
            continue
        if line.strip().startswith("#"):
            continue
        opening = _LIST_ENTRY.match(line)
        if opening is not None:
            parsed.append({opening["key"]: _unquote(value=opening["value"])})
            continue
        entry = _MAPPING_ENTRY.match(line)
        assert entry is not None, (
            f"{source.name} carries an instance line this test cannot read: {line!r}. The "
            f"instance list is the role's whole input, so a shape the parser misses is a "
            f"mapping nothing here checks"
        )
        assert parsed, f"{source.name} indents an instance key before any instance begins"
        parsed[-1][entry["key"]] = _unquote(value=entry["value"])
    assert parsed, f"{source.name} must declare this host's fabro_server_instances"
    return parsed


def _instance_named(*, unit: str, source: Path) -> dict[str, str]:
    """The one instance of `source` whose `unit_name` is `unit`."""
    matching = [entry for entry in _instances(source=source) if entry.get("unit_name") == unit]
    assert len(matching) == 1, (
        f"{source.name} must declare exactly one instance named {unit!r}; found "
        f"{len(matching)}, so either the instance is missing or the uniqueness the role "
        f"asserts on has already been violated in version control"
    )
    return matching[0]


def _host_variables(*, source: Path) -> dict[str, str]:
    """The host's `fabro_server_host_*` scalars plus the role's own defaults.

    Both halves are read rather than stated: the host scalars from the host_vars
    file, the defaults from `defaults/main.yml`, so a changed default reaches the
    render here the same way it reaches the host.
    """
    variables = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
    }
    variables.update(
        {
            match["name"]: _unquote(value=match["value"])
            for match in _HOST_SCALAR.finditer(_host_block(source=source))
        }
    )
    variables["ansible_managed"] = _ANSIBLE_MANAGED
    return variables


def _resolution_expressions() -> dict[str, str]:
    """Each fact the role's "Resolve this instance's axes" task sets, and its expression."""
    body = _task_body(name="Resolve this instance's axes")
    expressions = {match["fact"]: match["expression"] for match in _SET_FACT_ENTRY.finditer(body)}
    assert expressions, "the role must resolve this instance's axes with set_fact"
    return expressions


def _required_keys() -> frozenset[str]:
    """The instance keys the role refuses an incomplete mapping for."""
    body = _task_body(name="Refuse an instance mapping that does not spell every axis")
    keys = frozenset(match["key"] for match in _REQUIRED_KEY.finditer(body))
    assert keys, "the role must still enumerate the keys every instance mapping must spell"
    return keys


def _guarded_axes() -> tuple[str, ...]:
    """The instance axes the role's uniqueness preflight proves distinct, in its own order."""
    body = _task_body(
        name=(
            "Refuse two instances on this host that would share a unit, a state "
            "directory or a port"
        )
    )
    axes = tuple(dict.fromkeys(_GUARDED_AXIS.findall(body)))
    assert axes, "the uniqueness preflight must still map over the axes it proves distinct"
    return axes


def _evaluate_fallback(*, expression: str, variables: Mapping[str, str]) -> str:
    """One `default(...)` argument of the role's resolution, evaluated."""
    resolved: list[str] = []
    for term in (part.strip() for part in expression.split("~")):
        if term.startswith("'") and term.endswith("'"):
            resolved.append(term[1:-1])
            continue
        assert term in variables, (
            f"the role defaults an axis from {term!r}, which is not a variable this test "
            f"resolves; a default read from the wrong place renders the wrong unit"
        )
        resolved.append(variables[term])
    return "".join(resolved)


def _resolved_facts(*, instance: Mapping[str, str], source: Path) -> dict[str, str]:
    """Every `fabro_server_*` fact the role would hold while installing `instance`."""
    variables = _host_variables(source=source)
    for fact, expression in _resolution_expressions().items():
        match = _INSTANCE_EXPRESSION.match(expression)
        assert match is not None, (
            f"the role resolves {fact} with {expression!r}, a form this test cannot "
            f"evaluate. Teach it the new form rather than leaving the axis unrendered"
        )
        key, fallback = match["key"], match["fallback"]
        if key in instance:
            variables[fact] = instance[key]
            continue
        assert fallback is not None, (
            f"{instance.get('unit_name')} omits {key}, which the role resolves with no "
            f"default — Ansible would raise on the first unset name"
        )
        variables[fact] = _evaluate_fallback(expression=fallback, variables=variables)
    return variables


# --- rendering the committed unit template ---------------------------------

_HEADER_COMMENT = re.compile(r"\A\{#.*?-#\}\n", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{ (?P<name>[a-z_]+) \}\}")


def _template_body() -> str:
    """The committed unit template with its leading Jinja comment stripped, as Jinja strips it."""
    text = _TEMPLATE.read_text(encoding="utf-8")
    body = _HEADER_COMMENT.sub("", text)
    assert body != text, (
        "the template's explanatory header must remain a `{#- ... -#}` comment: it is "
        "what keeps the rendered unit byte-comparable with the units the shell installer "
        "wrote, which is the verification the fabro-hosts README describes"
    )
    return body


def _render_unit(*, variables: Mapping[str, str]) -> str:
    """The committed template rendered for one instance's resolved facts."""
    body = _template_body()
    unknown = sorted(set(_PLACEHOLDER.findall(body)) - set(variables))
    assert not unknown, (
        f"the template names {unknown}, which this instance's resolved facts do not "
        f"carry; Ansible would refuse the render on the first unset name"
    )
    return _PLACEHOLDER.sub(lambda match: variables[match["name"]], body)


def _line_starting(*, rendered: str, prefix: str) -> str:
    """The one line of a rendered unit beginning with `prefix`."""
    matching = [line for line in rendered.splitlines() if line.startswith(prefix)]
    assert (
        len(matching) == 1
    ), f"the rendered unit must carry exactly one {prefix!r} line; found {len(matching)}"
    return matching[0]


def _preflight_accepts(*, instances: list[Mapping[str, str]], axes: tuple[str, ...]) -> bool:
    """The role's uniqueness preflight verdict, computed the way the role computes it."""
    return all(len({entry.get(axis, "") for entry in instances}) == len(instances) for axis in axes)


def _doc_section(*, heading: str) -> str:
    """One `##` section of the role's HOST_VARS.md."""
    text = _ROLE_DOC.read_text(encoding="utf-8")
    start = text.find(f"{heading}\n")
    assert start >= 0, (
        f"the role's HOST_VARS.md must carry a {heading!r} section: the "
        f"non-functional-requirements section requires every per-host variable the role "
        f"reads to be documented beside the values, with its default where it has one"
    )
    remainder = text.find("\n## ", start + len(heading))
    return text[start:] if remainder < 0 else text[start:remainder]


# --- the scenario ----------------------------------------------------------


def test_the_unit_template_stays_inside_the_vocabulary_this_test_can_render() -> None:
    """The control on the substitution renderer: no filter, no conditional, no loop."""
    body = _template_body()
    assert "{%" not in body and "{#" not in body, (
        f"this file renders the unit by substituting `{{{{ name }}}}` and nothing else, "
        f"because neither Ansible nor Jinja is importable in this suite. A template "
        f"carrying a statement or a second comment block would be rendered WRONG here "
        f"and right on the host, which is worse than not rendering it at all; body={body!r}"
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


def test_an_instance_that_omits_both_axes_renders_the_unit_the_role_rendered_before_them() -> None:
    """The first Then: adding an optional axis changes nothing for an instance that omits it."""
    instance = _instance_named(unit=_FLEET_UNIT, source=_INVENTORY)
    present = sorted(axis for axis in _AXES if axis in instance)
    assert not present, (
        f"this arm is the no-axes arm, so hp-xubuntu's {_FLEET_UNIT} instance must omit "
        f"both {list(_AXES)}; it declares {present}, which would make the byte-identity "
        f"below a claim about an instance that uses the axes"
    )
    rendered = _render_unit(variables=_resolved_facts(instance=instance, source=_INVENTORY))
    assert rendered == _PRE_AXIS_UNIT, (
        f"an instance that omits binary_path and home_env MUST render byte-identically to "
        f"the unit the role rendered before the axes existed. A one-line difference here "
        f"is a converge that rewrites the live fleet factory's unit as a side effect of "
        f"declaring a second instance, and the restart it would eventually take is the "
        f"restart that kills whatever runs the factory is carrying;\nrendered={rendered!r}"
    )


def test_an_instance_that_names_its_own_binary_and_home_renders_a_unit_that_runs_them() -> None:
    """The second Then: the named binary is what ExecStart runs, the named home is HOME."""
    instance = _instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY)
    missing = sorted(axis for axis in _AXES if axis not in instance)
    assert (
        not missing
    ), f"the candidate instance is the one that names both axes; it omits {missing}"
    variables = _resolved_facts(instance=instance, source=_INVENTORY)
    rendered = _render_unit(variables=variables)
    exec_start = _line_starting(rendered=rendered, prefix="ExecStart=")
    assert exec_start.startswith(f"ExecStart={instance['binary_path']} server start "), (
        f"the unit MUST run the binary the instance names. A cutover candidate whose unit "
        f"starts the shared binary runs the OLD build under the new instance's name, which "
        f"is a cutover that reports success and changes nothing; exec_start={exec_start!r}"
    )
    assert (
        f"Environment=HOME={instance['home_env']}" in rendered.splitlines()
    ), f"the unit MUST set HOME to the home the instance names; rendered={rendered!r}"
    shared_binary = _evaluate_fallback(
        expression="fabro_server_host_home ~ '/.fabro/bin/fabro'", variables=variables
    )
    assert shared_binary not in exec_start, (
        f"the control arm: the shared binary must be GONE from ExecStart, not merely "
        f"accompanied by the named one; exec_start={exec_start!r}"
    )
    host_home = variables["fabro_server_host_home"]
    assert f"Environment=HOME={host_home}" not in rendered.splitlines(), (
        f"the control arm: HOME must be the named home, not the host home the pre-axis "
        f"template hardcoded; rendered={rendered!r}"
    )


def test_the_uniqueness_preflight_accepts_the_hosts_list_and_refuses_each_repeated_axis() -> None:
    """The third Then, both halves: the committed list passes, every repeat is refused."""
    axes = _guarded_axes()
    named_in_spec = frozenset(
        match["name"]
        for line in _NON_FUNCTIONAL.read_text(encoding="utf-8").splitlines()
        if line.startswith("**One instance per mapping.**")
        for match in _BACKTICKED.finditer(line)
    )
    assert frozenset(axes) <= named_in_spec, (
        f"the preflight must guard the axes the section names; role={sorted(axes)} "
        f"section={sorted(named_in_spec)}"
    )
    instances = _instances(source=_INVENTORY)
    assert _preflight_accepts(instances=instances, axes=axes), (
        f"the role's uniqueness preflight MUST accept hp-xubuntu's committed instance "
        f"list, candidate instance included — a list the preflight refuses is a host the "
        f"play cannot converge at all; instances={instances}"
    )
    fresh = {"unit_name": "fabro-server-clash", "home_dir": "/home/cwoolley/.fabro-clash"}
    fresh["port"] = "32279"
    for axis in axes:
        clash = {**instances[0], **{key: value for key, value in fresh.items() if key != axis}}
        assert not _preflight_accepts(instances=[*instances, clash], axes=axes), (
            f"the preflight MUST refuse a list in which two instances share {axis!r}. Two "
            f"units sharing a home_dir share a SlateDB store, which is not a cosmetic "
            f"clash; clash={clash}"
        )


def test_hp_xubuntu_declares_the_candidate_instance_in_the_document_and_the_inventory() -> None:
    """The candidate instance, declared where the role reads it and where the operator edits it."""
    declared = {
        source: _instance_named(unit=_CANDIDATE_UNIT, source=source)
        for source in (
            _ROLE_DOC,
            _INVENTORY,
        )
    }
    assert declared[_ROLE_DOC] == declared[_INVENTORY], (
        f"the role's HOST_VARS.md is the source and the inventory host_vars file is "
        f"generated from it, with no regeneration recipe — they are kept in lockstep by "
        f"hand, so a difference is a declaration the play will never apply; "
        f"doc={declared[_ROLE_DOC]} inventory={declared[_INVENTORY]}"
    )
    for source, instance in declared.items():
        variables = _host_variables(source=source)
        shared_binary = _evaluate_fallback(
            expression="fabro_server_host_home ~ '/.fabro/bin/fabro'", variables=variables
        )
        assert instance["port"] == _CANDIDATE_PORT, f"{source.name}: candidate port"
        assert instance["home_dir"] == _CANDIDATE_HOME, f"{source.name}: candidate state root"
        assert instance["home_env"] == _CANDIDATE_HOME, f"{source.name}: candidate HOME"
        assert instance["binary_path"] != shared_binary, (
            f"{source.name}: the candidate carries its OWN build — an instance declared "
            f"against the shared binary is the hand-installed drift this play exists to "
            f"end, re-expressed rather than fixed"
        )
        assert instance["service_state"] == "running", (
            f"{source.name}: the candidate is declared running, not parked: the cutover "
            f"moves production onto this build"
        )
        assert _required_keys() <= frozenset(instance), (
            f"{source.name}: the candidate must spell every key the role requires; "
            f"missing={sorted(_required_keys() - frozenset(instance))}"
        )


def test_the_role_documents_every_optional_axis_with_the_default_it_carries() -> None:
    """ "Documented beside the values": each optional axis, and where its default comes from."""
    expressions = _resolution_expressions()
    required = _required_keys()
    optional: dict[str, str] = {}
    for expression in expressions.values():
        match = _INSTANCE_EXPRESSION.match(expression)
        if match is None or match["fallback"] is None or match["key"] in required:
            continue
        optional[match["key"]] = match["fallback"]
    assert frozenset(_AXES) <= frozenset(optional), (
        f"both axes this slice adds MUST be OPTIONAL — an instance that omits one renders "
        f"as it did before the axis existed, which a required key cannot express; "
        f"optional={sorted(optional)}"
    )
    section = _doc_section(heading=_AXIS_DOC_HEADING)
    for axis, fallback in sorted(optional.items()):
        assert f"`{axis}`" in section, (
            f"{axis} is an optional per-instance axis the role reads and the document does "
            f"not name. An undocumented axis is one an operator discovers by reading the "
            f"role, which is the drift this document exists to prevent"
        )
        for term in (part.strip() for part in fallback.split("~")):
            token = term[1:-1] if term.startswith("'") and term.endswith("'") else term
            assert token in section, (
                f"the document must name what {axis} defaults to; the role defaults it "
                f"from {token!r}, which the section does not mention"
            )
