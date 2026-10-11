"""Consumer-tier: the sandbox environment CATALOG a `fabro_server` instance declares.

Work-item livespec-dev-tooling-fe62lh, the execution mirror of
livespec-orchestrator-beads-fabro `bd-ib-sxcnj7` (plan fabro-currency). Measured
2026-10-11: the hp-candidate canary run on `fabro-server-candidate` (v0.382.0-nightly.0)
passed its start node and failed at run preparation with `mise: not found`, because the
run was placed in the server's seeded `default` environment — `buildpack-deps:noble`,
2 CPU, 4GB — and the factory's `livespec-ci` environment does not exist in that server's
catalog at all.

WHY A CATALOG IS AN API CALL AND NOT A FILE. On this engine a sandbox environment is
SERVER-MANAGED state: it lives in the instance's own SQLite store, is written through
`POST /api/v1/environments` and `PUT /api/v1/environments/{id}`, and a `workflow.toml`
`[environments.*]` table is never selected. So the axis this slice adds cannot be
expressed as a rendered file the way `settings.toml` and the unit are; the only way
version control reaches the catalog is a request the converge makes, authenticated with
the `FABRO_DEV_TOKEN` the instance's `server.env` already carries.

WHAT IS DERIVED AND WHAT IS STATED. The axis name, the fields a declaration must spell,
the fact the role resolves them into, the task names and every gate predicate are READ
out of the role, so a role that resolves or gates differently fails here instead of being
re-described. Only the Definition of Done's own values are stated — the four field names,
the candidate's environment id, its image, its cpu and its memory — because a test that
derived those from the file it is checking would assert nothing.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_server"
_TASKS = _ROLE / "tasks" / "main.yml"

# The Definition of Done's own vocabulary, stated because it states it: the axis an
# instance mapping gains, and the four fields each declared environment spells.
_AXIS = "environments"
_FIELDS = ("id", "image", "cpu", "memory")

# Read out of the role, never restated. Naming the handles here is what makes a rename
# fail LOUDLY in `_named` instead of quietly turning an arm below into a no-op.
_RESOLVE_TASK = "Resolve this instance's axes"
_MAPPING_REFUSAL = "Refuse an instance mapping that does not spell every axis"
_DECLARATION_REFUSAL = "Refuse an environment declaration that does not spell every field"
_DUPLICATE_REFUSAL = "Refuse two declared environments that share an id"
# The role's FIRST write to the host. Both refusals above have to precede it, because a
# refusal that fires after a write has already left the host changed.
_FIRST_WRITE = "Create the shared libexec directory"
_ENVIRONMENTS_FACT = "fabro_server_environments"


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _tasks_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order.

    Text-sliced rather than YAML-parsed because no YAML library is importable in this
    suite — `[dependency-groups].dev` carries none, deliberately, since the package
    itself is dependency-free. A task begins at a column-zero `- name:` line and ends at
    the next one, which is the shape every role file in this tree uses.
    """
    text = source.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{source.name} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a catalog write "
        f"nothing here checks"
    )
    parsed: list[tuple[str, str]] = []
    for start, stop in pairwise([*openings, len(text)]):
        body = text[start:stop]
        parsed.append((body.split("\n", 1)[0][len("- name: ") :].strip(), body))
    return parsed


def _named(*, name: str, source: Path) -> str:
    """One task of a role file, from its `- name:` to the next one."""
    matching = [body for task_name, body in _tasks_of(source=source) if task_name == name]
    assert len(matching) == 1, (
        f"{source.name} must carry exactly one task named {name!r}; found {len(matching)}. "
        f"These arms read the role's own refusals and gates out of it rather than restating "
        f"them, so a missing or renamed task is a test that has stopped checking anything"
    )
    return matching[0]


def _task_index(*, name: str, source: Path) -> int:
    """Where one task sits in a role file, counted in tasks.

    Order is load-bearing rather than cosmetic for a refusal: "refuses before the host is
    changed" is a statement about where a task sits relative to another, and nothing else
    in the role expresses it.
    """
    names = [task_name for task_name, _ in _tasks_of(source=source)]
    assert name in names, f"{source.name} must still carry the task {name!r}"
    return names.index(name)


# One `set_fact` entry of the role's own resolution task: the fact and its expression.
_SET_FACT_ENTRY = re.compile(
    r'^ {4}(?P<fact>fabro_server_[a-z_0-9]+): "(?P<expression>\{\{ .+ \}\})"$', re.MULTILINE
)
# A role variable's expression when the instance does not name the axis.
_INSTANCE_EXPRESSION = re.compile(
    r"^\{\{ fabro_server_instance\.(?P<key>[a-z_0-9]+)"
    r"(?: \| default\((?P<fallback>.+)\))? \}\}$"
)
# A bare list item of a task's `that:` or `vars:` block — an identifier and nothing else,
# so a `that:` condition (which always carries an operator or a filter) cannot match.
_BARE_ITEM = re.compile(r"^ {6}- (?P<item>[a-z_]+)$", re.MULTILINE)
_LIST_FIELD = re.compile(r"^  (?P<field>[a-z_]+):\n(?P<items>(?:    (?:#|- ).*\n)+)", re.MULTILINE)
_SCALAR_FIELD = re.compile(r"^  (?P<field>[a-z_]+): (?P<value>[^\n>|].*)$", re.MULTILINE)
_LIST_ITEM = "- "


def _conditions(*, body: str, field: str) -> list[str]:
    """One task field as a list of conditions, whether it is spelled inline or as a list.

    `when:` and `changed_when:` both accept either shape and Ansible ANDs a `when:` list,
    so reading both here means an arm does not silently stop evaluating a gate because its
    author moved it onto one line. Comment lines BETWEEN a list's items are matched on
    purpose: every gate in this role is commented between its conditions, and a pattern
    accepting only `    - ` items would stop at the first comment and report the gate as
    carrying no conditions at all.
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


def _resolution_expressions() -> dict[str, str]:
    """Each fact the role's own axis-resolution task sets, and the expression it sets it to."""
    expressions = {
        match["fact"]: match["expression"]
        for match in _SET_FACT_ENTRY.finditer(_named(name=_RESOLVE_TASK, source=_TASKS))
    }
    assert expressions, "the role must resolve this instance's axes with set_fact"
    return expressions


def _bare_items(*, body: str) -> frozenset[str]:
    """Every bare identifier listed in one task's own blocks."""
    return frozenset(match["item"] for match in _BARE_ITEM.finditer(body))


# --- the axis an instance mapping gains ------------------------------------


def test_an_instance_mapping_accepts_an_optional_catalog_of_declared_environments() -> None:
    """The first assertion: the axis exists, it is optional, and each entry spells four fields."""
    expressions = _resolution_expressions()
    assert _ENVIRONMENTS_FACT in expressions, (
        f"the role MUST resolve {_ENVIRONMENTS_FACT} alongside the instance's other axes; "
        f"without it nothing in the role can read what a mapping declares;\n"
        f"resolved={sorted(expressions)}"
    )
    match = _INSTANCE_EXPRESSION.match(expressions[_ENVIRONMENTS_FACT])
    assert match is not None, (
        f"{_ENVIRONMENTS_FACT} must resolve from the instance mapping itself, as "
        f"`fabro_server_instance.<axis>` with a default; the role resolves it from "
        f"{expressions[_ENVIRONMENTS_FACT]!r}, which is a value this arm cannot hold "
        f"against the mapping it is supposed to come from"
    )
    assert match["key"] == _AXIS, (
        f"the axis an instance mapping declares MUST be named {_AXIS!r} — the Definition of "
        f"Done's own word, and the one HOST_VARS.md documents; the role reads "
        f"{match['key']!r}"
    )
    assert match["fallback"] == "[]", (
        f"{_AXIS} MUST be OPTIONAL and MUST default to the EMPTY LIST. Every instance on "
        f"both factory hosts predates this axis, and an empty catalog is the only default "
        f"that leaves those instances declaring nothing rather than declaring something "
        f"the role would then write; the role defaults it to {match['fallback']!r}"
    )
    required = _bare_items(body=_named(name=_MAPPING_REFUSAL, source=_TASKS))
    assert required, "the role must still enumerate the keys every instance mapping must spell"
    assert _AXIS not in required, (
        f"{_AXIS} MUST NOT join the keys the role refuses a mapping for. A required axis "
        f"would make every instance on both hosts — the fleet factories included — fail the "
        f"role's own preflight until each declared a catalog it has never needed;\n"
        f"required={sorted(required)}"
    )
    declaration = _named(name=_DECLARATION_REFUSAL, source=_TASKS)
    assert _bare_items(body=declaration) == frozenset(_FIELDS), (
        f"the role MUST refuse a declaration that does not spell exactly {sorted(_FIELDS)}: "
        f"an id to write it under, a docker image to run, a cpu count and a memory size. A "
        f"declaration missing one reaches the environments API as a body the server refuses, "
        f"which is a 422 mid-converge instead of a refusal before anything is read;\n"
        f"enumerated={sorted(_bare_items(body=declaration))}"
    )
    assert _conditions(body=declaration, field="loop") == [f"{{{{ {_ENVIRONMENTS_FACT} }}}}"], (
        f"the refusal MUST loop over {_ENVIRONMENTS_FACT} so EVERY declared environment is "
        f"judged. A refusal that read only the first entry would pass a list whose second "
        f"entry is the malformed one;\nloop={_conditions(body=declaration, field='loop')}"
    )
    assert _conditions(body=declaration, field="notify") == [], (
        "the refusal MUST notify nothing. Every notify in this role reaches the "
        "files-changed event, and that event's handlers restart a live factory; a refusal "
        "is a read of version control's own words and changes nothing a server is serving"
    )
    duplicates = _named(name=_DUPLICATE_REFUSAL, source=_TASKS)
    assert _conditions(body=duplicates, field="when") == [f"{_ENVIRONMENTS_FACT} | length > 1"], (
        f"the id refusal MUST be gated on there being more than one declaration — a single "
        f"entry cannot collide with itself, and the gate is what keeps the common case "
        f"silent;\nwhen={_conditions(body=duplicates, field='when')}"
    )
    assert _AXIS in duplicates and "unique" in duplicates, (
        f"the role MUST also refuse two declared environments that share an id: the catalog "
        f"is keyed by id, so two entries with one id are two declarations of which only the "
        f"last would survive — silently, because each write succeeds;\ntask={duplicates!r}"
    )
    first_write = _task_index(name=_FIRST_WRITE, source=_TASKS)
    for refusal in (_DECLARATION_REFUSAL, _DUPLICATE_REFUSAL):
        assert _task_index(name=refusal, source=_TASKS) < first_write, (
            f"{refusal!r} MUST run before {_FIRST_WRITE!r}, the role's first write to the "
            f"host. Every refusal in this role is a preflight rather than a mid-run failure "
            f"because this service is the orchestrator's own server: a run that refuses after "
            f"writing has already changed a host it then declined to converge"
        )
