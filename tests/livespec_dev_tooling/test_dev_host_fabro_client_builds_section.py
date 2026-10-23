"""The `## Dev host Fabro client builds` section, read against the committed tree.

`SPECIFICATION/non-functional-requirements.md` (v088). Its sibling
`test_fabro_client_role` CONVERGES the role and holds it to the scenario's Thens
over a synthetic host; this module holds the committed DECLARATION, the committed
`bin`, and the role's own documentation to the parts of the section that are
claims about what this repository has written down. Work-item
`livespec-dev-tooling-lirki2`.

WHY THE COMMITTED ENTRIES ARE READ AND NOT CONVERGED. They name paths on the
maintainer's dev host, and `/home/ubuntu/.local/state/...` is a place a test may
not write — the work-item records those Thens as host-captured for exactly that
reason. But "the declaration is well formed" is not a host question at all, and
it is the one a synthetic fixture cannot answer: a fixture proves the ROLE refuses
a bad entry, and only the committed file proves THIS repository has not written
one. Both halves are needed, and the failure each catches is different: the
fixture catches a role that stopped refusing, this catches an inventory that
stopped being refusable.

WHY THE SERVER-BINARY DEFAULT IS COMPARED ACROSS TWO ROLES. The section's
exclusion is scoped to "the `binary_path`, explicit or defaulted (the default
being the one the `fabro_server` role applies for that host, resolved per host
rather than restated)". `fabro_client` cannot import that default — Ansible role
defaults are not shared with a play that does not include the role — so it
carries the same expression, and the agreement is held HERE rather than hoped for
in a comment. A server role whose default moved while this one did not would
narrow the exclusion silently, and the symptom would be the two roles writing one
file on a host where the PATH client is a symbolic link into the server's binary
directory, which is every dev host in this fleet.

WHY THE DOCUMENTATION IS A TEST. The section's "Documented beside the values"
clause is an obligation with named contents, and documentation is the one
deliverable whose absence nothing else notices: the role converges fine without
it, and the operator who needs the rollback procedure is by definition not the
one who wrote it. Each required subject is asserted by a term that could not be
present by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_client"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_DOC = _ROLE / "HOST_VARS.md"
_GROUP_VARS = _ANSIBLE / "inventory" / "group_vars" / "dev_hosts.yml"
_SERVER_TASKS = _ANSIBLE / "roles" / "fabro_server" / "tasks" / "main.yml"
_CONFIG = _REPO_ROOT / ".livespec.jsonc"
_JUSTFILE = _REPO_ROOT / "justfile"
_CHECK_TARGETS = _REPO_ROOT / "check-targets.txt"

_BUILDS_KEY = "fabro_client_builds"
_OWNER_VARIABLE = "fabro_client_owner"
_CHECK_SLUG = "check-dev-host-fabro-client-bins-declared"
_ENTRY_KEYS = ("path", "source", "sha256")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# The `fabro_server` role's own fallback for an instance that names no
# `binary_path`, read out of its `set_fact` rather than restated.
_SERVER_FALLBACK = re.compile(
    r"fabro_server_binary_path:\s*\"\{\{ fabro_server_instance\.binary_path"
    r"\s*\|\s*default\((?P<fallback>[^)]+)\) \}\}\""
)
_COMMITTED_BIN = re.compile(r'"bin":\s*"(?P<path>[^"]+)"')
# The declaration block: the key at column zero, and every indented or blank line
# under it. A line at column zero closes it, which is the rule the check applies.
_BUILDS_BLOCK = re.compile(rf"^{_BUILDS_KEY}:\n(?P<body>(?:[ \t].*\n|\n)*)", re.MULTILINE)


def _entries() -> list[dict[str, str]]:
    """The `fabro_client_builds` entries the committed inventory declares.

    Block-scoped on the same rule `dev_host_fabro_client_bins_declared` applies —
    a line at column zero closes the declaration — because this package vendors no
    YAML reader and the check and this test must not disagree about what the file
    declares. The block is taken by regex rather than walked line by line so that
    the two readers' agreement is about the RULE and not about two hand-written
    loops.
    """
    block = _BUILDS_BLOCK.search(_GROUP_VARS.read_text(encoding="utf-8"))
    assert block is not None, f"{_GROUP_VARS} must declare this group's {_BUILDS_KEY}"
    entries: list[dict[str, str]] = []
    for raw in block["body"].splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            entries.append({})
        assert entries, f"{_GROUP_VARS} indents an entry key before any entry begins"
        key, _, value = stripped.removeprefix("- ").partition(":")
        entries[-1][key] = value.strip().strip("\"'")
    assert entries, f"{_GROUP_VARS}'s {_BUILDS_KEY} block must declare at least one entry"
    return entries


def test_the_committed_declaration_carries_an_entry_this_role_can_act_on() -> None:
    """The "Declared once, in the inventory" clause, over the committed entries.

    The shape rules are asserted against the file rather than a fixture because an
    entry that fails any of them refuses the WHOLE converge of `ansible/dev-
    host.yml` on the dev host — not just its own build — so a malformed entry here
    takes nineteen other roles down with it, and the symptom is a play that stops
    before it reads anything.
    """
    entries = _entries()
    assert len(entries) >= 2, (
        "the two incompatible client families are the reason this section exists: "
        f"`legacy` (0.254 fork engine) and `petri` (Petri-era), so {_GROUP_VARS} "
        f"declares both; it declares {len(entries)}"
    )
    for entry in entries:
        assert sorted(entry) == sorted(_ENTRY_KEYS), (
            f"every entry carries exactly path, source and sha256; this one carries "
            f"{sorted(entry)}"
        )
        assert entry["path"].startswith("/"), f"{entry['path']} must be absolute"
        assert entry["source"].startswith("/"), f"{entry['source']} must be absolute"
        assert _HEX64.match(entry["sha256"]) is not None, (
            f"the digest for {entry['path']} must be 64 lowercase hexadecimal digits; it "
            f"is '{entry['sha256']}'. The digest is the only thing standing between "
            f"'this host runs the build version control names' and 'this host runs "
            f"whatever is at that source path today'"
        )
    paths = [entry["path"] for entry in entries]
    assert len(set(paths)) == len(paths), f"two entries declare one path: {paths}"
    sources = [entry["source"] for entry in entries]
    assert not set(paths) & set(sources), (
        "no entry's source may be any entry's path: the dev host is the control node, "
        f"so the two name one machine. paths={paths} sources={sources}"
    )


def test_no_declared_path_is_the_binary_path_this_hosts_server_instances_default_to() -> None:
    """The exclusion, measured against the default the `fabro_server` role applies.

    The default is taken out of the server role's own `set_fact` and rendered with
    this host's `fabro_server_host_home`, so the comparison is the one the role
    makes at converge time rather than a literal typed twice. On `vps` the PATH
    client is a symbolic link to that exact file, which is why the exclusion is
    the thing keeping two roles from writing one binary.
    """
    fallback = _SERVER_FALLBACK.search(_SERVER_TASKS.read_text(encoding="utf-8"))
    assert fallback is not None, (
        f"{_SERVER_TASKS} must still resolve fabro_server_binary_path from the "
        f"instance's own binary_path with a default; this test reads that default out "
        f"of it rather than restating it, so a renamed fact is a test that has stopped "
        f"comparing anything"
    )
    expression = fallback["fallback"].strip()
    assert expression in _DEFAULTS.read_text(encoding="utf-8"), (
        f"{_DEFAULTS} must carry the server role's own default expression "
        f"({expression!r}) so the two cannot drift: a server default that moved while "
        f"this one did not would narrow the exclusion silently, and the symptom is two "
        f"roles writing one binary on a host whose PATH client links to it"
    )
    # Rendered the way the role renders it: the home of the account the dev host's
    # own host_vars name, which is the only machine-specific part of the default.
    home = re.search(
        r"^fabro_server_host_home:\s*(?P<home>\S+)$",
        (_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert home is not None, "the dev host's host_vars must declare fabro_server_host_home"
    defaulted = f"{home['home']}/.fabro/bin/fabro"
    declared = [entry["path"] for entry in _entries()]
    assert defaulted not in declared, (
        f"{defaulted} is the binary_path this host's fabro_server instances default to, "
        f"so no fabro_client_builds entry may declare it; declared={declared}"
    )
    for path in declared:
        assert not path.startswith(f"{home['home']}/.fabro/bin/"), (
            f"{path} sits in the directory fabro_server stages and RETAINS its own "
            f"builds in. The refusal catches the same FILE; it cannot catch a "
            f"neighbour, and a client build among the server's `.bak` copies is one an "
            f"operator reading that directory would take for a server build"
        )


def test_every_committed_bin_names_a_declared_path_and_the_check_is_wired() -> None:
    """The "Committed bins name a declared path" clause, both halves.

    The correspondence AND its enforcement, because either alone is the failure
    this clause names: a committed `bin` naming an undeclared path is a routing
    table resting on a hand-staged binary, and a correspondence that holds today
    with no check wired is one nothing keeps.
    """
    declared = [entry["path"] for entry in _entries()]
    committed = [
        match["path"] for match in _COMMITTED_BIN.finditer(_CONFIG.read_text(encoding="utf-8"))
    ]
    assert committed, (
        f"{_CONFIG} commits a dispatcher factory `bin` today — the petri carrier "
        f"client — so a reading that found none has stopped reading the file, and "
        f"every assertion below would then hold for want of an input"
    )
    for path in committed:
        assert path in declared, (
            f"the committed bin {path} names no declared fabro_client_builds path "
            f"({declared}), so the build a Dispatcher execs is staged by nothing"
        )
    assert _CHECK_SLUG in _JUSTFILE.read_text(encoding="utf-8"), (
        f"{_CHECK_SLUG} must be wired into this repository's `just check` aggregate: "
        f"the clause names it, and a correspondence nothing asserts is one the next "
        f"`bin` change breaks silently"
    )
    assert _CHECK_SLUG in _CHECK_TARGETS.read_text(encoding="utf-8"), (
        f"{_CHECK_SLUG} must also be a member of the tracked check-targets inventory, "
        f"which is the single source of truth the aggregate's mirror is read from"
    )


@pytest.mark.parametrize(
    ("subject", "term"),
    [
        ("the declaration itself", _BUILDS_KEY),
        ("the owner variable", _OWNER_VARIABLE),
        ("each entry key: path", "`path`"),
        ("each entry key: source", "`source`"),
        ("each entry key: sha256", "`sha256`"),
        ("which committed bin points at each declared path", "dispatcher.factories.petri.bin"),
        ("why rollback is a change to the inventory", "Rollback is a change to the inventory"),
        ("that the fabro_server role retains a copy and this one does not", "retains"),
        ("that a declared path is never a server instance's binary_path", "never a server"),
        ("that it is best kept out of the server's binary directory", "binary directory"),
        ("that a dev host whose login differs sets the owner variable", "login differs"),
    ],
)
def test_host_vars_documents_every_subject_the_section_names(*, subject: str, term: str) -> None:
    """The "Documented beside the values" clause, one arm per named subject.

    One arm each rather than one assertion over a list, so a missing subject names
    ITSELF in the failure rather than being one absent member of eleven.
    """
    assert term in _DOC.read_text(encoding="utf-8"), (
        f"{_DOC} must document {subject}: the section names it as a required content "
        f"of this file, and the reader who needs it is by definition not the one who "
        f"wrote the role"
    )
