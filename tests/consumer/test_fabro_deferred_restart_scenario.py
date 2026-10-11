"""Consumer-tier: the deferred restart the `fabro_server` role carries ACROSS runs.

Work-item livespec-dev-tooling-vmeiv6. Measured on `hp-xubuntu` at master `ec0efd8b`:
an apply pass with `fabro_server_restart_allowed` false installed the v0.382 carrier at
the candidate instance's `binary_path` and changed its unit, and said out loud that the
instance was NOT restarted. The documented remedy — re-run with
`-e fabro_server_restart_allowed=true` — then restarted nothing, because the first run's
notification lived only in that run's handler queue. The candidate kept serving
`0.378.0-nightly.0` with 72 hours of uptime while its files on disk described a different
server. A refusal that cannot be redeemed is not a deferral; it is a silent drop.

WHY THESE ARMS READ THE ROLE RATHER THAN A HOST. The three assertions graded here are
claims about what a converge DOES — which handler a changed file reaches, which gate that
handler is behind, and what the role's document tells the operator. None of the three is
improved by reaching `hp-xubuntu`, and the first two could not be answered from a host at
all: "the marker was written" is a claim about every run with the flag false, not about
one. The assertions that genuinely need systemd — that a permitted run RESTARTS the
instance, that a running server executing a file other than its `binary_path` is treated
as needing one, and that restarting REMOVES the marker — are host-captured, and this file
deliberately does not claim them. What it does assert about those paths is structural: the
role spells them, and it spells them behind the carrying-runs refusal.

THE PRIOR ART IS THE SIBLING ROLE, AND IT IS WHY THE MARKER IS A FILE. `docker_sandbox_slice`
already solves this shape: a setting that takes effect only on a restart is recorded as a
host-side pending marker and applied by a later operator-selected run. This role's version
is PER INSTANCE, because a host runs several Fabro servers and a marker naming the host
would say nothing about which of them owes the restart.

THE CONDITION EVALUATOR IS DELIBERATELY TINY, AND ONE TEST KEEPS IT HONEST. Ansible and
Jinja are not importable here — `ansible-lint` and `ansible-playbook` resolve through
`uvx` against their own interpreter (see the justfile), because ansible-core 2.21 requires
a Python floor this repository does not carry. So `_truth` evaluates the exact predicate
vocabulary the role's restart gates use and nothing else, exactly as the sibling
`test_docker_sandbox_slice_scenario` reads and evaluates that role's own pending
condition. `test_the_restart_gates_stay_inside_the_vocabulary_this_test_can_evaluate`
fails the moment a gate grows a form the evaluator does not know, rather than letting a
gate go silently unevaluated — an unevaluated gate is a test that has stopped checking
whether a converge would restart a live factory.

WHAT IS DERIVED AND WHAT IS STATED. The event name, the handler names, the marker
variable, the marker directory and every gate predicate are READ out of the role, so a
role that gates differently fails here instead of being re-described. Only the
Definition of Done's own vocabulary — the flag name `fabro_server_restart_allowed` and
the two dispositions of it — is stated, because the Definition of Done states it.

CONTROL ARMS. Every positive arm is paired. The marker arm proves the gate REFUSES the
permitted run (a handler that wrote the marker on every run would make the marker mean
nothing) and that at least one file-changing task notifies the event, so a role whose
notify had been dropped cannot pass by having a well-gated handler nothing reaches.
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
_HANDLERS = _ROLE / "handlers" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

# The Definition of Done's own vocabulary, stated because it states it.
_RESTART_FLAG = "fabro_server_restart_allowed"
_MARKER_VARIABLE = "fabro_server_restart_pending_marker"
_MARKER_DIRECTORY_VARIABLE = "fabro_server_restart_pending_dir"

# Read out of the role, never restated: the event a changed file raises, and the five
# entries that decide what happens to this instance's restart. Naming them here rather
# than inline is what makes a rename fail LOUDLY in `_named` instead of quietly turning an
# arm into a no-op.
_FILES_CHANGED = "Fabro instance files changed"
_RECORD_HANDLER = "Record that this instance's restart is deferred"
_REPORT_HANDLER = "Say which instance was left needing a restart"
_RESTART_HANDLER = "Restart the Fabro instance"
_CLEAR_HANDLER = "Clear the restart-pending marker this restart satisfied"
_CARRY_TASK = "Claim a restart this instance carried over from an earlier run"
_DECIDE_TASK = "Decide whether this instance carries a restart into this run"
_MARKER_PROBE = "Look for a restart this instance deferred on an earlier run"
_DEFERRED_FACT = "fabro_server_restart_deferred"


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _tasks_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order.

    Text-sliced rather than YAML-parsed because no YAML library is importable in this
    suite (`[dependency-groups].dev` carries none, deliberately — the package is
    dependency-free). A task begins at a column-zero `- name:` line and ends at the next
    one, which is the shape every role file in this tree uses.
    """
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


def _named(*, name: str, source: Path) -> str:
    """One task or handler of the role, from its `- name:` to the next one."""
    matching = [body for task_name, body in _tasks_of(source=source) if task_name == name]
    assert len(matching) == 1, (
        f"{source.name} must carry exactly one entry named {name!r}; found {len(matching)}. "
        f"These arms read the role's own gates out of it rather than restating them, so a "
        f"missing or renamed entry is a test that has stopped checking anything"
    )
    return matching[0]


_ROLE_DEFAULT = re.compile(r"^(?P<name>fabro_server_[a-z_0-9]+): (?P<value>\S+)$", re.MULTILINE)


def _role_defaults() -> dict[str, str]:
    """Every scalar the role's `defaults/main.yml` declares."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
    }
    assert declared, "the role must declare its variables in defaults/main.yml"
    return declared


# A list field's body is its `- ` items AND the comment lines between them. Matching the
# comments is load-bearing rather than tidy: every gate in this role is commented
# BETWEEN its conditions, so a pattern accepting only `    - ` items stops at the first
# comment and reports the gate as having no conditions at all — and `all([])` is True, so
# such a gate reads as firing unconditionally. That is the one wrong answer that is wrong
# in BOTH directions at once, and it is why `_fires` refuses an empty list outright.
_LIST_FIELD = re.compile(r"^  (?P<field>[a-z_]+):\n(?P<items>(?:    (?:#|- ).*\n)+)", re.MULTILINE)
_SCALAR_FIELD = re.compile(r"^  (?P<field>[a-z_]+): (?P<value>[^\n>|].*)$", re.MULTILINE)
_LIST_ITEM = "- "


def _conditions(*, body: str, field: str) -> list[str]:
    """One task field as a list of conditions, whether it is spelled inline or as a list.

    `when:`, `changed_when:`, `listen:` and `notify:` all accept either shape, and Ansible
    ANDs a `when:` list. Reading both shapes here means the arms below do not silently stop
    evaluating a gate because its author moved it onto one line.
    """
    for match in _LIST_FIELD.finditer(body):
        if match["field"] == field:
            return [
                line.strip()[len(_LIST_ITEM) :].strip()
                for line in match["items"].splitlines()
                if line.strip().startswith(_LIST_ITEM)
            ]
    for match in _SCALAR_FIELD.finditer(body):
        if match["field"] == field:
            return [_unquote(value=match["value"])]
    return []


# --- the role's own restart gates, evaluated -------------------------------
#
# The vocabulary: a reference (optionally `| bool`, optionally `| default(true|false)`),
# an equality against a quoted literal, `not`, parentheses, and the two joiners. `or`
# binds looser than `and` in Jinja, so it is split first.

_REFERENCE = re.compile(
    r"(?P<name>[a-z_][a-z_0-9.]*)(?:\s*\|\s*bool)?"
    r"(?:\s*\|\s*default\((?P<fallback>true|false)\))?(?:\s*\|\s*bool)?"
)
_COMPARISON = re.compile(
    r"(?P<name>[a-z_][a-z_0-9.]*)\s*(?P<operator>==|!=)\s*'(?P<literal>[^']*)'"
)


def _split_top_level(*, text: str, joiner: str) -> list[str]:
    """`text` split on `joiner`, ignoring occurrences inside parentheses."""
    parts: list[str] = []
    depth = 0
    start = 0
    position = 0
    while position < len(text):
        character = text[position]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0 and text.startswith(joiner, position):
            parts.append(text[start:position])
            position += len(joiner)
            start = position
            continue
        position += 1
    parts.append(text[start:])
    return parts


def _value(*, name: str, fallback: str | None, scope: Mapping[str, object]) -> object:
    """One name the role's gate reads, resolved against a MODELLED host state.

    An unmodelled name asserts rather than defaulting: a gate evaluated against a value
    this test invented is a gate evaluated against a different condition, which is worse
    than one left unevaluated because it answers confidently.
    """
    if name in scope:
        return scope[name]
    assert fallback is not None, (
        f"the role's restart gate reads {name!r}, which this test does not model and the "
        f"role does not default. Model it rather than letting the arms below answer about a "
        f"host state that was never described"
    )
    return fallback == "true"


def _truth(*, condition: str, scope: Mapping[str, object]) -> bool:
    """One gate condition of the role, evaluated against one modelled host state."""
    text = condition.strip()
    for joiner, combine in ((" or ", any), (" and ", all)):
        parts = _split_top_level(text=text, joiner=joiner)
        if len(parts) > 1:
            return combine(_truth(condition=part, scope=scope) for part in parts)
    if text.startswith("not "):
        return not _truth(condition=text[len("not ") :], scope=scope)
    if text.startswith("(") and text.endswith(")"):
        return _truth(condition=text[1:-1], scope=scope)
    comparison = _COMPARISON.fullmatch(text)
    if comparison is not None:
        matches = (
            _value(name=comparison["name"], fallback=None, scope=scope) == (comparison["literal"])
        )
        return matches is (comparison["operator"] == "==")
    reference = _REFERENCE.fullmatch(text)
    assert reference is not None, (
        f"the role's restart gate carries {text!r}, a form this evaluator does not know. "
        f"Teach it the new form rather than leaving the gate unevaluated: an unevaluated "
        f"gate is a test that has stopped checking whether a converge restarts a factory"
    )
    return bool(_value(name=reference["name"], fallback=reference["fallback"], scope=scope))


def _fires(*, body: str, field: str, scope: Mapping[str, object]) -> bool:
    """Whether every condition of `body`'s `field` holds — Ansible ANDs a list.

    An EMPTY list asserts rather than returning True. Ansible's own reading of a missing
    `when:` is "always", so returning True would be faithful to Ansible and useless here:
    every arm below asks whether a gate fires on one host state and not another, and a gate
    this reader could not see answers both questions the same way while looking exactly
    like a gate that passed. Refusing the empty list is what turned a silently-vacuous
    reader into a visible failure once already, during this work-item's first Green.
    """
    conditions = _conditions(body=body, field=field)
    assert conditions, (
        f"this arm asks whether the {field!r} gate fires, and the entry carries none this "
        f"reader can see. Either the gate is genuinely absent — in which case the role "
        f"restarts or records unconditionally — or it is spelled in a shape "
        f"`_conditions` does not read, which is a test that has stopped checking;\n"
        f"body={body!r}"
    )
    return all(_truth(condition=condition, scope=scope) for condition in conditions)


def _host_state(
    *,
    restart_allowed: bool,
    deferred: bool = False,
    stale: bool = False,
    restarted: bool = False,
) -> dict[str, object]:
    """A running, already-installed instance, with the restart flag as given.

    The two values that are neither the flag nor a named argument are pinned to the
    uninteresting case on purpose: the instance is `running` (a parked instance has no
    server to restart and is a separate disposition) and its unit file is already on disk
    under a real apply, which is what the role's check-mode guard reads.

    `deferred` is an earlier run's marker still on the host; `stale` is a running server
    executing a file other than its `binary_path`; `restarted` is this run having actually
    performed the restart. The defaults describe a CONVERGED instance — no marker, the
    right binary, nothing restarted — which is the control every arm below needs, because
    the expensive mistake in this mechanism is not failing to restart but restarting a live
    factory on a run where nothing was owed.
    """
    return {
        _RESTART_FLAG: restart_allowed,
        "fabro_server_service_state": "running",
        "ansible_check_mode": False,
        "fabro_server_unit_file.stat.exists": True,
        "fabro_server_restart_deferred": deferred,
        "fabro_server_binary_stale": stale,
        "fabro_server_restart_applied.changed": restarted,
    }


def _every_entry() -> list[tuple[str, str]]:
    """Every entry the role can run — its tasks AND its handlers.

    Handlers are included because a handler that deletes the marker is a path to losing
    the deferral exactly as a task is, and the arms below ask whether ANY path does so on
    a run that did not restart.
    """
    return [*_tasks_of(source=_TASKS), *_tasks_of(source=_HANDLERS)]


def _marker_clearing_entries() -> list[tuple[str, str]]:
    """Every entry that removes this instance's restart-pending marker."""
    return [
        (name, body)
        for name, body in _every_entry()
        if f"{{{{ {_MARKER_VARIABLE} }}}}" in body and "state: absent" in body
    ]


# --- the assertions --------------------------------------------------------


def test_a_run_that_may_not_restart_records_the_instances_pending_restart() -> None:
    """The first assertion: files changed under the flag false leave a marker behind."""
    notifying = [
        name
        for name, body in _tasks_of(source=_TASKS)
        if _FILES_CHANGED in _conditions(body=body, field="notify")
    ]
    assert notifying, (
        f"at least one task MUST notify {_FILES_CHANGED!r}: that event is how a changed "
        f"unit, drop-in, settings file or binary reaches the restart path at all, and a "
        f"well-gated handler nothing notifies records nothing"
    )
    handler = _named(name=_RECORD_HANDLER, source=_HANDLERS)
    assert _conditions(body=handler, field="listen") == [_FILES_CHANGED], (
        f"the handler that records the deferred restart MUST listen to {_FILES_CHANGED!r}, "
        f"the event those {len(notifying)} task(s) raise; a handler on any other event is "
        f"one a changed file never reaches"
    )
    assert _fires(body=handler, field="when", scope=_host_state(restart_allowed=False)), (
        f"a run with {_RESTART_FLAG} false MUST record the restart it refused to perform. "
        f"Without the record the refusal is a silent drop: the operator is told to re-run "
        f"with the flag true, and that re-run has nothing to act on because the first run's "
        f"notification never outlived its handler queue;\nwhen={_conditions(body=handler, field='when')}"
    )
    assert not _fires(body=handler, field="when", scope=_host_state(restart_allowed=True)), (
        f"the control arm: a run with {_RESTART_FLAG} true performs the restart, so it MUST "
        f"NOT also record one as pending. A marker written on every run is a marker that "
        f"means nothing by the second one"
    )
    marker = _role_defaults()[_MARKER_DIRECTORY_VARIABLE]
    assert f"{{{{ {_MARKER_VARIABLE} }}}}" in handler, (
        f"the record MUST be written at {_MARKER_VARIABLE}, a durable file on the host "
        f"under {marker}: a message in a play recap is gone the moment the terminal "
        f"scrolls, and the next run is where the deferral has to be readable;\n"
        f"handler={handler!r}"
    )


def test_a_refused_rerun_keeps_the_marker_and_reports_the_restart_still_pending() -> None:
    """The second assertion: the deferral survives every run that does not apply it."""
    claim = _named(name=_CARRY_TASK, source=_TASKS)
    assert _conditions(body=claim, field="notify") == [_FILES_CHANGED], (
        f"the carried-over claim MUST notify {_FILES_CHANGED!r}. This is the whole mechanism: "
        f"on a run where nothing on disk changed, NO task notifies, so the handler group is "
        f"never reached and the standing deferral is neither applied nor reported. A marker "
        f"nothing reads is a marker that may as well not exist"
    )
    assert _fires(
        body=claim, field="changed_when", scope=_host_state(restart_allowed=False, deferred=True)
    ), (
        f"an earlier run's marker MUST raise {_FILES_CHANGED!r} on this run even though this "
        f"run changed nothing; that is what carries the deferral ACROSS runs rather than "
        f"losing it with the handler queue that recorded it"
    )
    assert not _fires(body=claim, field="changed_when", scope=_host_state(restart_allowed=True)), (
        "the control arm, and the expensive one: on a CONVERGED instance — no marker, the "
        "running server already executing its binary_path — the claim MUST NOT fire. A claim "
        "that fired unconditionally would notify the restart handler on every run, so a run "
        "with the flag true would restart a live factory that owed nothing"
    )
    report = _named(name=_REPORT_HANDLER, source=_HANDLERS)
    assert _fires(
        body=report, field="when", scope=_host_state(restart_allowed=False, deferred=True)
    ), (
        f"a run with {_RESTART_FLAG} false MUST say the restart is still pending;\n"
        f"when={_conditions(body=report, field='when')}"
    )
    assert _MARKER_VARIABLE in report, (
        f"the report MUST name {_MARKER_VARIABLE} so the operator reading the recap learns "
        f"WHERE the deferral is recorded; a message that says a restart is owed without "
        f"saying what holds that fact leaves the next run's behaviour unexplained;\n"
        f"handler={report!r}"
    )
    clearing = _marker_clearing_entries()
    assert clearing, (
        "the control arm: at least one entry MUST remove the marker. A role with no path "
        "that clears it would satisfy 'a refused run keeps the marker' trivially, and would "
        "leave every instance permanently owing a restart it had already had"
    )
    for name, body in clearing:
        assert not _fires(
            body=body, field="when", scope=_host_state(restart_allowed=False, deferred=True)
        ), (
            f"{name!r} removes the marker on a run with {_RESTART_FLAG} false. That run "
            f"restarted nothing, so deleting the record DROPS the deferral silently — the "
            f"exact failure this work-item exists to fix, reintroduced one layer down;\n"
            f"when={_conditions(body=body, field='when')}"
        )
    recorded = _named(name=_RECORD_HANDLER, source=_HANDLERS)
    for varying in ("ansible_date_time", "now(", "lookup("):
        assert varying not in recorded, (
            f"the marker's content carries {varying!r}, so its bytes differ between two "
            f"refused runs. Ansible would then report the marker as CHANGED on every "
            f"converge, which is the opposite of 'keeps an existing marker': a standing "
            f"deferral would read as a fresh event each run and mean nothing by the third"
        )
    derivation = _named(name=_DECIDE_TASK, source=_TASKS)
    assert f"{_DEFERRED_FACT}:" in derivation and "stat.exists" in derivation, (
        f"the role MUST derive {_DEFERRED_FACT} from a stat of the marker file itself. The "
        f"arms above model that fact directly, so they are only evaluating the real host "
        f"condition while the role reads it from the marker's own existence;\n"
        f"task={derivation!r}"
    )
    stat_of_marker = _named(name=_MARKER_PROBE, source=_TASKS)
    assert f"{{{{ {_MARKER_VARIABLE} }}}}" in stat_of_marker, (
        f"the probe feeding {_DEFERRED_FACT} MUST stat {_MARKER_VARIABLE}, not some other "
        f"path: a deferral read from the wrong file is a gate evaluated against a host "
        f"state nobody wrote;\ntask={stat_of_marker!r}"
    )


def test_the_restart_gates_stay_inside_the_vocabulary_this_test_can_evaluate() -> None:
    """The control on the evaluator: every gate the arms read must actually be evaluated."""
    scope = _host_state(restart_allowed=False, deferred=True, stale=True, restarted=True)
    gated = (
        (_TASKS, _CARRY_TASK, "changed_when"),
        (_HANDLERS, _RESTART_HANDLER, "when"),
        (_HANDLERS, _RECORD_HANDLER, "when"),
        (_HANDLERS, _REPORT_HANDLER, "when"),
        (_HANDLERS, _CLEAR_HANDLER, "when"),
    )
    for source, name, field in gated:
        body = _named(name=name, source=source)
        conditions = _conditions(body=body, field=field)
        assert conditions, (
            f"{name!r} must carry a {field!r} this reader can see; an unread gate reads as "
            f"firing unconditionally, which for a restart means killing a live factory"
        )
        for condition in conditions:
            _truth(condition=condition, scope=scope)
    assert _REFERENCE.fullmatch("fabro_server_restart_applied.changed | default(false)"), (
        "the evaluator's own control: the dotted-register-with-default form the clear "
        "handler uses must be one it parses, or the arm above passes by not parsing it"
    )
