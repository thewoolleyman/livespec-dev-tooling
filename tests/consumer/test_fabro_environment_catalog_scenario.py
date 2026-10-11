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
_ENVIRONMENT_TASKS = _ROLE / "tasks" / "environment.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"

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
_API_TASK = "Resolve this instance's environments API"
_CATALOG_INCLUDE = "Create or update each sandbox environment this instance declares"
_CATALOG_READ = "Read what this instance's catalog holds for this environment"
_CURRENT_TASK = "Resolve what the catalog currently holds for this environment"
_TEMPLATE_READ = "Read the catalog entry a new environment is derived from"
_BASE_TASK = "Resolve the catalog entry this environment's unnamed fields come from"
_SETTINGS_TASK = "Resolve the settings this environment is written with"
_CREATE_TASK = "Create this environment in the instance's catalog"
_API_URL_FACT = "fabro_server_environments_url"
_PRESENT_FACT = "fabro_server_environment_present"
_SETTINGS_FACT = "fabro_server_environment_settings"
_ENVIRONMENT_LOOP_VAR = "fabro_server_environment"

# The API this slice writes through, and the one environment variable the instance's
# own `server.env` carries the credential under. Both are the Definition of Done's
# words rather than the role's, which is why they are stated here.
_API_PATH = "/api/v1/environments"
_TOKEN_NAME = "FABRO_DEV_TOKEN"
_SERVER_ENV = "storage/server.env"


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

    An ABSENT file asserts rather than raising. A reader that died on the open would fail
    with a `FileNotFoundError` from deep inside `pathlib`, which says that a path is
    missing and nothing about which claim went unproved; the assertion says what the file
    is for.
    """
    assert source.is_file(), (
        f"the role MUST carry {source.name}: every claim this module makes about what a "
        f"converge does to an instance's catalog is read out of that file, so its absence "
        f"is the catalog work not existing at all"
    )
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
# One mapping entry of a `set_fact` or an `environment` block, inline or folded. The
# folded continuation sits deeper than the key, which is what ends one entry and begins
# the next without a YAML parser.
_SET_FACT_KEY = re.compile(r"^ {4}(?P<fact>[A-Za-z_][A-Za-z_0-9]*): (?P<value>.*)$")
_FOLDED_LINE = re.compile(r"^ {6,}(?P<text>\S.*)$")
# The YAML block indicators a folded value opens with. They are syntax, not part of
# the expression the role evaluates, so the reader drops them.
_BLOCK_SCALARS = frozenset({">", ">-", "|", "|-"})


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


def _set_facts(*, name: str, source: Path) -> dict[str, str]:
    """Each fact one `set_fact` task sets, and the expression it sets it to.

    Folded (`>-`) as well as inline, because every expression in this slice that is
    worth reading is long enough that its author folded it. The value is normalised to
    one line, which is what Jinja sees: a folded scalar's newlines are spaces, and the
    block indicator itself is YAML syntax rather than part of the expression.
    """
    body = _named(name=name, source=source)
    facts: dict[str, str] = {}
    key: str | None = None
    for line in body.splitlines():
        entry = _SET_FACT_KEY.match(line)
        if entry is not None:
            key = entry["fact"]
            inline = entry["value"].strip()
            facts[key] = "" if inline in _BLOCK_SCALARS else _unquote(value=inline)
            continue
        folded = _FOLDED_LINE.match(line)
        if folded is not None and key is not None:
            facts[key] = f"{facts[key]} {folded['text']}".strip()
            continue
        key = None
    assert facts, (
        f"{name!r} must set at least one fact this reader can see; a set_fact whose "
        f"entries it cannot read is a derivation nothing here checks"
    )
    return facts


def _api_calls() -> dict[str, str]:
    """Every task of the role that runs a shell command, by name, with its command text.

    `shell` rather than `command` is how this role reaches the environments API at all:
    the token has to be read out of the instance's own `server.env` ON THE HOST and
    piped into curl, which needs a pipe. So "every shell task" is the honest population
    for the credential arms below — they are claims about all of them, not about the
    three this slice happens to add.
    """
    return {
        name: body
        for source in (_TASKS, _ENVIRONMENT_TASKS, _HANDLERS)
        for name, body in _tasks_of(source=source)
        if "ansible.builtin.shell:" in body
    }


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


# --- writing a declared environment through the instance's own API ---------


def test_each_declared_environment_is_written_through_this_instances_environments_api() -> None:
    """The second assertion, create half: one request per declared environment, to its own server."""
    url = _set_facts(name=_API_TASK, source=_TASKS).get(_API_URL_FACT)
    assert url is not None, (
        f"the role MUST resolve {_API_URL_FACT}: the catalog of a two-instance host belongs "
        f"to ONE of its servers, and a request sent to whichever server the CLI's default "
        f"target names would write the wrong instance's catalog;\nresolved={_API_TASK!r}"
    )
    assert url == f"http://127.0.0.1:{{{{ fabro_server_port }}}}{_API_PATH}", (
        f"the API MUST be {_API_PATH} on THIS instance's own loopback port, which is the "
        f"only address that identifies one server of a host that runs several; the role "
        f"resolves {url!r}"
    )
    include = _named(name=_CATALOG_INCLUDE, source=_TASKS)
    assert _conditions(body=include, field="loop") == [f"{{{{ {_ENVIRONMENTS_FACT} }}}}"], (
        f"the catalog work MUST be included once per DECLARED environment, looping over "
        f"{_ENVIRONMENTS_FACT}. An instance declaring none then reaches its server not at "
        f"all, which is what makes the axis safe to add to five live instances;\n"
        f"loop={_conditions(body=include, field='loop')}"
    )
    assert f"loop_var: {_ENVIRONMENT_LOOP_VAR}" in include, (
        f"the loop MUST name its variable {_ENVIRONMENT_LOOP_VAR}, not Ansible's `item`: "
        f"the included file is read by an operator who cannot see this loop, and `item` in "
        f"a nested include is the classic way one loop's value is read as another's"
    )
    read = _named(name=_CATALOG_READ, source=_ENVIRONMENT_TASKS)
    assert f"{{{{ {_API_URL_FACT} }}}}/{{{{ {_ENVIRONMENT_LOOP_VAR}.id }}}}" in read, (
        f"the catalog read MUST GET {_API_PATH}/<id> — the per-environment endpoint — so "
        f"that 404 answers 'this environment does not exist yet' for THIS id rather than "
        f"being inferred from a list;\ntask={read!r}"
    )
    assert _conditions(body=read, field="changed_when") == ["false"], (
        "the read MUST be changed_when false. A read that reported itself changed would "
        "make every converge of a converged host report drift it does not have"
    )
    assert _conditions(body=read, field="check_mode") == ["false"], (
        "the read MUST run under `--check` too: this repository's rule is that a drift "
        "report which skipped its own probes would report on a catalog it never inspected"
    )
    create = _named(name=_CREATE_TASK, source=_ENVIRONMENT_TASKS)
    assert "--request POST" in create and f"{{{{ {_API_URL_FACT} }}}}" in create, (
        f"creating an absent environment MUST POST to {_API_PATH} itself — the collection "
        f"endpoint, which is the only one that accepts an id;\ntask={create!r}"
    )
    assert f"{_SETTINGS_FACT}\n" in create or f"{_SETTINGS_FACT} " in create, (
        f"the POST body MUST be built from {_SETTINGS_FACT}, the settings the role derived "
        f"for this environment; a body spelled inline in the request would be a second "
        f"place the declared values live"
    )
    assert _conditions(body=create, field="changed_when") == ["true"], (
        "creating an environment that was not in the catalog IS a change, and must say so: "
        "a shell task reports nothing by itself, so a converge that created the factory's "
        "environment would otherwise be indistinguishable from one that found it already "
        "there"
    )
    assert _conditions(body=create, field="when") == [f"not ({_PRESENT_FACT} | bool)"], (
        f"the create MUST be gated on the environment being ABSENT from the catalog. "
        f"POSTing an id the catalog already holds is a 409, so an ungated create turns "
        f"every second converge into a failed run;\nwhen={_conditions(body=create, field='when')}"
    )


def test_the_request_body_is_derived_from_the_catalog_rather_than_spelled_in_the_role() -> None:
    """The control on the body: the role overrides the declared fields and invents nothing."""
    current = _set_facts(name=_CURRENT_TASK, source=_ENVIRONMENT_TASKS)
    assert _PRESENT_FACT in current, (
        f"the role MUST derive {_PRESENT_FACT} from the catalog read itself. Every gate "
        f"below reads that fact, so a fact derived from anything else is a gate answering "
        f"about a catalog nobody looked at;\nderived={sorted(current)}"
    )
    assert "stdout_lines" in current[_PRESENT_FACT] and "200" in current[_PRESENT_FACT], (
        f"{_PRESENT_FACT} MUST come from the status line of the catalog read's own output; "
        f"the role derives it from {current[_PRESENT_FACT]!r}"
    )
    base = _set_facts(name=_BASE_TASK, source=_ENVIRONMENT_TASKS)
    settings = _set_facts(name=_SETTINGS_TASK, source=_ENVIRONMENT_TASKS)
    assert _SETTINGS_FACT in settings, f"the role must derive {_SETTINGS_FACT}"
    expression = settings[_SETTINGS_FACT]
    base_fact = next(iter(base))
    assert expression.startswith(f"{{{{ {base_fact}"), (
        f"{_SETTINGS_FACT} MUST be built BY OVERRIDING the catalog entry the role read, "
        f"not assembled from role-side constants. A create or replace request requires "
        f"every field the server's build knows and refuses any field it does not, and this "
        f"repository cannot know which fields a given factory host's Fabro build has — the "
        f"candidate instance exists precisely to run a DIFFERENT build from its sibling. A "
        f"body carried from the server's own answer is the one shape that cannot be wrong "
        f"about its schema, and it also means a converge never resets a field version "
        f"control does not declare;\nexpression={expression!r}"
    )
    for field in ("image", "resources"):
        assert f"'{field}'" in expression, (
            f"the derived settings MUST override {field!r} — the two sub-objects the "
            f"declared image, cpu and memory live in;\nexpression={expression!r}"
        )
    for response_only in ("id", "revision"):
        assert f"- {response_only}\n" in _named(name=_SETTINGS_TASK, source=_ENVIRONMENT_TASKS), (
            f"{response_only!r} MUST be dropped from the derived settings. The API carries "
            f"both OUTSIDE the settings — the id in the create body and the path, the "
            f"revision in the If-Match header — and refuses a request body that repeats "
            f"them, so carrying the catalog entry verbatim would be refused"
        )


def test_the_api_credential_is_read_on_the_host_and_never_enters_ansibles_own_variables() -> None:
    """The second assertion, credential half: the token is used without being logged."""
    calls = _api_calls()
    assert calls, (
        "the role MUST reach the environments API through a host-side shell: the credential "
        "lives in a 0600 file on the factory host, and the whole point of this shape is "
        "that it is read there rather than slurped back to the controller"
    )
    reading = {name: body for name, body in calls.items() if _TOKEN_NAME in body}
    assert reading, (
        f"at least one of those tasks MUST read {_TOKEN_NAME}; the environments API "
        f"authenticates with it and nothing else the role holds"
    )
    for name, body in sorted(reading.items()):
        assert _SERVER_ENV in body, (
            f"{name!r} must read the token out of the instance's own {_SERVER_ENV}. That "
            f"file is where Fabro generates it, is mode 0600, and is per instance — a "
            f"token taken from anywhere else would authenticate against a different server "
            f"or not at all"
        )
        assert "--header @-" in body, (
            f"{name!r} MUST hand curl the Authorization header on STDIN (`--header @-`). "
            f"Spelled as an argument the token would sit in the host's process table for "
            f"the life of the request, readable by anything that can run `ps`; on stdin it "
            f"never appears in an argv at all;\ntask={body!r}"
        )
    for source in (_TASKS, _ENVIRONMENT_TASKS, _HANDLERS):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if _TOKEN_NAME not in line:
                continue
            assert "{{" not in line, (
                f"{source.name}:{number} resolves {_TOKEN_NAME} through a Jinja expression: "
                f"{line!r}. That is the one shape this assertion forbids — a templated "
                f"token is a VALUE in Ansible's variable space, which means it reaches the "
                f"play's own diagnostics, `-v` output, the module invocation record and any "
                f"message that interpolates the variable. Read it in the host-side shell "
                f"instead, where Ansible never sees it"
            )
