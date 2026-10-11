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

THESE ARMS READ TEXT, AND THE ROLE WAS CONTROLLED AGAINST REAL JINJA BY MEASUREMENT.
Ansible and Jinja are not importable in this suite — `ansible-lint` and
`ansible-playbook` resolve through `uvx` against their own interpreter (see the
justfile), because ansible-core 2.21 requires a Python floor this repository does not
carry — so every arm below reads the role as TEXT and evaluates only the tiny gate
vocabulary `_truth` understands. On 2026-10-11, before this slice was committed, the
committed `tasks/environment.yml` was walked through ansible-core 2.21.4's OWN filter
and test plugins for three modelled catalog answers: the declared environment absent
(404), present and already matching, and present carrying the seeded `default` entry's
settings. Every `set_fact`, every `assert` condition, every `when` and every `debug`
message was rendered in file order. The results:

- the POST body came out carrying `id`, `provider`, `image`, `resources`, `network`,
  `lifecycle`, `labels`, `volumes` and `env` — exactly Fabro's
  `CreateEnvironmentRequest` — with the declared image and envelope overridden and the
  base entry's `env` map carried through untouched; the PUT body was the same minus
  `id` and `revision`, which is `ReplaceEnvironmentRequest`;
- the match decision read False / True / False for the three answers, and on the
  matching one BOTH writes were skipped;
- the replace carried `If-Match` with the revision that run's own read returned.

That walk also FOUND TWO DEFECTS no text-reading arm could have seen, and each is now an
arm of its own: `items2dict` refusing the generator `rejectattr` hands it — which made
the whole derivation unevaluable, while `--syntax-check` passed it — and the disposition
report sitting after the writes it narrates. The walk is not reproduced in the suite; it
needs a network-resolved second interpreter, which no test may depend on. It is recorded
here as the evidence behind the claims above.

WHAT IS DERIVED AND WHAT IS STATED. The axis name, the fields a declaration must spell,
the fact the role resolves them into, the task names and every gate predicate are READ
out of the role, so a role that resolves or gates differently fails here instead of being
re-described. Only the Definition of Done's own values are stated — the four field names,
the candidate's environment id, its image, its cpu and its memory — because a test that
derived those from the file it is checking would assert nothing.
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
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_server"
_TASKS = _ROLE / "tasks" / "main.yml"
_ENVIRONMENT_TASKS = _ROLE / "tasks" / "environment.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"
_ROLE_DOC = _ROLE / "HOST_VARS.md"
_INVENTORY = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"

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
_MATCH_TASK = "Decide whether the catalog already matches what version control declares"
_DISPOSITION_TASK = "Name this environment's disposition in the run output"
_REPLACE_TASK = "Replace this environment in the instance's catalog"
_API_URL_FACT = "fabro_server_environments_url"
_PRESENT_FACT = "fabro_server_environment_present"
_SETTINGS_FACT = "fabro_server_environment_settings"
_CURRENT_FACT = "fabro_server_environment_current"
_MATCHES_FACT = "fabro_server_environment_matches"
_ENVIRONMENT_LOOP_VAR = "fabro_server_environment"

# The API this slice writes through, and the one environment variable the instance's
# own `server.env` carries the credential under. Both are the Definition of Done's
# words rather than the role's, which is why they are stated here.
_API_PATH = "/api/v1/environments"
_TOKEN_NAME = "FABRO_DEV_TOKEN"
_SERVER_ENV = "storage/server.env"
_DOC_HEADING = "## The sandbox environment catalog"
_ORCHESTRATOR_REPO = "livespec-orchestrator-beads-fabro"
_WORKFLOW_FILE = "workflow.toml"
# The filter pair that carries the measured trap below.
_ITEMS2DICT = "items2dict"
_LIST_FILTER = "list"
# The shell option every request in this slice opens with, and the only interpreter in
# this tree that HAS it. Both are stated rather than read: the point of the arm below is
# that a task using the former must name the latter, so deriving either from the file
# under test would assert nothing.
_PIPEFAIL = "pipefail"
_SHELL_EXECUTABLE_KEY = "executable"
_PIPEFAIL_SHELL = "/bin/bash"
_DEFAULT_SHELL = "/bin/sh"

# hp-xubuntu's three instances, and the one catalog entry the Definition of Done
# declares for its cutover candidate. Every value here is the Definition of Done's own:
# a test that read them out of the file it is checking would assert nothing.
_CANDIDATE_UNIT = "fabro-server-candidate"
_FLEET_UNIT = "fabro-server"
_HOMELAB_UNIT = "fabro-server-mi-homelab"
_CANDIDATE_ENVIRONMENT = {
    "id": "livespec-ci",
    "image": "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5",
    "cpu": "4",
    "memory": "8GB",
}

# One instance of a host's committed `fabro_server_instances`, and the nested catalog
# block it may carry. `unit_name` opens every instance mapping in both files, which is
# what bounds a read to one instance.
_INSTANCE_OPENER = re.compile(r"^ {2}- unit_name: (?P<unit>\S+)$")
_ENVIRONMENTS_OPENER = re.compile(r"^ {4}environments:$")
_ENVIRONMENT_OPENER = re.compile(r"^ {6}- (?P<key>[a-z_0-9]+): (?P<value>.+)$")
_ENVIRONMENT_FIELD = re.compile(r"^ {8}(?P<key>[a-z_0-9]+): (?P<value>.+)$")


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
_NOT = "not "
# One mapping entry of a `set_fact` or an `environment` block, inline or folded. The
# folded continuation sits deeper than the key, which is what ends one entry and begins
# the next without a YAML parser.
_SET_FACT_KEY = re.compile(r"^ {4}(?P<fact>[A-Za-z_][A-Za-z_0-9]*): (?P<value>.*)$")
_FOLDED_LINE = re.compile(r"^ {6,}(?P<text>\S.*)$")
_ROLE_DEFAULT = re.compile(r"^(?P<name>fabro_server_[a-z_0-9]+): (?P<value>\S+)$", re.MULTILINE)
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


# --- the run that writes nothing because the catalog already matches -------


def _truth(*, condition: str, scope: Mapping[str, bool]) -> bool:
    """One gate condition of the role, evaluated against one modelled catalog state.

    The vocabulary is exactly what the role's two write gates use — a reference, an
    optional `| bool`, `not`, and parentheses — and nothing else. An unmodelled name
    ASSERTS rather than defaulting: a gate evaluated against a value this test invented
    is a gate evaluated against a different condition, which is worse than one left
    unevaluated because it answers confidently.
    """
    text = condition.strip()
    if text.startswith(_NOT):
        return not _truth(condition=text[len(_NOT) :], scope=scope)
    if text.startswith("(") and text.endswith(")"):
        return _truth(condition=text[1:-1], scope=scope)
    name = text.removesuffix("| bool").strip()
    assert name in scope, (
        f"the role's catalog gate reads {name!r}, which this test does not model. Model "
        f"it rather than letting the arms below answer about a catalog state that was "
        f"never described"
    )
    return scope[name]


def _fires(*, name: str, scope: Mapping[str, bool]) -> bool:
    """Whether every `when:` condition of one task holds — Ansible ANDs a list.

    An EMPTY list asserts rather than returning True. Ansible's own reading of a missing
    `when:` is "always", so returning True would be faithful to Ansible and useless
    here: every arm below asks whether a write fires on one catalog state and not
    another, and a gate this reader could not see answers both questions the same way
    while looking exactly like a gate that passed.
    """
    conditions = _conditions(body=_named(name=name, source=_ENVIRONMENT_TASKS), field="when")
    assert conditions, (
        f"{name!r} writes a live factory's catalog and MUST carry a `when:` this reader "
        f"can see; an unread gate reads as firing unconditionally, which here means "
        f"rewriting an environment on every converge"
    )
    return all(_truth(condition=condition, scope=scope) for condition in conditions)


def _catalog_state(*, present: bool, matches: bool) -> dict[str, bool]:
    """One modelled state of the instance's catalog for one declared environment."""
    return {_PRESENT_FACT: present, _MATCHES_FACT: matches}


def test_a_run_whose_declared_environments_already_match_the_catalog_writes_nothing() -> None:
    """The third assertion, with both control arms: converged writes, drift does."""
    converged = _catalog_state(present=True, matches=True)
    for write in (_CREATE_TASK, _REPLACE_TASK):
        assert not _fires(name=write, scope=converged), (
            f"{write!r} MUST be skipped for an environment the catalog already holds with "
            f"the declared image, cpu and memory. A converge that wrote anyway would report "
            f"a change on every run of a converged host, which makes the change report "
            f"itself worthless — and every write to this API is a write to the catalog a "
            f"live factory dispatches runs into"
        )
    drifted = _catalog_state(present=True, matches=False)
    assert _fires(name=_REPLACE_TASK, scope=drifted), (
        "the first control arm: an environment the catalog holds with OTHER settings MUST "
        "be replaced. Without it 'writes nothing when converged' would be satisfied by a "
        "role that never writes an existing environment at all, which is the hand-POSTed "
        "catalog this slice exists to replace"
    )
    assert not _fires(name=_CREATE_TASK, scope=drifted), (
        "an environment the catalog already holds must not be CREATED: the collection "
        "endpoint refuses an id it already carries, so the run would fail rather than "
        "converge"
    )
    absent = _catalog_state(present=False, matches=False)
    assert _fires(name=_CREATE_TASK, scope=absent), (
        "the second control arm: the measured hp-candidate state — the declared "
        "environment absent from the catalog entirely — MUST be created. That is the "
        "condition the canary run failed in"
    )
    assert not _fires(name=_REPLACE_TASK, scope=absent), (
        "an absent environment must not be REPLACED: the per-environment endpoint 404s, "
        "and the If-Match revision it would carry does not exist"
    )


def test_the_match_decision_is_read_from_the_catalog_and_covers_every_declared_value() -> None:
    """The control on the decision: it compares the declared values against the real entry."""
    decision = _set_facts(name=_MATCH_TASK, source=_ENVIRONMENT_TASKS)
    assert _MATCHES_FACT in decision, f"the role must derive {_MATCHES_FACT}"
    expression = decision[_MATCHES_FACT]
    assert _CURRENT_FACT in expression, (
        f"{_MATCHES_FACT} MUST be computed against {_CURRENT_FACT}, the entry the catalog "
        f"read returned. A decision taken against anything else is a gate answering about "
        f"a catalog nobody looked at;\nexpression={expression!r}"
    )
    for field in _FIELDS:
        if field == "id":
            # The id is not COMPARED — it is what the entry was looked up by, so an
            # answer about any other id could not have been returned by that read.
            continue
        assert f"{_ENVIRONMENT_LOOP_VAR}.{field}" in expression, (
            f"the decision MUST compare the declared {field!r}. A field left out of it is "
            f"a field a converge would never correct: the catalog would keep the server's "
            f"own value and every run would report the environment as already matching"
        )
    assert _PRESENT_FACT in expression, (
        f"{_MATCHES_FACT} MUST be false for an environment the catalog does not hold at "
        f"all, independently of the comparisons: the entry it would compare against is the "
        f"empty mapping, and every `| default()` in those comparisons would then decide "
        f"the answer rather than the catalog"
    )
    replace = _named(name=_REPLACE_TASK, source=_ENVIRONMENT_TASKS)
    assert "--request PUT" in replace, (
        f"replacing MUST be a PUT to {_API_PATH}/<id>; POST is the create endpoint and "
        f"refuses an id the catalog already holds"
    )
    assert "If-Match" in replace and f"{_CURRENT_FACT}.revision" in replace, (
        "the replace MUST carry If-Match with the revision the read returned. That is the "
        "server's own optimistic-concurrency check: without it a converge would overwrite "
        "a change made between the read and the write, and the API requires the header, so "
        "there is no form of this request that skips the check"
    )
    disposition = _named(name=_DISPOSITION_TASK, source=_ENVIRONMENT_TASKS)
    assert _conditions(body=disposition, field="when") == [], (
        "the disposition report MUST be ungated. Ansible skips a `shell` under `--check`, "
        "so it is the only thing a drift read can learn about a catalog from — and a drift "
        "read that said nothing would be indistinguishable from one that found no drift"
    )
    assert _MATCHES_FACT in disposition and _PRESENT_FACT in disposition, (
        "the report MUST name both halves of the decision, so the operator reading a dry "
        "run can tell 'already converged' from 'would be created' from 'would be replaced'"
    )


def test_the_catalog_write_gates_stay_inside_the_vocabulary_this_test_can_evaluate() -> None:
    """The control on the evaluator: every gate the arms read must actually be evaluated."""
    scope = _catalog_state(present=True, matches=True)
    for write in (_CREATE_TASK, _REPLACE_TASK):
        conditions = _conditions(body=_named(name=write, source=_ENVIRONMENT_TASKS), field="when")
        for condition in conditions:
            assert isinstance(_truth(condition=condition, scope=scope), bool), (
                f"{write}: the role's gate {condition!r} must evaluate to a verdict here, "
                f"or the arms above are reading a condition this evaluator does not "
                f"understand — and an unevaluated gate is a test that has stopped checking "
                f"whether a converge rewrites a live factory's catalog"
            )
    with pytest.raises(AssertionError, match="does not model"):
        _truth(condition="fabro_server_environment_a_fact_no_arm_describes", scope=scope)


# --- what hp-xubuntu's cutover candidate declares --------------------------


def _declared_environments(*, unit: str, source: Path) -> list[dict[str, str]]:
    """Every environment the named instance of `source` declares, in file order.

    One parser serves both the role's `HOST_VARS.md` — the source the maintainer edits —
    and `inventory/host_vars/hp-xubuntu.yml`, which is generated from it and kept in
    lockstep by hand, so the two can be held against each other. Text-sliced for the
    same reason every other reader here is: no YAML library is importable in this suite.

    Bounded to ONE instance. An unbounded scan would read a sibling instance's catalog
    into this one's and still pass every assertion below, which is the quietest way for
    this module to stop testing the instance it names.
    """
    parsed: list[dict[str, str]] = []
    inside = False
    collecting = False
    for line in source.read_text(encoding="utf-8").splitlines():
        opener = _INSTANCE_OPENER.match(line)
        if opener is not None:
            inside = opener["unit"] == unit
            collecting = False
            continue
        if not inside or not line.strip() or line.strip().startswith("#"):
            continue
        if _ENVIRONMENTS_OPENER.match(line) is not None:
            collecting = True
            continue
        if not collecting:
            continue
        entry = _ENVIRONMENT_OPENER.match(line)
        if entry is not None:
            parsed.append({entry["key"]: _unquote(value=entry["value"])})
            continue
        field = _ENVIRONMENT_FIELD.match(line)
        if field is None:
            # Back at the instance's own indentation: the catalog block has closed.
            collecting = False
            continue
        assert parsed, f"{source.name} indents an environment field before any entry begins"
        parsed[-1][field["key"]] = _unquote(value=field["value"])
    assert parsed, (
        f"{source.name} must declare {unit}'s {_AXIS}; without them the factory's own "
        f"environment is still something somebody has to remember to POST by hand, which "
        f"is the state the hp-candidate canary failed in"
    )
    return parsed


def test_the_hp_candidate_declares_the_environment_the_factory_workflow_dispatches_into() -> None:
    """The fourth assertion, in the document the maintainer edits and the file the play reads."""
    declared = {
        source: _declared_environments(unit=_CANDIDATE_UNIT, source=source)
        for source in (_ROLE_DOC, _INVENTORY)
    }
    assert declared[_ROLE_DOC] == declared[_INVENTORY], (
        f"the role's HOST_VARS.md is the source and the inventory host_vars file is "
        f"generated from it, with no regeneration recipe — they are kept in lockstep by "
        f"hand, so a difference is a catalog the play will never write;\n"
        f"doc={declared[_ROLE_DOC]} inventory={declared[_INVENTORY]}"
    )
    for source, environments in declared.items():
        assert environments == [dict(_CANDIDATE_ENVIRONMENT)], (
            f"{source.name}: {_CANDIDATE_UNIT} MUST declare exactly the one environment the "
            f"factory's own workflow dispatches into — id {_CANDIDATE_ENVIRONMENT['id']}, "
            f"image {_CANDIDATE_ENVIRONMENT['image']}, cpu {_CANDIDATE_ENVIRONMENT['cpu']}, "
            f"memory {_CANDIDATE_ENVIRONMENT['memory']}. The image tag is the one the "
            f"orchestrator's implement-work-item workflow.toml pins, and the resource "
            f"envelope is the one the factory's runs are sized for; the server's seeded "
            f"default is 2 CPU and 4GB in buildpack-deps:noble, which is what the canary "
            f"run was prepared in when it failed;\ndeclared={environments}"
        )
    for source in (_ROLE_DOC, _INVENTORY):
        for other in (_FLEET_UNIT, _HOMELAB_UNIT):
            with pytest.raises(AssertionError, match=f"must declare {other}"):
                _declared_environments(unit=other, source=source)


# --- what the operator learns from the role's own document -----------------


def _doc_section(*, heading: str) -> str:
    """One `##` section of the role's HOST_VARS.md, up to the next `##`."""
    text = _ROLE_DOC.read_text(encoding="utf-8")
    start = text.find(f"{heading}\n")
    assert start >= 0, (
        f"the role's HOST_VARS.md must carry a {heading!r} section. This document is the "
        f"operator's interface to the role, and a mechanism that exists only in the task "
        f"comments is one the person bumping a sandbox image tag never reads"
    )
    remainder = text.find("\n## ", start + len(heading))
    return text[start:] if remainder < 0 else text[start:remainder]


def _prose(*, section: str) -> str:
    """One document section with markdown emphasis removed, for phrase matching.

    The arms below look for names an operator has to be able to read, and in correct
    markdown a variable or a path inside a sentence is backticked — so matching the raw
    bytes would make them pass only for prose that omitted the formatting the rest of
    this document uses, which is a test dictating typography rather than content.
    """
    return section.replace("`", "").replace("**", "")


def _catalog_defaults() -> dict[str, str]:
    """Every role default the catalog mechanism reads, and the value it carries."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in _ROLE_DEFAULT.finditer(_DEFAULTS.read_text(encoding="utf-8"))
        if match["name"].startswith("fabro_server_environment")
    }
    assert declared, (
        "the role must declare the catalog mechanism's own variables in defaults/main.yml, "
        "for the same reason it declares every other one there: a variable an operator "
        "discovers by reading tasks/ is the drift HOST_VARS.md exists to prevent"
    )
    return declared


def test_the_role_document_states_the_catalog_axis_and_where_its_image_tag_comes_from() -> None:
    """The fifth assertion: the axis, and that the image tag follows the workflow pin."""
    section = _doc_section(heading=_DOC_HEADING)
    assert len(section.split()) > 120, (
        f"{_DOC_HEADING!r} must carry the mechanism it names, not a stub. The operator "
        f"reading it is the one bumping a sandbox image tag or adding a second "
        f"environment, and what they need is not in the role's task comments;\n"
        f"section={section!r}"
    )
    prose = _prose(section=section)
    for named in (_AXIS, *_FIELDS, _API_PATH, _TOKEN_NAME, _SERVER_ENV):
        assert named in prose, (
            f"the section must name {named!r}: it is part of either the shape an operator "
            f"writes or the mechanism that carries it to the server, and a mechanism "
            f"documented by omission is one they reconstruct by reading the role"
        )
    for pinned in (_ORCHESTRATOR_REPO, _WORKFLOW_FILE, "pin"):
        assert pinned in prose, (
            f"the section must state that the declared image tag FOLLOWS {pinned!r}. A tag "
            f"declared here that the orchestrator's workflow does not pin is an "
            f"environment the factory never dispatches into — the two have to be bumped "
            f"together, and nothing but this document says so"
        )
    for disposition in ("created", "replaced"):
        assert disposition in prose, (
            f"the section must say when an environment is {disposition}. The three "
            f"dispositions — already matching, absent, present with other settings — are "
            f"what an operator reads a drift report against"
        )
    document = _ROLE_DOC.read_text(encoding="utf-8")
    for name, value in sorted(_catalog_defaults().items()):
        assert f"`{name}`" in document, (
            f"{name} is a catalog variable the role reads and the document does not name. "
            f"An undocumented variable is one an operator discovers by reading the role, "
            f"which is the drift this document exists to prevent"
        )
        assert value in document, (
            f"the document must name what {name} defaults to; the role defaults it to "
            f"{value!r}, which the document does not mention"
        )
    assert f"| `{_AXIS}` |" in document, (
        f"the optional-axis table must carry a {_AXIS!r} row too — that table is where an "
        f"operator looks for 'what may an instance mapping say', and a section further "
        f"down the document does not answer that question"
    )


# --- the derivation has to be one Ansible can actually evaluate ------------


def test_every_items2dict_in_the_role_is_handed_a_materialised_list() -> None:
    """A measured defect, kept out: `items2dict` REFUSES a generator.

    Measured 2026-10-11 by rendering the role's own settings expression through
    ansible-core 2.21.4's filter plugins: `dict2items | rejectattr(...) | items2dict`
    raises `AnsibleTypeError: items2dict requires a list, got <class 'generator'>
    instead`, because `rejectattr` is Jinja's own filter and yields a generator while
    `items2dict` type-checks its input. The whole derivation is therefore unevaluable,
    and nothing else in this suite could see it: every other arm reads the expression as
    TEXT, and the playbook's `--syntax-check` passes because the fault is in the
    template's runtime types rather than in its shape.

    The arm is written as a claim about EVERY `items2dict` in the role rather than about
    the one line that was wrong, because the trap belongs to the filter and not to this
    slice: the next derivation that filters a `dict2items` hits it identically.
    """
    piped = 0
    for source in (_TASKS, _ENVIRONMENT_TASKS, _HANDLERS):
        # Collapsed to one line first: a folded expression puts `| items2dict` on a line
        # of its own, so a per-line reader would see an empty upstream and report every
        # occurrence as wrong for the wrong reason — which it did, before this.
        collapsed = " ".join(source.read_text(encoding="utf-8").split())
        for match in re.finditer(rf"\| {_ITEMS2DICT}", collapsed):
            piped += 1
            upstream = collapsed[: match.start()].rstrip()
            assert upstream.endswith(f"| {_LIST_FILTER}"), (
                f"{source.name} pipes into {_ITEMS2DICT} from "
                f"{upstream.rsplit('|', 1)[-1].strip()!r}. `items2dict` type-checks its "
                f"input and REFUSES a generator, which is what Jinja's own `select`, "
                f"`reject`, `selectattr` and `rejectattr` all return — so the expression "
                f"does not merely read oddly, it raises at converge time. Materialise it "
                f"with `| {_LIST_FILTER}` first;\nupstream={upstream[-120:]!r}"
            )
    assert piped, (
        f"the role must still build a mapping with {_ITEMS2DICT}; this arm guards a trap "
        f"in that filter, and with no occurrence left it guards nothing"
    )


def test_the_disposition_is_reported_before_either_write_is_attempted() -> None:
    """A run says what it is about to do to a catalog before it does it.

    Measured 2026-10-11 by walking the committed task file through ansible-core's own
    Jinja for an absent environment: the create ran, and the line saying the environment
    "will be created" printed after it. In the future tense, about a write that had
    already happened. The same ordering makes a dry run read backwards — the only task
    `--check` reaches is the report, and a reader scanning a recap top-down would meet
    the two skipped writes first.
    """
    report = _task_index(name=_DISPOSITION_TASK, source=_ENVIRONMENT_TASKS)
    decision = _task_index(name=_MATCH_TASK, source=_ENVIRONMENT_TASKS)
    assert decision < report, (
        "the match decision MUST be taken before the report that reads it; a report "
        "ahead of its own input would render against whatever the previous loop "
        "iteration left behind, which on a second declared environment is the first "
        "one's verdict"
    )
    for write in (_CREATE_TASK, _REPLACE_TASK):
        assert report < _task_index(name=write, source=_ENVIRONMENT_TASKS), (
            f"{write!r} MUST come after the disposition report. A converge that writes "
            f"first and narrates afterwards says 'will be created' about a request it has "
            f"already made, and a dry run — where both writes are skipped and the report "
            f"is the only thing that runs — reads its own output out of order"
        )


def test_every_pipefail_shell_task_in_the_role_names_a_shell_that_has_pipefail() -> None:
    """A measured defect, kept out: `pipefail` under Ansible's DEFAULT shell exits 2.

    Measured 2026-10-11 by driving the committed catalog tail against a loopback stand-in
    for the instance's server: the run failed at the FIRST task of `environment.yml` with
    `rc: 2` and `stderr: "/bin/sh: 1: set: Illegal option -o pipefail"`, and the request
    log for the whole run held nothing but the health probes — no catalog read, no create,
    no replace. Ansible's `ansible_shell_executable` defaults to `/bin/sh`, nothing in
    this tree overrides it, and on a Debian-family host — which hp-xubuntu is — `/bin/sh`
    is dash, which has no `-o pipefail` and fails on the `set` line itself. So EVERY
    request this slice makes was unreachable on the target host.

    Nothing else in this suite could see it, which is the reason for the arm: every other
    arm reads the command TEXT and finds the pipe, the credential read and the curl flags
    all correct — they are — and `ansible-playbook --syntax-check` passes, because the
    fault is in which interpreter runs a correct script. `just check` passed 79/79 over a
    role whose catalog tasks could not run.

    Written as a claim about EVERY shell task in the role rather than about the four this
    slice added, because the trap belongs to the module default and not to this slice: the
    next shell task that opens with `set -o pipefail` hits it identically. It is also this
    tree's existing convention — `roles/node_status_credential/tasks/main.yml` and
    `roles/agent_node_password/tasks/reconcile_agent.yml` are the other inline-shell tasks
    under `ansible/`, and both pair `set -o pipefail` with `executable: /bin/bash`.

    BOTH halves are asserted of every shell task, unconditionally and with no filter,
    because for THIS role they are one property. `_api_calls` records why `shell` is
    reached for at all: the credential has to be read out of the instance's own
    `server.env` on the host and piped into curl, and a pipe is the whole difference
    between `shell` and `command`. A shell task here therefore has a pipe, a pipe whose
    upstream failure is swallowed is the bug `pipefail` exists to stop, and `pipefail`
    needs an interpreter that has it. A future task that wants `shell` without a pipe
    fails here and should: on this role's own reasoning it wanted `command`.
    """
    for name, body in _api_calls().items():
        assert _PIPEFAIL in body, (
            f"{name!r} runs a shell command without `set -o {_PIPEFAIL}`. This role uses "
            f"`shell` rather than `command` only because a request's credential is piped "
            f"into curl, and a pipe that reports its LAST command's status hides a failed "
            f"`sed` — which is a request sent with an empty bearer token. Open with "
            f"`set -euo {_PIPEFAIL}`, or use `command` if this task needs no pipe;"
            f"\nbody={body!r}"
        )
        assert f"{_SHELL_EXECUTABLE_KEY}: {_PIPEFAIL_SHELL}" in body, (
            f"{name!r} opens its command with `set -o {_PIPEFAIL}` and does not pass "
            f"`{_SHELL_EXECUTABLE_KEY}: {_PIPEFAIL_SHELL}`. Ansible runs a `shell` task "
            f"under `ansible_shell_executable`, which defaults to {_DEFAULT_SHELL} — dash "
            f"on every Debian-family factory host, including hp-xubuntu — and dash has no "
            f"`-o {_PIPEFAIL}`, so the task exits 2 on its own first line before reaching "
            f"the catalog at all. Name the interpreter that has the option;"
            f"\nbody={body!r}"
        )
    assert _api_calls(), (
        "the role must still reach its API with a shell request; this arm guards the "
        "interpreter those requests need, and with none left it guards nothing"
    )
