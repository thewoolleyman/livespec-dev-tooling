"""The `fabro_server` role's `host_vars/gmktec-xubuntu.yml` prose, read against the values.

`SPECIFICATION/non-functional-requirements.md` requires, where it governs Fabro
factory host provisioning, that the owning role's `HOST_VARS.md` document the
per-host values ("Documented beside the values"). This module holds the
`gmktec-xubuntu` section —
and the `Sandbox-driver plugin providers` section it leans on — to the values the
committed `ansible/inventory/host_vars/gmktec-xubuntu.yml` actually declares.
Work-item `livespec-dev-tooling-u2dyce`; plan `petri-factory-on-gmktec`.

WHY THE PROSE IS A TEST AT ALL. Documentation is the one deliverable whose
staleness nothing else notices: the role converges identically whatever the prose
says, and the operator who needs it — the one deciding whether a rollback puts the
host back on a build the file still calls "current" — is by definition not the one
who wrote it. The section was written when gmktec ran ONE instance on the v0.382
carrier at two concurrent runs; host_vars has since gained the candidate instance,
rolled to the registered-provider carrier, gained the `livespec-ci-rust`
environment and put the Kubernetes provider on the fleet instance. Nothing failed,
and the file kept reading as a description of the host.

WHY EVERY FIGURE IS READ OUT OF `host_vars` RATHER THAN TRANSCRIBED. A test that
hard-coded `8` or `32278` would pass for a prose paragraph that agreed with the
test and disagreed with the machine — the exact failure this module exists to
catch, reproduced one layer up. So the unit names, the ports, the concurrency, the
environment ids and the provider digest are all taken from the committed
declaration, and the assertions are that the PROSE carries what the DECLARATION
says. A host_vars change that the prose does not follow fails here; a host_vars
change the prose follows passes without this file being touched.

WHY THE DIGEST IS COMPARED ACROSS TWO FILES INSTEAD OF SPELLED IN THE PROSE. The
section's claim is that the fleet instance declares the `kubernetes` provider "at
the plugin digest the `sandbox_driver_kubernetes` role pins" — a claim about
AGREEMENT, not about a literal. Spelling the 64 hexadecimal digits in the prose
would make a true sentence that the next digest bump turns into a false one with
nothing noticing, so the prose names the relationship and this module measures it:
the digest `host_vars` declares for that provider must equal the one the role's
own `defaults/main.yml` pins. The symptom the comparison catches is an instance
launching a plugin binary the role never staged, which the host verifies at every
launch and reports as a provider that will not start.

WHY THE SUPERSEDED FACTS ARE ASSERTED ABSENT, SCOPED TO THE SECTION. A document
that gains the new carrier beside the old one is worse than one that never gained
it: two carriers in one paragraph read as a choice, and the rollback line in
`host_vars` is the only place that says which direction is which. The absence arms
are therefore scoped to the `gmktec-xubuntu` section — `adeefec` is still the hp
candidate's own build and must stay in that section — and to the providers
section, where the Fabro draft PR that once stood for "a build with registered
providers" has been superseded by a build that is deployed and nameable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_DOC = _ANSIBLE / "roles" / "fabro_server" / "HOST_VARS.md"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_DRIVER_DEFAULTS = _ANSIBLE / "roles" / "sandbox_driver_kubernetes" / "defaults" / "main.yml"

_HOST_SECTION = "## `host_vars/gmktec-xubuntu.yml`"
_PROVIDERS_SECTION = "## Sandbox-driver plugin providers"

_FLEET_UNIT = "fabro-server"
_CANDIDATE_UNIT = "fabro-server-candidate"
_DEPLOYED_BUILD = "0.393.0-nightly.1"
_DEPLOYED_COMMIT = "9f6c38f"
_SUPERSEDED_CARRIER = "adeefec"
_SUPERSEDED_BUILD_REFERENCE = "#1048"
_PROCESS_SPEC_KEY = "process_spec"
_PROVIDER_KIND = "kubernetes"
_DRIVER_ROLE = "sandbox_driver_kubernetes"

# One `fabro_server_instances` entry: the `- unit_name:` list item and every line
# indented under it. The next list item at the same indent, or any line at a
# shallower indent, closes it — the rule a reader of the file applies by eye, and
# the only one available to a package that vendors no YAML reader.
_INSTANCE_BLOCK = re.compile(
    r"^  - unit_name: (?P<unit>\S+)\n(?P<body>(?:(?:    .*)?\n)*)",
    re.MULTILINE,
)


def _section(*, title: str) -> str:
    """One `## ` section of the role document, heading included, next heading excluded."""
    text = _DOC.read_text(encoding="utf-8")
    start = text.find(f"{title}\n")
    assert start >= 0, (
        f"{_DOC} must still carry the section `{title}`: every assertion below is about "
        f"its contents, so a renamed heading is a test that has stopped reading anything"
    )
    rest = text.find("\n## ", start + 1)
    return text[start:] if rest < 0 else text[start:rest]


def _instance(*, unit: str) -> str:
    """The committed `host_vars` block declaring one instance of this host."""
    declared: dict[str, str] = {
        str(match["unit"]): str(match["body"])
        for match in _INSTANCE_BLOCK.finditer(_HOST_VARS.read_text(encoding="utf-8"))
    }
    assert unit in declared, (
        f"{_HOST_VARS} must declare the instance `{unit}`: this module documents what that "
        f"declaration says, so an absent instance is an input the prose cannot be held to"
    )
    return declared[unit]


def _scalar(*, body: str, key: str) -> str:
    """One scalar an instance block declares, with comments and quoting stripped."""
    found = re.search(rf"^    {re.escape(key)}:\s*(?P<value>\S+)\s*$", body, re.MULTILINE)
    assert found is not None, f"{_HOST_VARS} must declare `{key}` for this instance"
    return found["value"].strip("\"'")


def _environment_ids(*, body: str) -> list[str]:
    """Every catalog environment id an instance block declares, in declaration order."""
    ids = re.findall(r"^      - id: (?P<id>\S+)$", body, re.MULTILINE)
    assert ids, f"{_HOST_VARS} must declare at least one environment for this instance"
    return ids


def test_the_section_describes_both_instances_the_host_vars_declare() -> None:
    """Both instances, each named with the port the declaration gives it.

    The port is the load-bearing half: the two instances share a machine, an
    account and a build, and differ by unit, state root and port. A section that
    named only the fleet instance — which is what it said while the canary ran
    beside it — reads as a description of the whole host, so an operator reasoning
    about :32278 has nothing committed to reason from.
    """
    section = _section(title=_HOST_SECTION)
    for unit in (_FLEET_UNIT, _CANDIDATE_UNIT):
        port = _scalar(body=_instance(unit=unit), key="port")
        assert f"`{unit}`" in section, (
            f"the {_HOST_SECTION} section must name the instance `{unit}` that "
            f"{_HOST_VARS} declares"
        )
        assert port in section, (
            f"the {_HOST_SECTION} section must give `{unit}` its declared port {port}: "
            f"the two instances differ by port, so a section that omits one cannot be "
            f"read against the running host"
        )


def test_the_section_names_the_build_both_instances_are_pinned_to() -> None:
    """The deployed carrier, and not the carrier it superseded.

    The `binary_source` agreement is asserted first because it is what makes the
    prose's "both instances" true: a section naming one build for two instances
    that `host_vars` pins differently would be a false sentence this module had
    certified.
    """
    for unit in (_FLEET_UNIT, _CANDIDATE_UNIT):
        source = _scalar(body=_instance(unit=unit), key="binary_source")
        assert _DEPLOYED_COMMIT in source, (
            f"{_HOST_VARS} pins `{unit}` to {source}, which does not carry commit "
            f"{_DEPLOYED_COMMIT}; the prose below names one build for both instances, so "
            f"the two declarations must agree before it can say so"
        )
    section = _section(title=_HOST_SECTION)
    assert _DEPLOYED_BUILD in section and _DEPLOYED_COMMIT in section, (
        f"the {_HOST_SECTION} section must name the deployed carrier {_DEPLOYED_BUILD} at "
        f"commit {_DEPLOYED_COMMIT}: it is the build the host runs, and the one a rollback "
        f"is a rollback FROM"
    )
    assert _SUPERSEDED_CARRIER not in section, (
        f"the {_HOST_SECTION} section must no longer name the superseded v0.382 carrier "
        f"{_SUPERSEDED_CARRIER}: two carriers in one paragraph read as a choice, and the "
        f"rollback line in {_HOST_VARS} is the only place that says which is which. It "
        f"stays in the hp-xubuntu section, which is that host's candidate build"
    )


def test_the_section_states_the_fleet_instances_concurrency_and_environment_ids() -> None:
    """The fleet instance's `max_concurrent_runs` and the environments it serves.

    The concurrency is the figure that moves with the sandbox slice, so a stale one
    is read as permission: the section said two runs against an 18G slice long
    after the maintainer directive raised both. The environment ids are what a
    repository's own factory entry must name to reach this instance at all, so an
    id declared on the host and absent from the prose is a capability nothing
    documents.
    """
    section = _section(title=_HOST_SECTION)
    body = _instance(unit=_FLEET_UNIT)
    runs = _scalar(body=body, key="max_concurrent_runs")
    assert "max_concurrent_runs" in section, (
        f"the {_HOST_SECTION} section must name `max_concurrent_runs`, which is the key an "
        f"operator changing this host's capacity changes"
    )
    assert re.search(rf"\b{re.escape(runs)}\b", section) is not None, (
        f"the {_HOST_SECTION} section must state the declared max_concurrent_runs value "
        f"{runs} for `{_FLEET_UNIT}`; {_HOST_VARS} declares it, and the section's previous "
        f"figure was the one two directives ago"
    )
    for environment in ("livespec-ci", "livespec-ci-rust", "livespec-ci-k8s"):
        assert environment in _environment_ids(body=body), (
            f"{_HOST_VARS} must still declare the `{environment}` environment for "
            f"`{_FLEET_UNIT}`: the prose below states that it does"
        )
        assert f"`{environment}`" in section, (
            f"the {_HOST_SECTION} section must state the environment id `{environment}` "
            f"that {_HOST_VARS} declares for `{_FLEET_UNIT}`: a dispatch reaches this "
            f"instance only through a factory entry naming one of them"
        )


def test_the_section_states_the_kubernetes_provider_at_the_roles_pinned_digest() -> None:
    """The provider the fleet instance declares, and the digest claim, measured.

    The prose names the RELATIONSHIP rather than the 64 hexadecimal digits, so the
    next digest bump cannot turn a true sentence false with nothing noticing; this
    arm is what makes the relationship a measurement. The symptom a disagreement
    produces is an instance launching a plugin binary the role never staged, which
    the host verifies at every launch and reports as a provider that will not
    start.
    """
    declared = re.search(
        rf"^      {re.escape(_PROVIDER_KIND)}:\n(?P<body>(?:(?:        .*)?\n)*)",
        _instance(unit=_FLEET_UNIT),
        re.MULTILINE,
    )
    assert declared is not None, (
        f"{_HOST_VARS} must declare the `{_PROVIDER_KIND}` sandbox provider for "
        f"`{_FLEET_UNIT}`: the prose below states that it does"
    )
    instance_digest = re.search(
        r"^        sha256: (?P<digest>\S+)$", declared["body"], re.MULTILINE
    )
    assert (
        instance_digest is not None
    ), f"{_HOST_VARS} must pin a sha256 for `{_FLEET_UNIT}`'s `{_PROVIDER_KIND}` provider"
    pinned = re.search(
        rf"^{re.escape(_DRIVER_ROLE)}_sha256: (?P<digest>\S+)$",
        _DRIVER_DEFAULTS.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert pinned is not None, (
        f"{_DRIVER_DEFAULTS} must still pin the plugin digest under "
        f"`{_DRIVER_ROLE}_sha256`; this arm reads it out of the role rather than restating "
        f"it, so a renamed variable is an arm that has stopped comparing anything"
    )
    assert instance_digest["digest"] == pinned["digest"], (
        f"`{_FLEET_UNIT}` declares the `{_PROVIDER_KIND}` plugin at "
        f"{instance_digest['digest']} while {_DRIVER_ROLE} stages {pinned['digest']}, so "
        f"the instance would launch a binary the role never put on the host"
    )
    section = _section(title=_HOST_SECTION)
    assert "`sandbox_providers`" in section and f"`{_PROVIDER_KIND}`" in section, (
        f"the {_HOST_SECTION} section must state that `{_FLEET_UNIT}` declares the "
        f"`{_PROVIDER_KIND}` sandbox provider through `sandbox_providers`"
    )
    assert f"`{_DRIVER_ROLE}`" in section and "digest" in section, (
        f"the {_HOST_SECTION} section must say the provider is declared at the plugin "
        f"digest the `{_DRIVER_ROLE}` role pins: the digest is the only thing standing "
        f"between 'this instance launches the plugin version control names' and 'this "
        f"instance launches whatever is at that path today'"
    )


def test_the_providers_section_names_the_deployed_carrier_as_the_process_spec_build() -> None:
    """The `process_spec` requirement, attributed to a build rather than to a draft.

    The requirement was written against Fabro draft PR #1048 — the change that was
    GOING to register an unbundled kind — because no build carrying it had been
    deployed. One has: the carrier `host_vars` pins for every instance on this
    host. A requirement attributed to an unmerged pull request cannot be checked
    by anyone reading it, and leaves "which builds need this key" answerable only
    by whoever remembers the PR.
    """
    section = _section(title=_PROVIDERS_SECTION)
    assert _PROCESS_SPEC_KEY in section, (
        f"the {_PROVIDERS_SECTION} section must still be the place `{_PROCESS_SPEC_KEY}` is "
        f"documented"
    )
    assert _DEPLOYED_BUILD in section and _DEPLOYED_COMMIT in section, (
        f"the {_PROVIDERS_SECTION} section must name the deployed carrier "
        f"{_DEPLOYED_BUILD} ({_DEPLOYED_COMMIT}) as the build that requires a provider "
        f"`{_PROCESS_SPEC_KEY}`: a reader can check a deployed build against the host, and "
        f"cannot check a draft pull request against anything"
    )
    assert _SUPERSEDED_BUILD_REFERENCE not in section, (
        f"the {_PROVIDERS_SECTION} section must no longer attribute the "
        f"`{_PROCESS_SPEC_KEY}` requirement to Fabro draft PR {_SUPERSEDED_BUILD_REFERENCE}: "
        f"the build that carries it is deployed and nameable, so the draft is no longer "
        f"the answer to 'which builds need this key'"
    )
