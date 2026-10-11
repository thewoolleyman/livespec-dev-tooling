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

THE SECOND CONCERN: WHETHER THE ROLE TOUCHES THE HOST'S BINARY AT ALL. The axes
above decide which binary a unit STARTS. `binary_source` and `binary_sha256` decide
whether the role PUTS one there, by copying a control-node file that hashes to the
declared digest. That question is not answerable from a rendered unit — it lives
entirely in the `when:` guards and the `that:` conditions of the role's own tasks —
so the arms below read those expressions out of `tasks/main.yml` and EVALUATE them
against synthetic host states: a host whose binary already is the declared build, a
host whose binary is some other build, a host with no binary at that path at all,
and a control node whose staged file does not hash to what version control says.

THE EVALUATOR WAS CONTROLLED AGAINST REAL JINJA TOO, BY MEASUREMENT. On 2026-10-11,
before this slice was committed, ansible-core 2.21.4 evaluated the committed role's
own guard expressions — every `when:`, every `that:`, the `>-` folded replacement
decision and the digest-bearing `dest` of the keep — through `ansible-playbook`, for
five modelled host states: hp's fleet instance against a differing host binary, and
the candidate instance against a differing one, an identical one, no binary at all,
and a control-node source with the wrong digest. 44 verdicts, ZERO disagreements with
the evaluator below, and `{{ ... stat.checksum[:12] }}.bak` rendered the same name
character for character. That run is not reproduced in the suite — it needs a
network-resolved second interpreter, which no test may depend on — so it is recorded
here as the evidence that this evaluator agrees with the Jinja the host actually uses.

THAT EVALUATOR IS A RESTRICTED JINJA, AND ONE ARM KEEPS IT HONEST. It understands
names, string and integer literals, parentheses, `not`/`and`/`or`, the six
comparisons, a `[:n]` slice and exactly three filters (`length`, `bool`, `default`).
`test_the_binary_install_guards_stay_inside_the_vocabulary_this_test_can_evaluate`
evaluates every guard the arms below read and fails the moment one grows a form the
evaluator does not know, rather than letting a guard go silently unevaluated — an
unevaluated guard is a test that has stopped checking whether a converge would
rewrite a live factory's binary. Two things are deliberately NOT restated: the
replacement decision itself (read from the role's own `set_fact` expression and
evaluated, never re-expressed here) and the conditions of every guard.

WHAT THE EVALUATOR CANNOT PROVE, AND IS NOT CLAIMED TO. It evaluates guards; it does
not run Ansible, so it cannot prove that `ansible.builtin.copy` copies or that
`mv` renames. Those arms assert the SHAPE instead — that the staged copy's `dest` is
a sibling of `binary_path`, that the rename's `argv` moves exactly that sibling onto
`binary_path`, that the kept copy's name carries a prefix of the outgoing build's
sha256, and that the task order puts every refusal before every write.

THE THIRD CONCERN: WHETHER A RESTART THIS RUN REFUSED SURVIVES TO THE RUN THAT MAY
PERFORM IT. The two concerns above both end at the same place — files on the host have
changed and the running server has not been restarted — and `fabro_server_restart_allowed`
false is the normal way to get there. Measured on `hp-xubuntu` 2026-10-11: the apply
that installed the v0.382 carrier at the candidate's `binary_path` reported that the
instance was NOT restarted, and the follow-up run with the flag true then found nothing
changed, notified nothing, and left the candidate serving `0.378.0-nightly.0` with 72
hours of uptime. The notification does not survive the run that raised it, so the
re-run `HOST_VARS.md` tells the operator to perform could not apply it.

So the role records a deferred restart per instance on the host, and a later permitting
run applies it. The arms for that concern read the role's own marker expression, its
own pending decision and the `when:` of every task and handler involved, and EVALUATE
them against modelled host states: a marker present and a marker absent, a running
server executing its declared `binary_path` and one executing something else, a probe
that could not read the running process at all, and each of those under a permitting
and a refusing run. The marker path is rendered from the role's `set_fact` rather than
restated, so a role that names it differently fails here.

CONTROL ARMS FOR THAT CONCERN, PAIRED LIKE THE OTHERS. Every "restarts" arm is paired
with the state in which the role must restart NOTHING — an instance already executing
its own `binary_path` with no marker — because a pending decision that is always true
is a converge that kills a live factory on every permitting run. The unreadable-probe
state is asserted NOT pending for the same reason: a restart must never rest on a probe
that failed. And the marker is proven PER INSTANCE by rendering it for two of
`hp-xubuntu`'s instances and asserting the two paths differ, since one shared marker
would make the fleet instance's deferral apply to the candidate's restart.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_server"
_TEMPLATE = _ROLE / "templates" / "fabro-server.service.j2"
_TASKS = _ROLE / "tasks" / "main.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"
_INVENTORY = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"
_ANSIBLE_CFG = _ANSIBLE / "ansible.cfg"
_NON_FUNCTIONAL = _REPO_ROOT / "SPECIFICATION" / "non-functional-requirements.md"

# The two unit-rendering axes, and the section of the role's HOST_VARS.md that the
# "Documented beside the values" paragraph requires every optional axis to appear in.
_AXES = ("binary_path", "home_env")
_AXIS_DOC_HEADING = "## Optional per-instance axes"

# The two axes that decide whether the role INSTALLS a binary rather than which one a
# unit starts, and the tasks that carry that decision. The task names are read rather
# than restated wherever the role already states something; these are the handles.
_BINARY_AXES = ("binary_source", "binary_sha256")
_PAIR_REFUSAL = "Refuse an instance that does not spell both halves of the binary-install pair"
_SOURCE_READ = "Read the control node's copy of the binary this instance installs"
_DIGEST_REFUSAL = (
    "Refuse a control-node binary that is absent or does not hash to its declared digest"
)
_MISSING_REFUSAL = "Refuse a host with no built Fabro binary"
_REPLACE_DECISION = "Decide whether this instance's binary must be replaced"
_STAGE_TASK = "Stage this instance's binary beside the one it replaces"
_BACKUP_TASK = "Keep the outgoing binary beside the one that replaces it"
_RENAME_TASK = "Rename the staged copy onto this instance's binary path"
_QUIET_PROBE = "Ask this instance whether any Fabro run is active"
_QUIET_REFUSAL = "Refuse to restart or stop a factory that is carrying runs"
_LIBEXEC_TASK = "Create the shared libexec directory"
_UNIT_INSTALL = "Install the instance's systemd unit"
_RESTART_HANDLER = "Restart the Fabro instance"
_FILES_CHANGED = "Fabro instance files changed"
_REPLACE_FACT = "fabro_server_binary_replace"

# The deferred restart: the two facts the role holds, the tasks that set and read them,
# and the two handlers that write and clear the marker. Names rather than behaviour —
# the behaviour is read out of each task below and never restated here.
_MARKER_FACT = "fabro_server_restart_pending_marker"
_PENDING_FACT = "fabro_server_restart_pending"
_MARKER_NAMING_TASK = "Name this instance's restart-pending marker"
_PENDING_DECISION = "Decide whether this instance owes a restart from before this run"
_DEFER_HANDLER = "Record that this instance's restart is still pending"
_NOT_RESTARTED_HANDLER = "Say which instance was left needing a restart"
_CARRIER_TASK = "Carry this instance's deferred restart into this run"
_RUNNING_PID_TASK = "Read the main PID of whatever this instance is running now"
_RUNNING_BINARY_TASK = "Read the file this instance's running server actually executes"
_CLEAR_HANDLER = "Clear the restart-pending marker this restart satisfied"

# The v0.382 carrier build the fabro-currency cutover moves hp's production factory
# onto: where it is staged on the control node, and the digest it hashes to. Both are
# the Definition of Done's values, stated here rather than read out of the files the
# arms below check — a test that derived them from its own subject would assert nothing.
_CANDIDATE_BINARY_SOURCE = (
    "/home/ubuntu/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro"
)
_CANDIDATE_BINARY_SHA256 = "effe9d03c859e8072934947ce598980ea337065df17e737867685a1508514799"

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

# An axis name may carry DIGITS (`binary_sha256`), so every key pattern admits them.
# A `[a-z_]+`-only class reads a digit-bearing key as a line it cannot parse, which is
# the quietest way for these readers to stop reading the mapping they are given.
_LIST_ENTRY = re.compile(r"^ {2}- (?P<key>[a-z_0-9]+): (?P<value>.+)$")
_MAPPING_ENTRY = re.compile(r"^ {4}(?P<key>[a-z_0-9]+): (?P<value>.+)$")
_HOST_SCALAR = re.compile(r"^(?P<name>fabro_server_host_[a-z]+): (?P<value>\S+)$", re.MULTILINE)
_ROLE_DEFAULT = re.compile(r"^(?P<name>fabro_server_[a-z_]+): (?P<value>\S+)$", re.MULTILINE)
_SET_FACT_ENTRY = re.compile(
    r'^ {4}(?P<fact>fabro_server_[a-z_0-9]+): "(?P<expression>\{\{ .+ \}\})"$', re.MULTILINE
)
_INSTANCE_EXPRESSION = re.compile(
    r"^\{\{ fabro_server_instance\.(?P<key>[a-z_0-9]+)"
    r"(?: \| default\((?P<fallback>.+)\))? \}\}$"
)
_REQUIRED_KEY = re.compile(r"^ {6}- (?P<key>[a-z_]+)$", re.MULTILINE)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TASK_NAME = re.compile(r"^- name: (?P<name>.+)$", re.MULTILINE)
# One mapping-key pattern for both nesting levels the role uses: a task's own keys sit
# at two spaces (`when`, `become`, `notify`, `listen`, the module name) and that
# module's arguments sit at four, so `_key_block` takes the depth as an argument rather
# than there being a regex per depth. `inline` is non-optional so a block form reads as
# an empty inline value rather than as a missing group.
_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[a-z_.0-9]+):(?P<inline>.*)$")
_TASK_INDENT = 2
_ARGUMENT_INDENT = 4
_BLOCK_SCALAR = frozenset({">", ">-", "|", "|-"})
# The instance list's own opening line, and the first line at column zero AFTER
# it — which is where one host's block stops in both the role's HOST_VARS.md and
# the generated inventory file. The search must start past the opening line, or
# that line is its own terminator and the block reads as empty.
_INSTANCES_LINE = "\nfabro_server_instances:\n"
_COLUMN_ZERO = re.compile(r"^\S", re.MULTILINE)
_GUARDED_AXIS = re.compile(r"map\(attribute='(?P<axis>[a-z_]+)'")
_BACKTICKED = re.compile(r"`(?P<name>[a-z_0-9]+)`")
# One row of the optional-axis table of the role's HOST_VARS.md: the axis, the default
# it carries, and what naming it does. Read as a table rather than scanned as prose
# because "documents its default" is a claim about a cell, and a prose scan would be
# satisfied by the axis name appearing anywhere in the section.
_DOC_TABLE_ROW = re.compile(
    r"^\| `(?P<axis>[a-z_0-9]+)` \| (?P<default>[^|]+) \| (?P<meaning>.+) \|$", re.MULTILINE
)


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _task_body(*, name: str, source: Path = _TASKS) -> str:
    """One task of a role file, from its `- name:` to the next task.

    `source` defaults to `tasks/main.yml` because that is where almost every read
    below goes; the restart handler is read out of `handlers/main.yml` with the same
    parser, because a handler is a task and its `when:` is the gate that decides
    whether a replaced binary becomes a restarted factory.
    """
    text = source.read_text(encoding="utf-8")
    opening = f"- name: {name}\n"
    start = text.find(opening)
    assert start >= 0, (
        f"{source.name} must still carry the task {name!r}; this test reads the role's own "
        f"resolution, preflight and install guards out of it rather than restating them, so "
        f"a renamed task is a test that has stopped checking anything"
    )
    remainder = text.find("\n- name: ", start + len(opening))
    return text[start:] if remainder < 0 else text[start:remainder]


def _task_index(*, name: str) -> int:
    """Where one task sits in `tasks/main.yml`, counted in tasks.

    Order is load-bearing and not cosmetic here: "refuses before changing the host"
    and "keeps the outgoing binary BEFORE replacing it" are both statements about
    where a task sits relative to another, and nothing else in the role expresses them.
    """
    names = _TASK_NAME.findall(_TASKS.read_text(encoding="utf-8"))
    assert name in names, (
        f"tasks/main.yml must still carry the task {name!r}; the ordering arms below have no "
        f"other handle on it"
    )
    return names.index(name)


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


# --- reading one task's guards and its module arguments --------------------


def _key_block(*, lines: Iterable[str], indent: int, key: str) -> list[str]:
    """One mapping key's value lines: its inline remainder first, then its nested block.

    ONE reader serves both nesting levels the role uses — a task's own keys at two
    spaces (`when`, `notify`, `listen`, the module name) and that module's arguments at
    four — so the two depths cannot drift apart, and nesting a call inside a call is how
    a module argument is reached. The nested lines keep their indentation for exactly
    that reason; a leaf reader strips them.

    A block-scalar marker (`>-` and friends) is dropped rather than returned as a value:
    the role's replacement decision is a folded `>-` scalar, and YAML joins its lines
    with a single space, which is what `_module_argument` reproduces.
    """
    collected: list[str] | None = None
    for line in lines:
        match = _KEY_LINE.match(line)
        if match is not None and len(match["indent"]) == indent:
            if match["key"] != key:
                if collected is not None:
                    break
                continue
            collected = []
            inline = match["inline"].strip()
            if inline and inline not in _BLOCK_SCALAR:
                collected.append(inline)
            continue
        if collected is None:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        collected.append(line)
    assert collected, (
        f"the role must still carry a non-empty {key!r} at indent {indent}; this arm's whole "
        f"subject is that key, so an absent one is a guard that has stopped existing rather "
        f"than a passing test"
    )
    return collected


def _task_list_field(*, body: str, field: str) -> list[str]:
    """One task-level field read as a list, whether the role spells it inline or as a block.

    `when:` is the field this exists for, and Ansible accepts both spellings with the
    same meaning — a list is ANDed, and a lone condition may be written inline. A
    reader that understood only one spelling would read a real guard as absent.
    """
    return [
        _unquote(value=line.strip().removeprefix("- "))
        for line in _key_block(lines=body.splitlines(), indent=_TASK_INDENT, key=field)
    ]


def _module_block(*, body: str, module: str, argument: str) -> list[str]:
    """One argument of one task's module call, as its raw value lines."""
    return _key_block(
        lines=_key_block(lines=body.splitlines(), indent=_TASK_INDENT, key=module),
        indent=_ARGUMENT_INDENT,
        key=argument,
    )


def _module_argument(*, body: str, module: str, argument: str) -> str:
    """One scalar module argument — a path, an owner, a mode, a folded expression."""
    block = _module_block(body=body, module=module, argument=argument)
    return _unquote(value=" ".join(line.strip() for line in block))


def _module_argument_list(*, body: str, module: str, argument: str) -> list[str]:
    """One sequence-valued module argument — an `assert`'s `that:`, a `command`'s `argv:`."""
    return [
        _unquote(value=line.strip().removeprefix("- "))
        for line in _module_block(body=body, module=module, argument=argument)
    ]


_FLOW_SEQUENCE = re.compile(r"\A\[(?P<items>[^\]]*)\]\Z")


def _argv_items(*, body: str) -> list[str]:
    """One `command` task's `argv`, whether the role spells it as a block or inline.

    The role uses BOTH forms, and they mean the same thing to Ansible: a `- ` item per
    line where the argv carries a long templated path, and the single-line
    `[systemctl, show, …]` flow sequence for its short systemd reads. A reader that
    understood only the block form would take a whole flow argv as ONE opaque string and
    then assert about a value no host receives.

    The flow form is split on `, ` rather than parsed as YAML, which is sound only
    because no argv in this role carries a comma INSIDE an item. The assert below is the
    control on that: a spelling this split mangled reads as one item or an empty one and
    fails HERE, rather than quietly satisfying an assertion about the wrong string.
    """
    items = _module_argument_list(body=body, module="ansible.builtin.command", argument="argv")
    flow = _FLOW_SEQUENCE.fullmatch(items[0]) if len(items) == 1 else None
    parsed = items if flow is None else [_unquote(value=item) for item in flow["items"].split(", ")]
    assert len(parsed) > 1 and all(parsed), (
        f"a command's argv must read as two or more non-empty words; this one read as "
        f"{parsed}, which means the reader above mangled a spelling the role really uses"
    )
    return parsed


# --- evaluating the role's own guards --------------------------------------
#
# A restricted Jinja. Read the module docstring's "THAT EVALUATOR IS A RESTRICTED
# JINJA" paragraph for why the restriction is the point and for the control arm that
# keeps it from silently widening.

_Value = str | bool | int | None

_EXPRESSION_TOKEN = re.compile(
    r"\s*(?P<token>\(|\)|\[|\]|:|\||==|!=|>|and\b|or\b|not\b|'[^']*'|"
    r"[A-Za-z_][A-Za-z_0-9.]*|[0-9]+)"
)
_EXPRESSION_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9.]*")
_EVALUABLE_FILTERS = ("bool", "default", "length")
# `<`, `>=` and `<=` are deliberately ABSENT rather than written and never exercised.
# The tokenizer does not emit them either, so a guard that grew one fails the
# vocabulary control as an unknown token instead of being evaluated by a branch no
# test runs — which is the whole hazard the control exists to catch.
_COMPARISONS = ("==", "!=", ">")
_TEMPLATED = re.compile(r"\{\{ (?P<expression>.+?) \}\}")
_WHOLE_TEMPLATE = re.compile(r"\A\{\{ (?P<expression>.+) \}\}\Z", re.DOTALL)


def _expression_tokens(*, expression: str) -> list[str]:
    """One guard expression, tokenized, with anything outside the vocabulary refused."""
    text = expression.strip()
    found: list[str] = []
    position = 0
    while position < len(text):
        match = _EXPRESSION_TOKEN.match(text, position)
        assert match is not None, (
            f"the role's guard {text!r} carries something this evaluator does not know, at "
            f"offset {position}. Teach it the new form rather than leaving the guard "
            f"unevaluated: an unevaluated guard is a test that has stopped checking whether "
            f"a converge would rewrite a live factory's binary"
        )
        found.append(match["token"])
        position = match.end()
    assert found, f"an empty expression is not a guard; expression={expression!r}"
    return found


def _apply_filter(*, name: str, value: _Value, argument: _Value) -> _Value:
    """One Jinja filter of the three this evaluator knows."""
    assert name in _EVALUABLE_FILTERS, (
        f"the role's guard uses the Jinja filter {name!r}; this evaluator knows only "
        f"{list(_EVALUABLE_FILTERS)}"
    )
    if name == "length":
        assert isinstance(
            value, str
        ), f"`| length` is evaluated for strings only here; value={value!r}"
        return len(value)
    if name == "bool":
        # Ansible's own coercion, which is why the role spells `| bool` on the
        # replacement decision at all: a `set_fact` template can reach a `when:` as the
        # STRING "False", which is truthy to Python and false to `| bool`.
        return value in (True, "True", "true", "yes", 1)
    return argument if value is None else value


def _compare(*, operator: str, left: _Value, right: _Value) -> bool:
    """One comparison of a guard — the three `_COMPARISONS` admits."""
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    assert operator == ">", f"the tokenizer must not emit {operator!r}, which this knows nothing of"
    assert isinstance(left, int) and isinstance(right, int), (
        f"an ordering comparison is evaluated for numbers only here; "
        f"left={left!r} right={right!r}"
    )
    return left > right


def _parse_primary(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """A parenthesized expression, a literal, or one name looked up in the scope."""
    assert position < len(tokens), f"the guard ends where a value was expected; tokens={tokens}"
    token = tokens[position]
    if token == "(":
        value, position = _parse_or(tokens=tokens, position=position + 1, scope=scope)
        assert (
            position < len(tokens) and tokens[position] == ")"
        ), f"an unclosed parenthesis in the role's guard; tokens={tokens}"
        return value, position + 1
    if token.startswith("'"):
        return token[1:-1], position + 1
    if token.isdigit():
        return int(token), position + 1
    assert (
        _EXPRESSION_NAME.fullmatch(token) is not None
    ), f"the role's guard carries {token!r} where a value was expected; tokens={tokens}"
    assert token in scope, (
        f"the role's guard reads {token!r}, which this test's scope does not model. A name "
        f"this evaluator invented a value for would be a guard evaluated against a host "
        f"state nobody chose; add it to the scope deliberately"
    )
    return scope[token], position + 1


def _parse_filtered(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """One value with its filter chain and any `[:n]` slice applied, tightest binding first."""
    value, position = _parse_primary(tokens=tokens, position=position, scope=scope)
    while position < len(tokens) and tokens[position] in ("|", "["):
        if tokens[position] == "[":
            assert (
                tokens[position + 1] == ":" and tokens[position + 3] == "]"
            ), f"`[:n]` is the only subscript this evaluator knows; tokens={tokens[position:]}"
            bound = tokens[position + 2]
            assert bound.isdigit(), f"a slice bound must be a literal; bound={bound!r}"
            assert isinstance(value, str), f"a slice is evaluated for strings only; {value!r}"
            value = value[: int(bound)]
            position += 4
            continue
        name = tokens[position + 1]
        position += 2
        argument: _Value = None
        if position < len(tokens) and tokens[position] == "(":
            argument, position = _parse_or(tokens=tokens, position=position + 1, scope=scope)
            assert (
                position < len(tokens) and tokens[position] == ")"
            ), f"an unclosed filter argument; tokens={tokens}"
            position += 1
        value = _apply_filter(name=name, value=value, argument=argument)
    return value, position


def _parse_unary(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """`not`, which binds looser than a filter and tighter than `and` — as Jinja does."""
    if position < len(tokens) and tokens[position] == "not":
        value, position = _parse_unary(tokens=tokens, position=position + 1, scope=scope)
        return not value, position
    return _parse_filtered(tokens=tokens, position=position, scope=scope)


def _parse_comparison(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """One comparison, or a bare value where the guard carries no operator."""
    left, position = _parse_unary(tokens=tokens, position=position, scope=scope)
    if position < len(tokens) and tokens[position] in _COMPARISONS:
        operator = tokens[position]
        right, position = _parse_unary(tokens=tokens, position=position + 1, scope=scope)
        return _compare(operator=operator, left=left, right=right), position
    return left, position


def _parse_and(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """`and`, evaluated eagerly rather than short-circuit — see `_evaluate`'s docstring."""
    value, position = _parse_comparison(tokens=tokens, position=position, scope=scope)
    while position < len(tokens) and tokens[position] == "and":
        right, position = _parse_comparison(tokens=tokens, position=position + 1, scope=scope)
        value = bool(value) and bool(right)
    return value, position


def _parse_or(
    *, tokens: list[str], position: int, scope: Mapping[str, _Value]
) -> tuple[_Value, int]:
    """`or`, the loosest binding in the vocabulary."""
    value, position = _parse_and(tokens=tokens, position=position, scope=scope)
    while position < len(tokens) and tokens[position] == "or":
        right, position = _parse_and(tokens=tokens, position=position + 1, scope=scope)
        value = bool(value) or bool(right)
    return value, position


def _evaluate(*, expression: str, scope: Mapping[str, _Value]) -> _Value:
    """One guard expression of the role, evaluated against one modelled host state.

    `and` / `or` are evaluated EAGERLY where Jinja short-circuits. That is visible only
    to a guard whose right-hand side reads a name the scope does not model, and it is
    the safer direction: the scope-membership assert in `_parse_primary` then fires and
    says so, instead of a short circuit hiding an unmodelled name until the day a guard
    is reordered.
    """
    tokens = _expression_tokens(expression=expression)
    value, position = _parse_or(tokens=tokens, position=0, scope=scope)
    assert position == len(tokens), (
        f"this test evaluated only part of the role's guard {expression!r}, which is worse "
        f"than not evaluating it: it answers confidently about a different condition; "
        f"remaining={tokens[position:]}"
    )
    return value


def _holds(*, conditions: Iterable[str], scope: Mapping[str, _Value]) -> bool:
    """A whole `when:` or `that:`, which Ansible ANDs."""
    return all(bool(_evaluate(expression=condition, scope=scope)) for condition in conditions)


def _render_templated(*, text: str, scope: Mapping[str, _Value]) -> str:
    """One templated module argument — a path, an owner, a digest-bearing name — rendered."""
    return _TEMPLATED.sub(
        lambda match: str(_evaluate(expression=match["expression"], scope=scope)), text
    )


def _template_expression(*, value: str) -> str:
    """The single expression of a value that is nothing but one `{{ ... }}`."""
    match = _WHOLE_TEMPLATE.fullmatch(value)
    assert (
        match is not None
    ), f"this arm expects a value that is exactly one template expression; value={value!r}"
    return match["expression"]


def _when(*, name: str) -> list[str]:
    """The `when:` of one task of `tasks/main.yml`."""
    return _task_list_field(body=_task_body(name=name), field="when")


def _install_scope(
    *,
    instance: Mapping[str, str],
    host_checksum: str | None,
    source_checksum: str | None,
) -> dict[str, _Value]:
    """Every name the role's binary-install guards read, for one instance and one host state.

    `host_checksum=None` models a `binary_path` with no file at it: `stat` reports
    `exists: false` and OMITS `checksum` entirely rather than reporting an empty one,
    which is exactly the undefined the role's decision expression spells `| default('')`
    against. `source_checksum=None` models the same on the control node.

    The replacement decision is not restated here. It is read out of the role's own
    `set_fact` and evaluated, so a role that decides differently fails these arms
    instead of being re-described by them.
    """
    scope: dict[str, _Value] = dict(_resolved_facts(instance=instance, source=_INVENTORY))
    scope["fabro_server_binary.stat.exists"] = host_checksum is not None
    scope["fabro_server_binary.stat.executable"] = host_checksum is not None
    scope["fabro_server_binary.stat.checksum"] = host_checksum
    scope["fabro_server_binary_source_stat.stat.exists"] = source_checksum is not None
    scope["fabro_server_binary_source_stat.stat.checksum"] = source_checksum
    scope[_REPLACE_FACT] = _evaluate(
        expression=_template_expression(
            value=_module_argument(
                body=_task_body(name=_REPLACE_DECISION),
                module="ansible.builtin.set_fact",
                argument=_REPLACE_FACT,
            )
        ),
        scope=scope,
    )
    return scope


def _restart_scope(
    *,
    instance: Mapping[str, str],
    marker_present: bool,
    running_binary: str | None,
    restart_allowed: bool,
) -> dict[str, _Value]:
    """Every name the role's deferred-restart guards read, for one instance and one host state.

    `running_binary=None` models a probe that could not read the running process's
    `/proc/<pid>/exe` at all — a stopped unit, or a `MainPID` systemd reports as 0.
    `stat` then omits `lnk_source` rather than reporting an empty one, which is the
    undefined the role's decision spells `| default(...)` against.

    Neither the marker path nor the pending decision is restated here: both are read
    out of the role's own `set_fact` and rendered or evaluated, so a role that names
    the marker differently or decides pendingness differently fails these arms instead
    of being re-described by them.
    """
    scope: dict[str, _Value] = dict(_resolved_facts(instance=instance, source=_INVENTORY))
    # `false`/`true` as Ansible delivers an `-e` override and a YAML default — strings
    # a `when:` reaches through `| bool`, which is why the role spells that filter.
    scope["fabro_server_restart_allowed"] = "true" if restart_allowed else "false"
    # Not check mode, and the unit already on disk: the state every arm below is about.
    # The check-mode half of each gate is exercised by the role's existing arms.
    scope["ansible_check_mode"] = False
    scope["fabro_server_unit_file.stat.exists"] = True
    scope["fabro_server_restart_pending_file.stat.exists"] = marker_present
    scope["fabro_server_running_binary.stat.lnk_source"] = running_binary
    scope[_MARKER_FACT] = _render_templated(
        text=_module_argument(
            body=_task_body(name=_MARKER_NAMING_TASK),
            module="ansible.builtin.set_fact",
            argument=_MARKER_FACT,
        ),
        scope=scope,
    )
    scope[_PENDING_FACT] = _evaluate(
        expression=_template_expression(
            value=_module_argument(
                body=_task_body(name=_PENDING_DECISION),
                module="ansible.builtin.set_fact",
                argument=_PENDING_FACT,
            )
        ),
        scope=scope,
    )
    return scope


def _bodies_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order.

    Text-sliced for the same reason `_task_body` is: no YAML library is importable in
    this suite. The ENUMERATION matters where `_task_body` does not — "nothing else in
    the role removes this file" is a claim about every task and handler there is, and a
    reader that can only fetch a task BY NAME cannot make it.
    """
    text = source.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{source.name} must declare its tasks as column-zero `- name:` entries; a task "
        f"this reader cannot see is a task nothing below checks, and the arms using it "
        f"assert over EVERY task rather than over one"
    )
    return [
        (text[start:stop].split("\n", 1)[0][len("- name: ") :].strip(), text[start:stop])
        for start, stop in pairwise([*openings, len(text)])
    ]


def _executable_bodies() -> list[tuple[str, str]]:
    """Every task AND handler of the role — everything an apply can run."""
    return [*_bodies_of(source=_TASKS), *_bodies_of(source=_HANDLERS)]


def _handler_index(*, name: str) -> int:
    """Where one handler sits in `handlers/main.yml`, counted in handlers.

    Order is load-bearing among handlers that share a `listen`: Ansible runs them in the
    order the file declares, so "the marker is cleared only after the restart" is a
    statement about this index and nothing else in the role expresses it.
    """
    names = [handler for handler, _ in _bodies_of(source=_HANDLERS)]
    assert name in names, f"handlers/main.yml must still carry the handler {name!r}"
    return names.index(name)


def _hp_instances() -> list[dict[str, str]]:
    """The two `hp-xubuntu` instances the deferred-restart arms model, fleet first.

    Two rather than one because the marker is a PER-INSTANCE record, and a single
    instance cannot show that: one shared marker would make the fleet instance's
    deferral apply to the candidate's restart, and every arm below would still pass.
    """
    return [
        _instance_named(unit=unit, source=_INVENTORY) for unit in (_FLEET_UNIT, _CANDIDATE_UNIT)
    ]


def _binary_install_guards() -> dict[str, list[str]]:
    """Every condition the arms below evaluate, keyed by where the role spells it."""
    return {
        f"{_PAIR_REFUSAL} (that)": _module_argument_list(
            body=_task_body(name=_PAIR_REFUSAL), module="ansible.builtin.assert", argument="that"
        ),
        f"{_DIGEST_REFUSAL} (that)": _module_argument_list(
            body=_task_body(name=_DIGEST_REFUSAL), module="ansible.builtin.assert", argument="that"
        ),
        f"{_SOURCE_READ} (when)": _when(name=_SOURCE_READ),
        f"{_DIGEST_REFUSAL} (when)": _when(name=_DIGEST_REFUSAL),
        f"{_MISSING_REFUSAL} (when)": _when(name=_MISSING_REFUSAL),
        f"{_STAGE_TASK} (when)": _when(name=_STAGE_TASK),
        f"{_BACKUP_TASK} (when)": _when(name=_BACKUP_TASK),
        f"{_RENAME_TASK} (when)": _when(name=_RENAME_TASK),
    }


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


# --- installing the instance's binary from the control node ----------------


def test_the_binary_install_guards_stay_inside_the_vocabulary_this_test_can_evaluate() -> None:
    """The control on the restricted-Jinja evaluator: every guard it reads must evaluate."""
    scope = _install_scope(
        instance=_instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY),
        host_checksum="0" * 64,
        source_checksum=_CANDIDATE_BINARY_SHA256,
    )
    guards = _binary_install_guards()
    for where, conditions in sorted(guards.items()):
        for condition in conditions:
            evaluated = _evaluate(expression=condition, scope=scope)
            assert isinstance(evaluated, bool), (
                f"{where}: the role's guard {condition!r} must evaluate to a verdict here, or "
                f"the arms below are reading a condition this evaluator does not understand; "
                f"evaluated={evaluated!r}"
            )


def test_an_instance_that_omits_the_binary_install_axes_leaves_the_hosts_binary_alone() -> None:
    """The first assertion: omitting `binary_source` changes neither the host nor the unit."""
    instance = _instance_named(unit=_FLEET_UNIT, source=_INVENTORY)
    present = sorted(axis for axis in _BINARY_AXES if axis in instance)
    assert not present, (
        f"this arm is the no-source arm, so hp-xubuntu's {_FLEET_UNIT} instance must omit both "
        f"{list(_BINARY_AXES)}; it declares {present}, which would make every verdict below a "
        f"claim about an instance that uses them"
    )
    # A host binary that is nothing like the candidate's build, and a control node that
    # does hold that build: the arm must hold because this instance declares no source,
    # never because the two digests happen to agree.
    scope = _install_scope(
        instance=instance, host_checksum="0" * 64, source_checksum=_CANDIDATE_BINARY_SHA256
    )
    for name in (_SOURCE_READ, _DIGEST_REFUSAL, _STAGE_TASK, _BACKUP_TASK, _RENAME_TASK):
        assert not _holds(conditions=_when(name=name), scope=scope), (
            f"{name!r} MUST be skipped for an instance that names no binary_source. A task "
            f"that ran would stage, back up or REPLACE the binary of the live fleet factory "
            f"as a side effect of a converge nobody asked to change a build"
        )
    assert _holds(conditions=_when(name=_MISSING_REFUSAL), scope=scope), (
        f"{_MISSING_REFUSAL!r} MUST still run for an instance the role is not installing a "
        f"binary for: that refusal is the whole preflight such an instance has, and the new "
        f"axes must not quietly disarm it"
    )
    body = _template_body()
    leaked = sorted(axis for axis in _BINARY_AXES if axis in body)
    assert not leaked, (
        f"neither install axis may reach the unit template: these two decide whether the role "
        f"PUTS a binary on the host, not which one the unit starts, and a template that read "
        f"one would make declaring a source rewrite the unit too; leaked={leaked}"
    )


def test_the_role_refuses_a_control_node_binary_that_does_not_match_its_declared_digest() -> None:
    """The second assertion: a source that does not hash to its digest is refused, host untouched."""
    instance = _instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY)
    conditions = _module_argument_list(
        body=_task_body(name=_DIGEST_REFUSAL), module="ansible.builtin.assert", argument="that"
    )
    assert _holds(
        conditions=conditions,
        scope=_install_scope(
            instance=instance, host_checksum="0" * 64, source_checksum=_CANDIDATE_BINARY_SHA256
        ),
    ), (
        "the refusal MUST clear when the control node's file hashes to the declared digest; a "
        "refusal that never clears is a host that can never be converged at all"
    )
    for wrong in (None, "f" * 64, f"{_CANDIDATE_BINARY_SHA256[:-1]}0"):
        assert not _holds(
            conditions=conditions,
            scope=_install_scope(instance=instance, host_checksum="0" * 64, source_checksum=wrong),
        ), (
            f"the role MUST refuse a control-node source whose digest is {wrong!r} against the "
            f"declared {_CANDIDATE_BINARY_SHA256!r}. The digest is the only thing between "
            f"'installs the build version control names' and 'installs whatever is at that "
            f"path today', and that path is in a mutable state tree"
        )
    refusal = _task_index(name=_DIGEST_REFUSAL)
    for name in (_STAGE_TASK, _BACKUP_TASK, _RENAME_TASK, _LIBEXEC_TASK, _UNIT_INSTALL):
        assert refusal < _task_index(name=name), (
            f"the digest refusal MUST come before {name!r}: 'refuses before changing the host' "
            f"is a statement about task order and nothing else in the role expresses it"
        )


def test_a_host_binary_that_differs_from_its_source_is_replaced_by_renaming_a_staged_copy() -> None:
    """The third assertion: differ and it is installed, agree and nothing is touched."""
    instance = _instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY)
    differs = _install_scope(
        instance=instance, host_checksum="0" * 64, source_checksum=_CANDIDATE_BINARY_SHA256
    )
    already = _install_scope(
        instance=instance,
        host_checksum=_CANDIDATE_BINARY_SHA256,
        source_checksum=_CANDIDATE_BINARY_SHA256,
    )
    for name in (_STAGE_TASK, _RENAME_TASK):
        assert _holds(conditions=_when(name=name), scope=differs), (
            f"{name!r} MUST run when the host's binary is not the declared build — that is the "
            f"whole mechanism, and a guard that never opens is a cutover that reports success "
            f"and changes nothing"
        )
        assert not _holds(conditions=_when(name=name), scope=already), (
            f"{name!r} MUST be skipped when the host already holds the declared build. A role "
            f"that re-staged and re-renamed on every converge would report changed forever and "
            f"notify a restart of a live factory each time"
        )
    stage = _task_body(name=_STAGE_TASK)
    binary_path = str(differs["fabro_server_binary_path"])
    staged = _render_templated(
        text=_module_argument(body=stage, module="ansible.builtin.copy", argument="dest"),
        scope=differs,
    )
    assert staged != binary_path and staged.startswith(f"{binary_path}."), (
        f"the copy MUST land BESIDE binary_path, not on it: binary_path is what a running "
        f"server's ExecStart named and what Restart=always re-execs, so a partial write there "
        f"is a factory that cannot start; staged={staged!r} binary_path={binary_path!r}"
    )
    source = _render_templated(
        text=_module_argument(body=stage, module="ansible.builtin.copy", argument="src"),
        scope=differs,
    )
    assert source == _CANDIDATE_BINARY_SOURCE, (
        f"the staged copy MUST come from the control-node path the instance declares; "
        f"source={source!r}"
    )
    argv = [
        _render_templated(text=item, scope=differs)
        for item in _module_argument_list(
            body=_task_body(name=_RENAME_TASK), module="ansible.builtin.command", argument="argv"
        )
    ]
    assert argv[0] == "mv" and argv[-2:] == [staged, binary_path], (
        f"the install MUST complete by RENAMING exactly the staged copy onto binary_path — one "
        f"rename(2) within a directory, so the binary is either the old build or the new one "
        f"and never a half-written file; argv={argv}"
    )


def test_the_outgoing_binary_is_kept_beside_its_replacement_under_its_own_digest() -> None:
    """The fourth assertion: what the host held is kept, named for the build it holds."""
    instance = _instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY)
    outgoing = f"a1b2c3d4e5f60718{'9' * 48}"
    scope = _install_scope(
        instance=instance, host_checksum=outgoing, source_checksum=_CANDIDATE_BINARY_SHA256
    )
    body = _task_body(name=_BACKUP_TASK)
    assert _holds(
        conditions=_when(name=_BACKUP_TASK), scope=scope
    ), "the outgoing binary MUST be kept whenever a replacement is about to happen"
    binary_path = str(scope["fabro_server_binary_path"])
    kept_from = _render_templated(
        text=_module_argument(body=body, module="ansible.builtin.copy", argument="src"),
        scope=scope,
    )
    assert kept_from == binary_path, (
        f"what is kept MUST be the binary the host currently holds at binary_path, not the "
        f"incoming one; kept_from={kept_from!r}"
    )
    assert (
        _module_argument(body=body, module="ansible.builtin.copy", argument="remote_src") == "true"
    ), (
        "the outgoing binary is on the FACTORY HOST, so the copy MUST be remote_src: without "
        "it ansible.builtin.copy looks for that path in the role's files/ directory on the "
        "control node and the keep silently becomes a missing-file failure"
    )
    kept = _render_templated(
        text=_module_argument(body=body, module="ansible.builtin.copy", argument="dest"),
        scope=scope,
    )
    assert kept.startswith(f"{binary_path}."), (
        f"the kept copy MUST sit BESIDE binary_path, where a rollback can find it without "
        f"knowing anything but the instance's own path; kept={kept!r}"
    )
    prefix = kept[len(binary_path) + 1 :].split(".")[0]
    assert len(prefix) >= 8 and outgoing.startswith(prefix), (
        f"the kept copy's name MUST carry a prefix of the SHA256 OF THE BUILD IT HOLDS. A "
        f"timestamp would not do: the point of keeping it is to be able to say which build a "
        f"rollback returns to, and `fabro --version` cannot be asked of a file that is no "
        f"longer the one the unit starts; kept={kept!r} outgoing={outgoing!r}"
    )
    assert _task_index(name=_BACKUP_TASK) < _task_index(name=_RENAME_TASK), (
        "the outgoing binary must be kept BEFORE the rename replaces it; after the rename "
        "there is nothing left to keep"
    )
    first_install = _install_scope(
        instance=instance, host_checksum=None, source_checksum=_CANDIDATE_BINARY_SHA256
    )
    assert not _holds(conditions=_when(name=_BACKUP_TASK), scope=first_install), (
        "a first install has no outgoing binary to keep; a keep that ran anyway would fail the "
        "converge on the one host state this axis exists to repair"
    )
    assert _holds(
        conditions=_when(name=_RENAME_TASK), scope=first_install
    ), "...while the install itself MUST still happen on that host"


def test_an_installed_binary_is_owned_by_the_service_user_and_executable() -> None:
    """The fifth assertion: the instance's service account owns it, mode 0755."""
    instance = _instance_named(unit=_CANDIDATE_UNIT, source=_INVENTORY)
    scope = _install_scope(
        instance=instance, host_checksum="0" * 64, source_checksum=_CANDIDATE_BINARY_SHA256
    )
    body = _task_body(name=_STAGE_TASK)
    for argument, name in (
        ("owner", "fabro_server_host_user"),
        ("group", "fabro_server_host_group"),
    ):
        rendered = _render_templated(
            text=_module_argument(body=body, module="ansible.builtin.copy", argument=argument),
            scope=scope,
        )
        assert rendered == str(scope[name]), (
            f"the installed binary's {argument} MUST be the instance's service account "
            f"({scope[name]!r}); a binary the unit's User= cannot read is a factory that will "
            f"not start; rendered={rendered!r}"
        )
    assert (
        _module_argument(body=body, module="ansible.builtin.copy", argument="mode") == "0755"
    ), "the installed binary MUST be mode 0755 — it is the file systemd execs"
    argv = _module_argument_list(
        body=_task_body(name=_RENAME_TASK), module="ansible.builtin.command", argument="argv"
    )
    assert argv[0] == "mv", (
        f"the owner and mode are set once, on the staged copy, and carried onto binary_path by "
        f"rename(2) — which preserves both. A mechanism that wrote binary_path directly would "
        f"need a second chown nothing here would notice was missing; argv={argv}"
    )


def test_replacing_a_binary_restarts_the_instance_only_through_the_carrying_runs_refusal() -> None:
    """The sixth assertion: a replaced binary reaches the restart only through the one gate."""
    assert _task_list_field(body=_task_body(name=_RENAME_TASK), field="notify") == [
        _FILES_CHANGED
    ], (
        f"the rename MUST notify {_FILES_CHANGED!r}: a host whose binary changed while its "
        f"running server still executes the old inode is drift, and that handler is the only "
        f"thing in the role that either applies it or says out loud that it did not"
    )
    assert _task_index(name=_QUIET_REFUSAL) < _task_index(name=_RENAME_TASK), (
        f"{_QUIET_REFUSAL!r} MUST have already run before the rename, so a factory carrying "
        f"runs has halted the play before its binary is touched"
    )
    probe = _task_list_field(body=_task_body(name=_QUIET_PROBE), field="when")
    assert any("fabro_server_restart_allowed" in condition for condition in probe), (
        f"the carrying-runs probe MUST be on the table whenever a restart is: without that the "
        f"refusal could be skipped on exactly the run that restarts; when={probe}"
    )
    handler = _task_body(name=_RESTART_HANDLER, source=_HANDLERS)
    assert _task_list_field(body=handler, field="listen") == [
        _FILES_CHANGED
    ], f"the restart handler MUST be the one listening to {_FILES_CHANGED!r}"
    gates = _task_list_field(body=handler, field="when")
    assert any("fabro_server_restart_allowed" in condition for condition in gates), (
        f"the restart MUST stay gated on fabro_server_restart_allowed. A binary replacement "
        f"that restarted by default would kill whatever the factory is carrying, which is the "
        f"one thing this role refuses to do; when={gates}"
    )


def test_hp_xubuntu_declares_the_candidate_binary_source_and_its_digest() -> None:
    """The seventh assertion: the v0.382 carrier build, declared where the role reads it."""
    for source in (_ROLE_DOC, _INVENTORY):
        instance = _instance_named(unit=_CANDIDATE_UNIT, source=source)
        assert instance.get("binary_source") == _CANDIDATE_BINARY_SOURCE, (
            f"{source.name}: the candidate instance must declare the control-node path the "
            f"v0.382 carrier build is staged at; declared={instance.get('binary_source')!r}"
        )
        assert instance.get("binary_sha256") == _CANDIDATE_BINARY_SHA256, (
            f"{source.name}: it must declare that build's sha256, which is what makes the "
            f"install an install OF A NAMED BUILD rather than of whatever is at that path; "
            f"declared={instance.get('binary_sha256')!r}"
        )
        assert _HEX64.fullmatch(instance["binary_sha256"]) is not None, (
            f"{source.name}: binary_sha256 must be 64 lowercase hex digits, which is what "
            f"ansible.builtin.stat's sha256 checksum is compared against character for "
            f"character; an abbreviated or upper-cased digest never matches"
        )
        assert instance["binary_source"] != instance["binary_path"], (
            f"{source.name}: binary_source is a CONTROL-NODE path and binary_path is the "
            f"factory host's; a declaration in which they are the same path reads as a copy of "
            f"a file onto itself"
        )


def test_the_role_documents_the_binary_install_axes_and_the_defaults_they_carry() -> None:
    """The eighth assertion: both axes, and their defaults, in the document the operator edits."""
    required = _required_keys()
    optional: dict[str, str] = {}
    for expression in _resolution_expressions().values():
        match = _INSTANCE_EXPRESSION.match(expression)
        if match is None or match["fallback"] is None or match["key"] in required:
            continue
        optional[match["key"]] = match["fallback"]
    section = _doc_section(heading=_AXIS_DOC_HEADING)
    rows = {row["axis"]: row["default"].strip() for row in _DOC_TABLE_ROW.finditer(section)}
    for axis in _BINARY_AXES:
        assert axis in optional, (
            f"{axis} MUST be OPTIONAL: an instance that omits it leaves the host's binary "
            f"exactly as it found it, which a required key cannot express; "
            f"optional={sorted(optional)}"
        )
        assert _evaluate_fallback(expression=optional[axis], variables={}) == "", (
            f"{axis} must default to the empty string — the one value that can mean 'this "
            f"instance's binary is not managed from the control node'; the role defaults it "
            f"from {optional[axis]!r}"
        )
        assert rows.get(axis), (
            f"the {_AXIS_DOC_HEADING!r} section must carry a row for `{axis}` stating the "
            f"default it has. An undocumented axis is one an operator discovers by reading the "
            f"role, which is the drift this document exists to prevent; rows={sorted(rows)}"
        )


# --- carrying a deferred restart across runs -------------------------------


def test_a_refusing_run_records_this_instances_deferred_restart_on_the_host() -> None:
    """The first assertion: files changed under a refusing run leave a per-instance marker."""
    handler = _task_body(name=_DEFER_HANDLER, source=_HANDLERS)
    assert _task_list_field(body=handler, field="listen") == [_FILES_CHANGED], (
        f"the marker MUST be written by a handler listening to {_FILES_CHANGED!r}. That "
        f"notification is the only thing in the role that means 'this instance's files "
        f"changed during this run'; a task could only guess at it, and a marker written on "
        f"every converge would mean nothing by the third one"
    )
    gates = _task_list_field(body=handler, field="when")
    markers: list[str] = []
    for instance in _hp_instances():
        refusing = _restart_scope(
            instance=instance, marker_present=False, running_binary=None, restart_allowed=False
        )
        assert _holds(conditions=gates, scope=refusing), (
            f"{instance['unit_name']}: the marker MUST be written when the run REFUSED the "
            f"restart it was owed. That is the whole defect — measured on hp-xubuntu "
            f"2026-10-11, the apply that installed the carrier build reported 'NOT "
            f"restarted' and recorded that nowhere, so the re-run HOST_VARS.md asks for "
            f"found nothing changed and restarted nothing; when={gates}"
        )
        permitting = _restart_scope(
            instance=instance, marker_present=False, running_binary=None, restart_allowed=True
        )
        assert not _holds(conditions=gates, scope=permitting), (
            f"{instance['unit_name']}: the control arm — a run that APPLIES the restart must "
            f"not also record one as owed. A marker written beside a restart that happened "
            f"is a deferral the next run would apply against an instance that needs nothing"
        )
        marker = _render_templated(
            text=_module_argument(body=handler, module="ansible.builtin.copy", argument="dest"),
            scope=refusing,
        )
        assert marker == refusing[_MARKER_FACT], (
            f"the handler MUST write the marker the role's own set_fact names, not a path "
            f"spelled a second time: two spellings of one path is a deferral recorded where "
            f"nothing reads it; dest={marker!r} fact={refusing[_MARKER_FACT]!r}"
        )
        assert str(instance["unit_name"]) in marker, (
            f"the marker MUST be keyed by unit_name, so each instance on the host owns its "
            f"own record; marker={marker!r}"
        )
        markers.append(marker)
    assert len(set(markers)) == len(markers), (
        f"the two instances MUST record their deferrals at DIFFERENT paths. One shared "
        f"marker would make the fleet instance's deferral apply to the candidate's restart, "
        f"which is a restart of a live factory nobody deferred; markers={markers}"
    )


def test_a_permitting_run_restarts_an_instance_whose_pending_marker_is_present() -> None:
    """The second assertion: a recorded deferral reaches the restart, past the quiet guard."""
    carrier = _task_body(name=_CARRIER_TASK)
    assert _task_list_field(body=carrier, field="notify") == [_FILES_CHANGED], (
        f"the carried deferral MUST notify {_FILES_CHANGED!r} — the same notification a "
        f"changed unit file raises. Reusing it is what makes the restart obey the handler's "
        f"existing refusals instead of acquiring a second, weaker path to systemd"
    )
    assert _task_list_field(body=carrier, field="changed_when") == ["true"], (
        "the carrier MUST report CHANGED unconditionally. Ansible fires a notify only for a "
        "task that changed, so without this the handler is never reached and the marker is "
        "read every run and acted on never — which is the defect this slice exists to fix"
    )
    gates = _task_list_field(body=carrier, field="when")
    handler = _task_body(name=_RESTART_HANDLER, source=_HANDLERS)
    for instance in _hp_instances():
        recorded = _restart_scope(
            instance=instance, marker_present=True, running_binary=None, restart_allowed=True
        )
        assert recorded[_PENDING_FACT] is True, (
            f"{instance['unit_name']}: a present marker MUST make this instance pending on "
            f"its own. The marker is what an earlier refusing run left behind, and reading "
            f"it is the whole mechanism; pending={recorded[_PENDING_FACT]!r}"
        )
        assert _holds(conditions=gates, scope=recorded), (
            f"{instance['unit_name']}: a permitting run MUST carry a recorded deferral into "
            f"the restart. Measured on hp-xubuntu 2026-10-11, the run that was told it may "
            f"restart found nothing changed and notified nothing, so the candidate kept "
            f"serving the build it had before the carrier was installed; when={gates}"
        )
        assert _holds(conditions=_task_list_field(body=handler, field="when"), scope=recorded), (
            f"{instance['unit_name']}: the restart handler's own gate MUST also hold in that "
            f"state, or the notify above reaches a handler that declines it and the deferral "
            f"is carried forward forever"
        )
        refusing = _restart_scope(
            instance=instance, marker_present=True, running_binary=None, restart_allowed=False
        )
        assert not _holds(conditions=gates, scope=refusing), (
            f"{instance['unit_name']}: the control arm — a marker present under a REFUSING "
            f"run must notify nothing. A carrier that fired regardless of the flag would "
            f"restart a live factory on an ordinary converge, which is the one thing this "
            f"role refuses to do"
        )
        settled = _restart_scope(
            instance=instance,
            marker_present=False,
            running_binary=str(recorded["fabro_server_binary_path"]),
            restart_allowed=True,
        )
        assert settled[_PENDING_FACT] is False, (
            f"{instance['unit_name']}: an instance with no marker, already executing its own "
            f"binary_path, owes NOTHING. A pending decision that is always true is a "
            f"permitting run that kills a live factory every time it is used"
        )
        assert not _holds(conditions=gates, scope=settled), (
            f"{instance['unit_name']}: ...and the carrier must be skipped for it, so "
            f"-e fabro_server_restart_allowed=true stays safe to pass on a converged host"
        )
    assert _task_index(name=_QUIET_REFUSAL) < _task_index(name=_CARRIER_TASK), (
        f"{_QUIET_REFUSAL!r} MUST run BEFORE the carrier notifies. 'After the carrying-runs "
        f"refusal passes' is a statement about task order and nothing else in the role "
        f"expresses it: a carrier placed earlier would hand the handler a factory the "
        f"refusal had not yet examined"
    )
    probe = _task_list_field(body=_task_body(name=_QUIET_PROBE), field="when")
    assert any("fabro_server_restart_allowed" in condition for condition in probe), (
        f"the carrying-runs probe MUST be on the table for exactly the runs this carrier "
        f"fires on, or the refusal above is ordered before a guard that never ran; "
        f"when={probe}"
    )


def test_a_permitting_run_restarts_an_instance_executing_a_file_other_than_its_binary() -> None:
    """The third assertion: a running server on the wrong file is pending without a marker.

    THE BEHAVIOURAL ARM COMES FIRST, deliberately. Read the role's own pending decision
    before reading the probe tasks that feed it, so a role that carries the probes and
    does not CONSULT them fails on the verdict rather than on a task name — and so this
    arm's own Red proved the behaviour unimplemented rather than merely unnamed.
    """
    gates = _task_list_field(body=_task_body(name=_CARRIER_TASK), field="when")
    handler_gates = _task_list_field(
        body=_task_body(name=_RESTART_HANDLER, source=_HANDLERS), field="when"
    )
    for instance in _hp_instances():
        declared = str(
            _restart_scope(
                instance=instance, marker_present=False, running_binary=None, restart_allowed=True
            )["fabro_server_binary_path"]
        )
        stale = _restart_scope(
            instance=instance,
            marker_present=False,
            running_binary=f"{declared}.a1b2c3d4e5f6.bak",
            restart_allowed=True,
        )
        assert stale[_PENDING_FACT] is True, (
            f"{instance['unit_name']}: a server executing a file other than its own "
            f"binary_path MUST be pending WITHOUT a marker. That is the state nobody "
            f"recorded — a binary replaced out of band, or a marker removed by hand — and "
            f"it is exactly hp-xubuntu's candidate on 2026-10-11, running the pre-carrier "
            f"build with the carrier already at binary_path"
        )
        assert _holds(conditions=gates, scope=stale) and _holds(
            conditions=handler_gates, scope=stale
        ), (
            f"{instance['unit_name']}: ...and a permitting run MUST carry it through to the "
            f"restart handler; when={gates}"
        )
        current = _restart_scope(
            instance=instance,
            marker_present=False,
            running_binary=declared,
            restart_allowed=True,
        )
        assert current[_PENDING_FACT] is False and not _holds(conditions=gates, scope=current), (
            f"{instance['unit_name']}: the control arm — a server already executing its own "
            f"binary_path owes nothing. A comparison that read this as pending would restart "
            f"a converged live factory on every permitting run"
        )
        unreadable = _restart_scope(
            instance=instance, marker_present=False, running_binary=None, restart_allowed=True
        )
        assert unreadable[_PENDING_FACT] is False and not _holds(
            conditions=gates, scope=unreadable
        ), (
            f"{instance['unit_name']}: the second control arm — a probe that could not read "
            f"the running process at all (a stopped unit, a MainPID of 0, an unreadable "
            f"/proc entry) MUST mean 'nothing owed'. Restarting a live factory on the "
            f"strength of a probe that FAILED is the one outcome worse than leaving a "
            f"deferral unapplied"
        )
        assert (
            _restart_scope(
                instance=instance, marker_present=True, running_binary=None, restart_allowed=True
            )[_PENDING_FACT]
            is True
        ), (
            f"{instance['unit_name']}: ...and that fail-open must not reach the MARKER term: "
            f"a deferral that WAS recorded still survives a probe that failed"
        )
    argv = _argv_items(body=_task_body(name=_RUNNING_PID_TASK))
    assert argv[:1] == ["systemctl"] and any("fabro_server_unit_name" in item for item in argv), (
        f"the PID MUST be read for THIS instance's own unit. A PID read for any other unit "
        f"would answer about a sibling server on the same host, and on hp-xubuntu that "
        f"sibling is the live fleet factory; argv={argv}"
    )
    probe = _task_body(name=_RUNNING_BINARY_TASK)
    probed = _module_argument(body=probe, module="ansible.builtin.stat", argument="path")
    assert "/exe" in probed and "fabro_server_running_pid" in probed, (
        f"the executed file MUST be read from /proc/<MainPID>/exe — what the KERNEL knows "
        f"the running process was exec'd from. Nothing a digest comparison can say about a "
        f"file on disk substitutes for it: a rename within a directory leaves the inode a "
        f"running process execs untouched, so a replaced binary changes the disk and not "
        f"the process; path={probed!r}"
    )
    assert _module_argument(body=probe, module="ansible.builtin.stat", argument="follow") == (
        "false"
    ), (
        "the stat MUST NOT follow the link: the wanted answer is lnk_source, the path "
        "/proc/<pid>/exe POINTS AT, and a followed stat reports the link's target metadata "
        "while losing the name the comparison is about"
    )
    for writer in (_STAGE_TASK, _RENAME_TASK, _UNIT_INSTALL, _LIBEXEC_TASK):
        assert _task_index(name=_RUNNING_BINARY_TASK) < _task_index(name=writer), (
            f"the running-binary probe MUST read the host BEFORE {writer!r} writes to it. "
            f"Taken afterwards it would answer about the server this run produced rather "
            f"than the one it inherited, which is the comparison that is being made"
        )


def test_restarting_an_instance_removes_its_restart_pending_marker() -> None:
    """The fourth assertion: the restart is what clears the record, and the only thing."""
    handler = _task_body(name=_CLEAR_HANDLER, source=_HANDLERS)
    assert _task_list_field(body=handler, field="listen") == [_FILES_CHANGED], (
        f"the marker MUST be cleared by a handler on the same {_FILES_CHANGED!r} "
        f"notification the restart itself listens to. A clear anywhere else would run on "
        f"converges the restart did not"
    )
    assert _module_argument(body=handler, module="ansible.builtin.file", argument="state") == (
        "absent"
    ), "clearing the record means REMOVING the file; anything else leaves it readable"
    assert _handler_index(name=_RESTART_HANDLER) < _handler_index(name=_CLEAR_HANDLER), (
        f"the clear MUST be declared AFTER {_RESTART_HANDLER!r}. Ansible runs handlers "
        f"sharing a listen in file order, so a clear declared first would remove the record "
        f"and THEN attempt the restart — and a restart that fails would leave an instance "
        f"owing one with nothing on the host saying so"
    )
    gates = _task_list_field(body=handler, field="when")
    for instance in _hp_instances():
        restarting = _restart_scope(
            instance=instance, marker_present=True, running_binary=None, restart_allowed=True
        )
        assert _holds(conditions=gates, scope=restarting), (
            f"{instance['unit_name']}: a run that RESTARTS the instance MUST clear its "
            f"marker. A marker that outlives the restart it asked for makes every later "
            f"permitting run restart a live factory that owes nothing; when={gates}"
        )
        cleared = _render_templated(
            text=_module_argument(body=handler, module="ansible.builtin.file", argument="path"),
            scope=restarting,
        )
        assert cleared == restarting[_MARKER_FACT], (
            f"the handler MUST remove THIS instance's marker, the one the role's set_fact "
            f"names. A clear aimed at any other path would leave this instance's deferral "
            f"standing and remove a sibling's; path={cleared!r}"
        )
        refusing = _restart_scope(
            instance=instance, marker_present=True, running_binary=None, restart_allowed=False
        )
        assert not _holds(conditions=gates, scope=refusing), (
            f"{instance['unit_name']}: the control arm — a run that did NOT restart must not "
            f"clear the record either. That is the whole bug this slice fixes, reintroduced "
            f"one layer down: the deferral would be erased by the very converge that failed "
            f"to apply it"
        )
    removers = [
        (name, body)
        for name, body in _executable_bodies()
        if _MARKER_FACT in body
        and re.search(r"^    state: absent$", body, re.MULTILINE) is not None
    ]
    assert [name for name, _ in removers] == [_CLEAR_HANDLER], (
        f"the restart MUST be the ONLY thing in the role that removes a marker, so a "
        f"deferral survives every converge until the window is actually taken; the role "
        f"removes it in {[name for name, _ in removers]}"
    )
