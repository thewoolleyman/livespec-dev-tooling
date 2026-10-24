"""gmktec-xubuntu's Fabro instances, and the prose that must describe them.

WHAT THIS FILE GRADES (work-item livespec-dev-tooling-u2dyce). The
"Documented beside the values" clause of
`SPECIFICATION/non-functional-requirements.md` requires the owning role's
`HOST_VARS.md` to document the per-host values the role reads. For
`gmktec-xubuntu` those values moved underneath the prose: the host gained a
second Fabro instance, rolled both onto a new carrier, gained a third catalog
environment and gained a sandbox-driver provider, while
`ansible/roles/fabro_server/HOST_VARS.md` still described one instance on the
v0.382 carrier at two concurrent runs. Prose that describes a configuration the
inventory no longer declares is worse than no prose: it reads as a record and
answers a reader wrongly, and nothing errors.

SO THE RECORD IS DERIVED, NOT RESTATED. Every expected value below is read out
of `ansible/inventory/host_vars/gmktec-xubuntu.yml` — the file the role actually
consumes — and the document is required to carry it. The point is the LOCKSTEP:
a later change to the instance set, a carrier move, a new environment id or a
raised `max_concurrent_runs` fails here until the section beside those values is
brought with it. A test that hard-coded today's figures would pass over exactly
the drift this item was filed for.

THE PLUGIN DIGEST IS GRADED ACROSS TWO FILES, because the document's claim spans
them: the instance declares the `kubernetes` provider at a digest, and the
`sandbox_driver_kubernetes` role installs the plugin at a digest. The claim
"at the plugin digest that role pins" is true only while the two agree, and a
host variable naming a build the role does not install is a provider whose
workers refuse it at every launch — a run that cannot start, reported as a
sandbox failure rather than as the drift it is.

TEXT-SLICED, for the reason the sibling `fabro_server` modules give: no YAML
library is importable in this suite (`ansible-lint` and `ansible-playbook` are
resolved through `uvx` against their own interpreter — see the justfile). Each
reader below therefore asserts the SHAPE of the committed file and refuses by
name anything it cannot find, so a parse that silently matched nothing surfaces
as a failing assertion rather than as an empty expectation that passes.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE_DOC = _ANSIBLE / "roles" / "fabro_server" / "HOST_VARS.md"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_PLUGIN_DEFAULTS = _ANSIBLE / "roles" / "sandbox_driver_kubernetes" / "defaults" / "main.yml"

# The two headings this item's Definition of Done names, spelled as the document
# spells them. A renamed heading is a section a reader cannot find, so it fails
# here rather than being searched for by fuzzy match.
_HOST_HEADING = "## `host_vars/gmktec-xubuntu.yml`"
_PROVIDER_HEADING = "## Sandbox-driver plugin providers"

# The fleet instance, and the provider kind it declares. Named rather than
# derived because they are what the Definition of Done is ABOUT: the assertions
# are statements about this instance and this kind, so deriving them from the
# file would make the test agree with whatever the file happened to say.
_FLEET_UNIT = "fabro-server"
_PROVIDER_KIND = "kubernetes"
_PLUGIN_ROLE = "sandbox_driver_kubernetes"
_PLUGIN_DIGEST_VARIABLE = f"{_PLUGIN_ROLE}_sha256"

# The carrier the host is pinned to, as the maintainer named it in the work-item:
# a release string that appears in no committed file, beside the commit the
# staged build path does carry. The commit is DERIVED (below) and compared, so
# the pair cannot drift apart silently; the release string is the human-readable
# half a reader asks for and git cannot supply.
_CARRIER_RELEASE = "0.393.0-nightly.1"
# The carrier this host was installed with and no longer runs. Its absence is the
# graded half of "names the new build WHERE it now names the old one": a section
# carrying both reads as a host running both.
_SUPERSEDED_CARRIER = "adeefec"

_INSTANCES_KEY = "fabro_server_instances:"
_UNIT_OPENING = re.compile(r"^  - unit_name: (?P<unit>\S+)$", re.MULTILINE)
_ENVIRONMENT_ID = re.compile(r"^\s+- id: (?P<id>\S+)$", re.MULTILINE)
# The commit the staged build path names, e.g. `v0393-9f6c38fab` -> `9f6c38fab`.
_BUILD_COMMIT = re.compile(r"/v\d+-(?P<commit>[0-9a-f]{7,})/")
_CONCURRENCY_STATEMENT = re.compile(r"`max_concurrent_runs` is (?P<runs>\d+)")
# How short a commit the prose may name. Seven is git's own default abbreviation.
_COMMIT_PREFIX = 7


def _document() -> str:
    assert _ROLE_DOC.is_file(), (
        f"the fabro_server role MUST carry {_ROLE_DOC.name}: it is the generator source for "
        f"every host's committed host_vars, so a role without it loses its per-host values "
        f"at the next regeneration"
    )
    return _ROLE_DOC.read_text(encoding="utf-8")


def _section(*, heading: str) -> str:
    """One `## ` section of the role document, heading excluded."""
    text = _document()
    assert heading in text, f"{_ROLE_DOC.name} MUST carry the section {heading!r}"
    body = text.split(heading, 1)[1]
    following = re.search(r"^## ", body, re.MULTILINE)
    return body[: following.start()] if following is not None else body


def _instances() -> dict[str, str]:
    """Each Fabro instance gmktec declares, unit name to the body declaring it."""
    text = _HOST_VARS.read_text(encoding="utf-8")
    assert _INSTANCES_KEY in text, (
        f"{_HOST_VARS.name} MUST declare {_INSTANCES_KEY!r}: the fabro_server role reads its "
        f"whole per-instance configuration from that list"
    )
    block = text.split(_INSTANCES_KEY, 1)[1]
    following = re.search(r"^[a-z]", block, re.MULTILINE)
    block = block[: following.start()] if following is not None else block
    openings = list(_UNIT_OPENING.finditer(block))
    assert openings, f"{_HOST_VARS.name} MUST declare at least one instance under its list"
    bounds = [*(match.start() for match in openings), len(block)]
    return {
        match["unit"]: block[start:end]
        for match, (start, end) in zip(openings, pairwise(bounds), strict=True)
    }


def _instance(*, unit: str) -> str:
    declared = _instances()
    assert unit in declared, (
        f"{_HOST_VARS.name} MUST declare the instance {unit!r}; it declares "
        f"{sorted(declared)} — this test grades the prose describing that instance, so a "
        f"renamed unit is a question about the inventory before it is one about the document"
    )
    return declared[unit]


def _scalar(*, body: str, key: str, why: str) -> str:
    """One scalar an instance declares, refused BY NAME when it declares none."""
    match = re.search(rf"^\s+{key}: (?P<value>\S.*)$", body, re.MULTILINE)
    assert match is not None, f"the instance MUST declare {key}: {why}"
    return match["value"].strip()


def _nested_block(*, body: str, key: str) -> str:
    """The lines nested under one mapping key, bounded by indentation.

    Bounded by the first line indented no deeper than the key itself, which is
    the whole of YAML's block structure this reader needs — and the reason a
    sibling key, or one of this file's column-four comments, closes the block
    rather than being swallowed into it.
    """
    openings = list(re.finditer(rf"^(?P<indent> *){key}:$", body, re.MULTILINE))
    assert len(openings) == 1, f"the instance MUST declare exactly one {key} mapping"
    rest = body[openings[0].end() :]
    closing = re.search(rf"^ {{0,{len(openings[0]['indent'])}}}\S", rest, re.MULTILINE)
    block = rest[: closing.start()] if closing is not None else rest
    assert block.strip(), f"the instance's {key} mapping MUST declare something"
    return block


def _child_keys(*, block: str) -> list[str]:
    """The keys at the outermost indent of one nested block, in file order."""
    lines = [line for line in block.splitlines() if line.strip()]
    depth = len(lines[0]) - len(lines[0].lstrip())
    return [
        line.strip().removesuffix(":")
        for line in lines
        if len(line) - len(line.lstrip()) == depth and line.strip().endswith(":")
    ]


def _plugin_digest() -> str:
    """The plugin digest the `sandbox_driver_kubernetes` role pins."""
    text = _PLUGIN_DEFAULTS.read_text(encoding="utf-8")
    pinned = rf"^{_PLUGIN_DIGEST_VARIABLE}: (?P<digest>[0-9a-f]{{64}})$"
    match = re.search(pinned, text, re.MULTILINE)
    assert match is not None, (
        f"{_PLUGIN_ROLE} MUST declare {_PLUGIN_DIGEST_VARIABLE} as a 64-hex digest: it is what "
        f"the host verifies the plugin against at every launch"
    )
    return match["digest"]


def _carrier_commit(*, body: str) -> str:
    """The commit the instance's staged build path names."""
    source = _scalar(
        body=body,
        key="binary_source",
        why="the control-node build this instance is carried from is what names its carrier",
    )
    match = _BUILD_COMMIT.search(source)
    assert match is not None, (
        f"the staged build path {source!r} MUST carry its commit, so the document and the "
        f"inventory name one build rather than two spellings of an unknown one"
    )
    return match["commit"]


def test_the_section_describes_both_instances_the_inventory_declares() -> None:
    section = _section(heading=_HOST_HEADING)
    for unit, body in _instances().items():
        port = _scalar(body=body, key="port", why="an instance is reached on exactly one port")
        assert f"`{unit}`" in section, (
            f"the {_HOST_HEADING} section MUST name the instance {unit!r}: the inventory "
            f"declares it, and a section describing fewer instances than the host runs reads "
            f"as a record of a host that does not exist"
        )
        assert port in section, (
            f"the {_HOST_HEADING} section MUST state {unit!r}'s port {port}: the port is how "
            f"an operator reaches the instance the prose is describing"
        )


def test_the_section_names_the_carrier_both_instances_are_pinned_to() -> None:
    section = _section(heading=_HOST_HEADING)
    commits = {unit: _carrier_commit(body=body) for unit, body in _instances().items()}
    assert len(set(commits.values())) == 1, (
        f"this test states that both instances are pinned to ONE build, which is what the "
        f"document says; the inventory now stages {commits} — bring the document's claim and "
        f"this assertion to whatever the inventory means before trusting either"
    )
    commit = next(iter(commits.values()))
    assert commit[:_COMMIT_PREFIX] in section, (
        f"the {_HOST_HEADING} section MUST name the carrier commit {commit[:_COMMIT_PREFIX]} "
        f"the inventory stages; the commit is the only half of a build's identity git can "
        f"check, so a section naming a release alone names a build nobody can resolve"
    )
    assert _CARRIER_RELEASE in section, (
        f"the {_HOST_HEADING} section MUST name the carrier release {_CARRIER_RELEASE}: it is "
        f"the half of the build's identity no committed file carries, so prose is the only "
        f"place a reader can learn it"
    )
    assert _SUPERSEDED_CARRIER not in section, (
        f"the {_HOST_HEADING} section MUST NOT still name the superseded carrier "
        f"{_SUPERSEDED_CARRIER!r}: this host no longer runs it, and a section naming two "
        f"carriers leaves a reader to guess which one is live"
    )


def test_the_section_states_the_fleet_instance_concurrency_and_environments() -> None:
    section = _section(heading=_HOST_HEADING)
    body = _instance(unit=_FLEET_UNIT)
    declared = _scalar(
        body=body,
        key="max_concurrent_runs",
        why="the slot cap is the per-host decision the sandbox slice is sized against",
    )
    stated = _CONCURRENCY_STATEMENT.search(section)
    assert stated is not None, (
        f"the {_HOST_HEADING} section MUST state the slot cap as '`max_concurrent_runs` is "
        f"<n>': it moves with the docker_sandbox_slice limits, so a reader raising one needs "
        f"the other's committed value in the same sentence"
    )
    assert stated["runs"] == declared, (
        f"the {_HOST_HEADING} section states `max_concurrent_runs` is {stated['runs']} while "
        f"{_FLEET_UNIT} declares {declared}: the prose and the value beside it disagree"
    )
    for environment in _ENVIRONMENT_ID.findall(_nested_block(body=body, key="environments")):
        assert f"`{environment}`" in section, (
            f"the {_HOST_HEADING} section MUST name {_FLEET_UNIT}'s catalog environment "
            f"{environment!r}: a dispatch reaches an environment only by naming it, so an "
            f"undocumented one is capacity nobody knows how to route to"
        )


def test_the_section_states_the_provider_is_pinned_to_the_roles_plugin_digest() -> None:
    section = _section(heading=_HOST_HEADING)
    providers = _nested_block(body=_instance(unit=_FLEET_UNIT), key="sandbox_providers")
    assert _child_keys(block=providers) == [_PROVIDER_KIND], (
        f"{_FLEET_UNIT} MUST declare exactly the {_PROVIDER_KIND!r} sandbox provider; it "
        f"declares {_child_keys(block=providers)} — the document's claim is about that kind"
    )
    declared = _scalar(
        body=providers,
        key="sha256",
        why="the instance's workers verify the plugin against this digest at every launch",
    )
    assert declared == _plugin_digest(), (
        f"{_FLEET_UNIT} declares the {_PROVIDER_KIND} plugin at {declared} while {_PLUGIN_ROLE} "
        f"installs {_plugin_digest()}: the document's claim that the two agree is false, and a "
        f"provider whose digest does not match the installed plugin refuses every launch"
    )
    assert f"`{_PROVIDER_KIND}`" in section and f"`{_PLUGIN_ROLE}`" in section, (
        f"the {_HOST_HEADING} section MUST state that {_FLEET_UNIT} declares the "
        f"{_PROVIDER_KIND!r} sandbox provider at the digest the {_PLUGIN_ROLE} role pins: the "
        f"two are one fact spread across two files, and only the prose says they must agree"
    )


def test_the_provider_section_names_the_deployed_carrier_rather_than_a_draft() -> None:
    section = _section(heading=_PROVIDER_HEADING)
    commit = _carrier_commit(body=_instance(unit=_FLEET_UNIT))
    assert _CARRIER_RELEASE in section and commit[:_COMMIT_PREFIX] in section, (
        f"the {_PROVIDER_HEADING} section MUST name the deployed carrier {_CARRIER_RELEASE} "
        f"({commit[:_COMMIT_PREFIX]}) as the build that requires a provider `process_spec`: an "
        f"operator reading it needs the build this fleet runs, not one it might have run"
    )
    assert "#1048" not in section, (
        f"the {_PROVIDER_HEADING} section MUST NOT still name Fabro draft PR #1048 as the "
        f"gate: the carrier carrying that work is deployed, so a draft reads as a capability "
        f"this fleet is still waiting on"
    )
