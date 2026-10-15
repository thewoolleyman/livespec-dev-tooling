"""Consumer-tier: the `## Fabro factory host provisioning` section of
`SPECIFICATION/non-functional-requirements.md`, read for the one piece of state the
`fabro_server` role used to refuse rather than create — the checkout its unit's
`WorkingDirectory` names.

WHY THE CHECKOUT IS PROVISIONING AND NOT OUT-OF-BAND STATE. Every other refusal in
the role's preflight block stands in for a manual step only an operator can take: a
`SESSION_SECRET` Fabro itself generates, a GitHub App key held in the instance's own
vault, a `tailscale serve` mapping that lives in another repository, a binary this
role will never build. A git clone is none of those — it is derivable from one URL —
and on a factory host that has none, the refusal "clone it before applying this role"
left exactly one way through: a hand clone. That is what the fleet host guard denies
and what the plan assertion "nothing on that host is set up by hand beyond the role's
documented out-of-band state" forbids. So the role takes the clone, and the section's
"One play, applied after a drift read" paragraph — a service installed by hand is
drift to be expressed in the play, never an accepted exception — is the reason it has
to.

WHY THESE ARMS READ THE ROLE'S OWN GATES RATHER THAN RUNNING ANSIBLE. Ansible and
Jinja are not importable here: `ansible-lint` and `ansible-playbook` resolve through
`uvx` against their own interpreter (see the justfile), because ansible-core 2.21
requires a Python floor this repository does not carry, and no test may depend on a
network-resolved second interpreter. The questions this file asks are anyway
questions about GATES — whether a clone fires on a host that has no checkout and not
on one that has, whether a drift read reports it instead of performing it, whether
the refusal still refuses a host that declares no remote — and a gate is a `when:`
expression. So the arms below read those expressions out of `tasks/main.yml` and
EVALUATE them against modelled host states, rather than restating what the role says.

THE EVALUATOR IS A RESTRICTED JINJA, AND IT REFUSES WHAT IT DOES NOT KNOW. Its
vocabulary is exactly what these gates use: a reference, `| length > 0`, an optional
`| default(true|false)` or `| bool`, `not`, and parentheses. An unmodelled name
ASSERTS rather than defaulting, and an unknown FORM asserts rather than being skipped
— an unevaluated gate is a test that has stopped checking whether a converge would
clone over a live factory's working tree, and it would keep passing while it did so.

WHAT THE EVALUATOR CANNOT PROVE, AND IS NOT CLAIMED TO. It evaluates gates; it does
not run Ansible, so it cannot prove that `ansible.builtin.git` clones. Those arms
assert the SHAPE instead — that the clone's `repo` is the declared remote, its `dest`
the declared checkout, its `version` the declared ref, that it runs as the instance's
service user, that it sits BEFORE the refusal that needs its result, and that it
spells `update: false` so the one module in this role capable of resetting a working
tree is configured never to.

BOTH GUARDS ON THE CLONE ARE LOAD-BEARING, AND THEY GUARD DIFFERENT THINGS — which is
why two arms below check them separately. The `when:` is the DECISION: clone only
where there is nothing to lose. `update: false` is the CONSEQUENCE of that decision
being wrong, because `ansible.builtin.git` defaults to `update: true`, which resets
the working tree HARD onto `version` — and the directory this names is the
`WorkingDirectory` of a server that is carrying live Fabro runs while the role runs
against it. A live factory's uncommitted work is not a thing to leave to a single
condition.

CONTROL ARMS. Every positive arm is paired against the opposite host state, because a
gate that fired unconditionally would satisfy a one-sided arm: the clone arm is paired
with a host whose checkout exists, the refusal arm with a host that declares a remote,
and the refusal's own `that:` conditions are evaluated against BOTH a present and an
absent checkout, so a predicate that accepted everything could not pass.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "fabro_server"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

# The tasks this file is about, named rather than described: the probe that reads the
# host, the clone that provisions what the probe did not find, and the refusal whose
# message used to be a factory host's only instruction.
_CHECKOUT_PROBE = "Look for the checkout this instance runs in"
_CLONE_TASK = "Clone this host's checkout from the remote it declares"
_CHECKOUT_REFUSAL = "Refuse an instance whose checkout is missing"

# The per-host axes. `fabro_server_host_checkout` predates this work; the other two are
# the optional axis this adds — the remote a host with no checkout is cloned from, and
# the ref that clone is left on.
_CHECKOUT = "fabro_server_host_checkout"
_REMOTE_AXIS = "fabro_server_host_checkout_remote"
_REF_AXIS = "fabro_server_host_checkout_ref"
_SERVICE_USER = "fabro_server_host_user"

# The registers the gates read: the probe's stat, and the clone's own result.
_PROBE_EXISTS = "fabro_server_checkout.stat.exists"
_PROBE_ISDIR = "fabro_server_checkout.stat.isdir"
_CLONE_REGISTER = "fabro_server_checkout_clone"

# `ansible.builtin.git`'s own default is `update: true`, which RESETS the working tree
# onto `version`. The value this role must spell is the other one, and it is stated here
# rather than read out of the file an arm checks.
_NO_UPDATE = "false"

_GIT_MODULE = "ansible.builtin.git"
_STAT_MODULE = "ansible.builtin.stat"
_ASSERT_MODULE = "ansible.builtin.assert"
# The three modules that may name the checkout path: two that only READ it, and the one
# that creates it. Any other module naming that path is a converge writing into a live
# factory's working tree, which is the thing this whole file exists to bound.
_PERMITTED_CHECKOUT_MODULES = frozenset({_STAT_MODULE, _ASSERT_MODULE, _GIT_MODULE})

_DOC_HEADING = "## The checkout the server runs in"

# --- reading the committed role --------------------------------------------

_TASK_OPENING = re.compile(r"^- name: ", re.MULTILINE)
# A list field's body is its `- ` items AND the comment lines between them. Matching the
# comments is load-bearing rather than tidy: every gate in this role is commented BETWEEN
# its conditions, so a pattern accepting only `- ` items stops at the first comment and
# reports the gate as having no conditions at all — and `all([])` is True, so such a gate
# reads as firing unconditionally.
#
# TWO depths, because the two gates this file evaluates sit at two: a task's own `when:`
# is a task key, while an assert's `that:` is an ARGUMENT OF THE MODULE and so one indent
# deeper. One pattern would read the shallower gate and silently return nothing for the
# other — a `that:` nobody evaluated is a refusal this file claims to have checked.
_TASK_LIST_FIELD = re.compile(
    r"^  (?P<field>[a-z_]+):\n(?P<items>(?:    (?:#|- ).*\n)+)", re.MULTILINE
)
_MODULE_LIST_FIELD = re.compile(
    r"^    (?P<field>[a-z_]+):\n(?P<items>(?:      (?:#|- ).*\n)+)", re.MULTILINE
)
_SCALAR_FIELD = re.compile(r"^  (?P<field>[a-z_]+): (?P<value>[^\n>|].*)$", re.MULTILINE)
# A module's own argument, one indent deeper than the task's keys.
_MODULE_ARGUMENT = re.compile(r"^    (?P<argument>[a-z_]+): (?P<value>.+)$", re.MULTILINE)
# A task's module is its one key carrying a dotted collection name; the task's other keys
# (`become`, `when`, `register`) never do.
_MODULE_KEY = re.compile(r"^  (?P<module>[a-z_]+\.[a-z_.]+):$", re.MULTILINE)
_ROLE_DEFAULT = re.compile(r"^(?P<name>fabro_server_[a-z_0-9]+): (?P<value>\S+)$", re.MULTILINE)
# The checkout axis WITHOUT the two that extend its name, so a task that merely names the
# remote does not read as a task that touches the checkout directory.
_CHECKOUT_REFERENCE = re.compile(rf"{_CHECKOUT}(?![a-z_])")
_LIST_ITEM = "- "


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _tasks() -> list[tuple[str, str]]:
    """Every top-level task of `tasks/main.yml`, as `(name, body)` in file order.

    Text-sliced rather than YAML-parsed because no YAML library is importable in this
    suite — `[dependency-groups].dev` carries none, deliberately, since the package is
    dependency-free. A task begins at a column-zero `- name:` line and ends at the next
    one, which is the shape every role file in this tree uses.
    """
    text = _TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in _TASK_OPENING.finditer(text)]
    assert openings, (
        f"{_TASKS.name} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a converge path "
        f"nothing here checks"
    )
    parsed: list[tuple[str, str]] = []
    for start, stop in pairwise([*openings, len(text)]):
        body = text[start:stop]
        parsed.append((body.split("\n", 1)[0][len("- name: ") :].strip(), body))
    return parsed


def _named(*, name: str) -> str:
    """One task of the role, from its `- name:` to the next one."""
    matching = [body for task_name, body in _tasks() if task_name == name]
    assert len(matching) == 1, (
        f"{_TASKS.name} must carry exactly one task named {name!r}; found {len(matching)}. "
        f"These arms read the role's own gates out of it rather than restating them, so a "
        f"missing or renamed task is a test that has stopped checking anything"
    )
    return matching[0]


def _position(*, name: str) -> int:
    """Where one task sits in `tasks/main.yml`, counted in tasks.

    Order is load-bearing and not cosmetic here: "clones it BEFORE the preflight that
    requires it" is a statement about where a task sits relative to another, and nothing
    else in the role expresses it.
    """
    names = [task_name for task_name, _ in _tasks()]
    assert name in names, (
        f"{_TASKS.name} must still carry the task {name!r}; the ordering arm below has no "
        f"other handle on it"
    )
    return names.index(name)


def _module_of(*, body: str) -> str:
    """The Ansible module one task invokes."""
    match = _MODULE_KEY.search(body)
    assert match is not None, (
        f"every task reached by these arms must invoke its module through the fully "
        f"qualified collection name; this one does not, so this reader cannot tell a read "
        f"from a write;\nbody={body!r}"
    )
    return match["module"]


def _argument(*, body: str, argument: str) -> str:
    """One argument of the module a task invokes."""
    found = {match["argument"]: match["value"] for match in _MODULE_ARGUMENT.finditer(body)}
    assert argument in found, (
        f"the task must pass {argument!r} to its module; it passes "
        f"{sorted(found)}. An argument this reader cannot see is one the module takes its "
        f"own default for, and every default that matters here is the dangerous one"
    )
    return _unquote(value=found[argument])


def _conditions(*, body: str, field: str, pattern: re.Pattern[str]) -> list[str]:
    """One `when:` or `that:` of a task, as the list of conditions Ansible ANDs.

    `pattern` selects the depth the field sits at — `_TASK_LIST_FIELD` for a task's own
    `when:`, `_MODULE_LIST_FIELD` for an assert's `that:`.

    The LIST shape only. Ansible accepts a one-line scalar too, and this reader refuses
    it on purpose: the arms below each ask whether a gate holds on one modelled host
    state, and a gate moved onto one line would read as having no conditions at all —
    `all([])` is True, so the gate would read as firing unconditionally while looking
    exactly like a gate that passed. Refusing the shape is how that stays visible.
    """
    matching = [match for match in pattern.finditer(body) if match["field"] == field]
    assert len(matching) == 1, (
        f"this arm reads the {field!r} of a task and found {len(matching)} in the list "
        f"shape this reader understands. Spell it as a `- ` list, one condition per line, "
        f"as every other gate in this role does;\nbody={body!r}"
    )
    return [
        line.strip()[len(_LIST_ITEM) :].strip()
        for line in matching[0]["items"].splitlines()
        if line.strip().startswith(_LIST_ITEM)
    ]


def _scalar(*, body: str, field: str) -> str | None:
    """One of a task's own keys — `become_user`, `register`, `check_mode` — or None."""
    for match in _SCALAR_FIELD.finditer(body):
        if match["field"] == field:
            return _unquote(value=match["value"])
    return None


def _role_defaults() -> dict[str, str]:
    """Every scalar the role's `defaults/main.yml` declares."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
    }
    assert declared, "the role must declare its variables in defaults/main.yml"
    return declared


def _doc_section(*, heading: str) -> str:
    """One `## ` section of the role's HOST_VARS.md, up to the next `## `."""
    text = _ROLE_DOC.read_text(encoding="utf-8")
    start = text.find(f"\n{heading}\n")
    assert start >= 0, (
        f"{_ROLE_DOC.name} must carry the section {heading!r}. The section IS the "
        f'documentation obligation the spec\'s "Documented beside the values" paragraph '
        f"places on this role, so its absence is the obligation unmet"
    )
    # Past the leading newline the search anchored on, so the split below cannot find
    # this section's own opening and hand back an empty string.
    return text[start + 1 :].split("\n## ", maxsplit=1)[0]


def _prose(*, section: str) -> str:
    """One document section with markdown emphasis removed, for phrase matching.

    The arms below look for names an operator has to be able to read, and in correct
    markdown a variable or a path inside a sentence is backticked — so matching the raw
    bytes would make them pass only for prose that omitted the formatting the rest of
    this document uses, which is a test dictating typography rather than content.
    """
    return section.replace("`", "").replace("**", "")


# --- the role's own gates, evaluated --------------------------------------
#
# The vocabulary is exactly what these gates spell and NOTHING ELSE: a reference
# (optionally `| bool`, optionally `| default(true|false)`), a `| length > 0` emptiness
# test, `not`, and parentheses. `and` / `or` are deliberately ABSENT rather than written
# and never exercised: Ansible ANDs a `when:` LIST, so every gate these arms read is one
# condition per line, and a joiner inside a single condition would be a shape this
# evaluator has never evaluated. It refuses such a condition outright — see the
# "does not know" assert below — rather than being quietly taught a branch no committed
# gate exercises, which is the shape that lets an evaluator drift away from the role.

_REFERENCE = re.compile(
    r"(?P<name>[a-z_][a-z_0-9.]*)(?:\s*\|\s*bool)?"
    r"(?:\s*\|\s*default\((?P<fallback>true|false)\))?(?:\s*\|\s*bool)?"
)
_NON_EMPTY = re.compile(r"(?P<name>[a-z_][a-z_0-9.]*)\s*\|\s*length\s*>\s*0")


def _value(*, name: str, fallback: str | None, scope: Mapping[str, object]) -> object:
    """One name the role's gate reads, resolved against a MODELLED host state.

    An unmodelled name asserts rather than defaulting: a gate evaluated against a value
    this test invented is a gate evaluated against a different condition, which is worse
    than one left unevaluated because it answers confidently.
    """
    if name in scope:
        return scope[name]
    assert fallback is not None, (
        f"the role's checkout gate reads {name!r}, which this test does not model and the "
        f"role does not default. Model it rather than letting the arms below answer about "
        f"a host state that was never described"
    )
    return fallback == "true"


def _truth(*, condition: str, scope: Mapping[str, object]) -> bool:
    """One gate condition of the role, evaluated against one modelled host state."""
    text = condition.strip()
    if text.startswith("not "):
        return not _truth(condition=text[len("not ") :], scope=scope)
    if text.startswith("(") and text.endswith(")"):
        return _truth(condition=text[1:-1], scope=scope)
    non_empty = _NON_EMPTY.fullmatch(text)
    if non_empty is not None:
        declared = _value(name=non_empty["name"], fallback=None, scope=scope)
        assert isinstance(declared, str), (
            f"`| length > 0` is an emptiness test over a declared STRING here; "
            f"{non_empty['name']!r} is modelled as {declared!r}"
        )
        return len(declared) > 0
    reference = _REFERENCE.fullmatch(text)
    assert reference is not None, (
        f"the role's checkout gate carries {text!r}, a form this evaluator does not know. "
        f"Teach it the new form rather than leaving the gate unevaluated: an unevaluated "
        f"gate is a test that has stopped checking whether a converge clones over a live "
        f"factory's working tree"
    )
    return bool(_value(name=reference["name"], fallback=reference["fallback"], scope=scope))


def _fires(*, name: str, scope: Mapping[str, object]) -> bool:
    """Whether every `when:` condition of one task holds — Ansible ANDs a list.

    An EMPTY list asserts rather than returning True. Ansible's own reading of a missing
    `when:` is "always", so returning True would be faithful to Ansible and useless here:
    every arm below asks whether a gate fires on one host state and not another, and a
    gate this reader could not see answers both questions the same way while looking
    exactly like a gate that passed.
    """
    conditions = _conditions(body=_named(name=name), field="when", pattern=_TASK_LIST_FIELD)
    assert conditions, (
        f"this arm asks whether {name!r} fires, and the task carries no `when:` this "
        f"reader can see. Either the gate is genuinely absent — in which case the task "
        f"runs on every host, including one whose checkout a live factory is working in — "
        f"or it is spelled in a shape `_conditions` does not read, which is a test that "
        f"has stopped checking"
    )
    return all(_truth(condition=condition, scope=scope) for condition in conditions)


def _host_state(*, remote: str, checkout_exists: bool, cloned: bool) -> dict[str, object]:
    """One modelled factory host: what it declares, what it has, and what the clone did.

    `cloned` is the clone task's own register. In a real run it is `changed` only where
    the gate above it fired AND the module succeeded, so a state that says a clone
    happened on a host that already had a checkout is not reachable — the arms below
    never construct one.
    """
    return {
        _REMOTE_AXIS: remote,
        _PROBE_EXISTS: checkout_exists,
        _PROBE_ISDIR: checkout_exists,
        f"{_CLONE_REGISTER}.changed": cloned,
    }


def test_a_host_that_declares_the_remote_and_has_no_checkout_gets_one_cloned_first() -> None:
    """The first assertion: the clone fires, as the service user, before the preflight."""
    bare = _host_state(remote="https://github.com/o/r.git", checkout_exists=False, cloned=False)
    assert _fires(name=_CLONE_TASK, scope=bare), (
        f"{_CLONE_TASK!r} MUST fire on a host that declares its checkout remote and has no "
        f"checkout directory. That host — gmktec-xubuntu on the day it is provisioned — is "
        f"the whole case: without the clone its only way past the refusal below is a hand "
        f"clone, which the fleet host guard denies"
    )
    body = _named(name=_CLONE_TASK)
    assert _module_of(body=body) == _GIT_MODULE, (
        f"the clone must go through {_GIT_MODULE}; a hand-rolled `command: git clone` is a "
        f"task with no check mode and no idempotence of its own"
    )
    assert _argument(body=body, argument="repo") == f"{{{{ {_REMOTE_AXIS} }}}}", (
        f"the clone must read its remote from {_REMOTE_AXIS}, the axis the host declares. "
        f'A remote embedded in the role is the host-specific value the spec\'s "One play" '
        f"paragraph forbids a role from carrying"
    )
    assert _argument(body=body, argument="dest") == f"{{{{ {_CHECKOUT} }}}}", (
        f"the clone must land at {_CHECKOUT} — the directory the unit's WorkingDirectory "
        f"names and the preflight below stats. A clone anywhere else leaves the refusal "
        f"refusing while reporting a change"
    )
    assert _argument(body=body, argument="version") == f"{{{{ {_REF_AXIS} }}}}", (
        f"the clone must leave the new checkout on the ref {_REF_AXIS} names, so what a "
        f"freshly provisioned factory runs is declared rather than whatever the remote's "
        f"HEAD happened to be"
    )
    assert _scalar(body=body, field="become") == "true", (
        "the clone needs privilege: Ansible reaches these hosts as an account that is not "
        "necessarily the service user"
    )
    assert _scalar(body=body, field="become_user") == f"{{{{ {_SERVICE_USER} }}}}", (
        f"the checkout must be OWNED by the instance's service user, so the clone runs as "
        f"{_SERVICE_USER}. A root-owned checkout is one the factory's own server cannot "
        f"write to — and the role has no task that would fix the ownership afterwards"
    )
    assert _position(name=_CHECKOUT_PROBE) < _position(name=_CLONE_TASK), (
        f"{_CLONE_TASK!r} must come AFTER {_CHECKOUT_PROBE!r}: its gate reads that probe's "
        f"register, and a gate reading an unregistered variable is a clone decided on "
        f"nothing"
    )
    assert _position(name=_CLONE_TASK) < _position(name=_CHECKOUT_REFUSAL), (
        f"{_CLONE_TASK!r} must come BEFORE {_CHECKOUT_REFUSAL!r}. The refusal is what the "
        f"clone exists to satisfy; ordered the other way the role refuses the host it was "
        f"about to provision, and the axis changes nothing"
    )


def test_a_host_whose_checkout_already_exists_is_left_exactly_as_it_was_found() -> None:
    """The second assertion: the working tree and HEAD of a live factory's checkout."""
    live = _host_state(remote="https://github.com/o/r.git", checkout_exists=True, cloned=False)
    assert not _fires(name=_CLONE_TASK, scope=live), (
        f"{_CLONE_TASK!r} MUST be skipped on a host whose checkout directory already "
        f"exists, even one that declares the remote. That directory is the "
        f"WorkingDirectory of a server carrying live Fabro runs while this role runs "
        f"against it, and it holds uncommitted work no converge may touch"
    )
    body = _named(name=_CLONE_TASK)
    assert _argument(body=body, argument="update") == _NO_UPDATE, (
        f"the clone must spell `update: {_NO_UPDATE}`. This is the SECOND guard, and it "
        f"guards something different from the gate above: {_GIT_MODULE} defaults to "
        f"`update: true`, which resets the working tree HARD onto `version`. The gate is "
        f"the decision; this is what happens if the decision is ever wrong, and a live "
        f"factory's uncommitted work is not a thing to leave to one condition"
    )
    for name, task in _tasks():
        if _CHECKOUT_REFERENCE.search(task) is None:
            continue
        module = _module_of(body=task)
        assert module in _PERMITTED_CHECKOUT_MODULES, (
            f"{name!r} names {_CHECKOUT} and invokes {module}, which is neither a read nor "
            f"the clone. Every other task that may name a live factory's checkout must "
            f"only READ it: {sorted(_PERMITTED_CHECKOUT_MODULES)}"
        )
        if module == _GIT_MODULE:
            assert name == _CLONE_TASK, (
                f"{name!r} is a second {_GIT_MODULE} task against the checkout. One clone, "
                f"gated on the directory being absent, is the whole of what this role may "
                f"do to that tree"
            )


def test_a_host_that_declares_no_remote_is_refused_by_the_checkout_preflight_as_before() -> None:
    """The third assertion: the undeclared host's path through the role is unchanged."""
    undeclared = _host_state(remote="", checkout_exists=False, cloned=False)
    assert not _fires(name=_CLONE_TASK, scope=undeclared), (
        f"{_CLONE_TASK!r} MUST be skipped on a host that declares no checkout remote. The "
        f"empty default is the word for \"this host's checkout is not provisioned from "
        f'here", and it has to leave behaviour exactly as it was before the axis existed'
    )
    assert _fires(name=_CHECKOUT_REFUSAL, scope=undeclared), (
        f"{_CHECKOUT_REFUSAL!r} MUST still run for a host that declares no remote and has "
        f"no checkout. The refusal is that host's only signal; skipping it would let the "
        f"role proceed to write a unit whose WorkingDirectory does not exist"
    )
    conditions = _conditions(
        body=_named(name=_CHECKOUT_REFUSAL), field="that", pattern=_MODULE_LIST_FIELD
    )
    assert not all(_truth(condition=condition, scope=undeclared) for condition in conditions), (
        f"and it must REFUSE: the refusal's own `that:` conditions have to read false for "
        f"a host with no checkout directory. A refusal that fires and passes is the "
        f"quietest regression available here;\nthat={conditions!r}"
    )
    present = _host_state(remote="", checkout_exists=True, cloned=False)
    assert all(_truth(condition=condition, scope=present) for condition in conditions), (
        "the control arm: those same conditions must read true for a host that has its "
        "checkout, or the arm above would pass against a predicate that refused every host"
    )


def test_a_check_run_reports_the_clone_it_would_make_and_changes_nothing() -> None:
    """The fourth assertion: `--check` reports the clone, and the preflight stands aside."""
    body = _named(name=_CLONE_TASK)
    assert _scalar(body=body, field="check_mode") is None, (
        f"{_CLONE_TASK!r} must NOT carry `check_mode:`, unlike every probe around it. The "
        f"probes set `check_mode: false` because a drift report that skipped its own reads "
        f"would report on a host it never inspected; this task WRITES, so leaving check "
        f"mode alone is what makes `just ansible-drift` report the clone instead of "
        f"performing it"
    )
    would_clone = _host_state(
        remote="https://github.com/o/r.git", checkout_exists=False, cloned=True
    )
    assert not _fires(name=_CHECKOUT_REFUSAL, scope=would_clone), (
        f"{_CHECKOUT_REFUSAL!r} MUST stand aside once the clone reports a change. Under "
        f"`--check` nothing is written, so the probe's register still says the directory "
        f"is absent — a refusal reading only that register would fail the drift read of "
        f"exactly the host this axis was added for, and an operator cannot apply a play "
        f"whose drift report they are forbidden to obtain"
    )
    applied = _host_state(remote="https://github.com/o/r.git", checkout_exists=True, cloned=False)
    assert _fires(name=_CHECKOUT_REFUSAL, scope=applied), (
        "the control arm: a run that cloned nothing — because the checkout was already "
        "there — must still reach the refusal. A gate that stood aside on every run would "
        "retire the preflight rather than accommodate the clone"
    )


def test_the_role_document_states_the_checkout_remote_axis_and_that_it_never_resets() -> None:
    """The fifth assertion: HOST_VARS.md carries the axis, its default and the rule."""
    defaults = _role_defaults()
    assert defaults.get(_REMOTE_AXIS) == "", (
        f"{_REMOTE_AXIS} must be declared in defaults/main.yml and must default to EMPTY. "
        f'Empty is the only safe default because it is the one value that means "touch '
        f'nothing", which is what every host did before the axis existed — and a variable '
        f"an operator discovers by reading tasks/ is the drift HOST_VARS.md prevents"
    )
    assert defaults.get(_REF_AXIS), (
        f"{_REF_AXIS} must be declared in defaults/main.yml with a non-empty default; "
        f"{_GIT_MODULE} takes its own default for an empty `version`, which is a ref this "
        f"role would then not be declaring at all"
    )
    section = _doc_section(heading=_DOC_HEADING)
    assert len(section.split()) > 80, (
        f"{_DOC_HEADING!r} must carry the mechanism it names, not a stub. The operator "
        f"reading it is the one provisioning a new factory host, and what they need — that "
        f"declaring one URL is the whole of it, and that an existing checkout is untouched "
        f"— is not in the role's task comments;\nsection={section!r}"
    )
    prose = _prose(section=section)
    for axis in (_REMOTE_AXIS, _REF_AXIS, _CHECKOUT):
        assert axis in prose, (
            f"the section must name {axis}. An undocumented variable is one an operator "
            f"discovers by reading the role, which is the drift this document exists to "
            f"prevent"
        )
    assert "empty" in prose.lower(), (
        f"the section must state what {_REMOTE_AXIS} DEFAULTS to, and its default is "
        f"empty. A section naming an axis without its default leaves an operator unable to "
        f"tell whether declaring nothing provisions nothing or provisions something"
    )
    assert defaults[_REF_AXIS] in section, (
        f"the section must name what {_REF_AXIS} defaults to; the role defaults it to "
        f"{defaults[_REF_AXIS]!r}, which the section does not mention"
    )
    assert "never reset" in prose.lower(), (
        f"the section must say in those words that an existing checkout is NEVER RESET. "
        f"This is the fact an operator needs before running the play against a live "
        f"factory host, and it is the one claim the role's two guards exist to make "
        f"true;\nsection={section!r}"
    )


def test_the_gate_evaluator_refuses_an_unmodelled_name_and_an_unknown_form() -> None:
    """The evaluator's own contract — the control that keeps the arms above honest.

    Every arm above answers a question of the form "does this gate fire on this host".
    The two ways such an answer goes silently wrong are a name the scope never described
    (answered confidently about a different host) and a form the evaluator does not know
    (skipped, so the gate reads as firing unconditionally). Both must raise.
    """
    absent: Mapping[str, object] = {}
    assert _truth(condition=f"{_CLONE_REGISTER}.changed | default(false)", scope=absent) is False, (
        "with no record of a clone at all, the refusal's gate MUST read false — the "
        "preflight runs. Reading true would stand the refusal aside on the strength of a "
        "register that was never written"
    )
    assert _truth(condition=f"{_CLONE_REGISTER}.changed | default(true)", scope=absent) is True, (
        "the paired arm, proving the one above reads the role's own default rather than "
        "returning false for every absent name"
    )
    with pytest.raises(AssertionError, match="does not model"):
        _ = _truth(condition="fabro_server_a_fact_no_arm_describes", scope=absent)
    with pytest.raises(AssertionError, match="does not know"):
        _ = _truth(condition="fabro_server_host_checkout_remote is match('^http')", scope=absent)
