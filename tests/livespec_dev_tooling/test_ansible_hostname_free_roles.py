"""`_ansible_hostname_free_roles` — the role-tree half of the hostname-free check.

`check-ansible-hostname-free` refused a machine name in a play's `hosts:` field,
in a role's YAML values and in a role template. It did NOT read EXECUTABLES, and
that is where the names it missed actually lived: a `${VAR:-<host>}` default in a
shipped refresh tool, a host as an ssh `ProxyJump` target, a host as a directory
component of a key path, a `restic --host <host>` argument. All of them are
non-comment lines of files a role installs and a host then runs, and the check
passed the tree clean while every one of them was there
(measured 2026-10-19 on master cc607f3e, livespec-dev-tooling-mavj5i).

WHAT "AS A VALUE" MEANS IN A SHELL LINE, and why it is not the YAML rule. A YAML
value is the whole scalar, so `key: host` is an assignment and prose that merely
mentions a host inside a longer sentence is not. A shell line has no such shape:
the name arrives as a path component, after an `@`, inside a `${VAR:-...}`
default, or as the bare word after an option. So the line is read as SHELL
FIELDS — split on whitespace and on the punctuation that separates a value from
its surroundings, with `:-` treated as the default-expansion separator it is, and
a leading `-` stripped so an option's own argument is reached — and a field that
EQUALS an inventory host name is that host named as a value. `measured on vps:`
survives that split as the field `vps:`, which is not a host name, so a
provenance line inside an error message still passes; `vps-restic-backup` and
`arq-vps-backup` survive as themselves, so a path and an account name do too.

Those were carved out of the parent module into this one by cohesion: the parent
now owns the INVENTORY's host names, the play scan and the report, and this module
owns everything that reads a value out of the role tree.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "livespec_dev_tooling"
_ROLES_MODULE_PATH = _PACKAGE / "_ansible_hostname_free_roles.py"
_ROLES_MODULE_NAME = "livespec_dev_tooling._ansible_hostname_free_roles"
_CHECK_PATH = _PACKAGE / "ansible_hostname_free.py"

# The names that MUST cross the module boundary, and so must be public: pyright
# strict (`reportPrivateUsage`) and `check-private-calls` both refuse an import
# of a `_`-prefixed name defined elsewhere.
_PUBLIC_SURFACE = ("Finding", "role_findings", "strip_quotes")
# The names that must no longer be DEFINED in the parent: a size split that left
# the bodies behind and re-exported them would pass a "the new file exists" test
# while changing nothing.
_MOVED_OUT = (
    "class _Finding(",
    "def _role_findings(",
    "def _template_findings(",
    "def _yaml_line_findings(",
    "def _tailnet_pattern(",
)

_INVENTORY = """\
all:
  children:
    legacy:
      children:
        dev_hosts:
          hosts:
            vps:
        ci_pool:
          hosts:
            poweredge-xubuntu:
              cluster_role: server
"""


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "ansible_hostname_free check module should exist"
    spec = importlib.util.spec_from_file_location("ansible_hostname_free_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    returncode: int
    findings: list[dict[str, object]]


def _write(*, root: Path, relative: str, text: str, executable: bool = False) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and parse its findings."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    findings = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return _CheckRun(returncode=rc, findings=findings)


def _tree(*, root: Path) -> Path:
    """A minimal clean ansible tree: an inventory and one group-targeted play."""
    _write(root=root, relative="ansible/inventory/legacy.yml", text=_INVENTORY)
    _write(root=root, relative="ansible/site.yml", text="- name: Pool\n  hosts: ci_pool\n")
    return root


def _executable(*, root: Path, relative: str, body: str) -> None:
    """One role-installed script, shebang and executable bit both."""
    _write(
        root=root,
        relative=f"ansible/roles/r/files/{relative}",
        text=f"#!/usr/bin/env bash\n{body}",
        executable=True,
    )


def _tokens(*, run: _CheckRun) -> list[tuple[object, object]]:
    return [(item["kind"], item["token"]) for item in run.findings]


def test_the_role_tree_scan_lives_in_its_own_module() -> None:
    """The split, asserted on both sides so a re-export shim cannot satisfy it.

    The parent file was at 188 LLOC against a 200-line soft ceiling, so the
    executable rule could not be added to it without pushing it into the soft
    band. It is split by COHESION rather than by line count: the inventory's host
    names, the play scan and the report stay in the parent; everything that reads
    a VALUE out of the role tree moves here.
    """
    assert _ROLES_MODULE_PATH.is_file(), (
        "the role-tree scan must live in its own module: the parent cannot carry "
        "the executable rule and stay under the LLOC soft ceiling"
    )
    module = importlib.import_module(_ROLES_MODULE_NAME)
    parent_source = _CHECK_PATH.read_text(encoding="utf-8")

    for name in _PUBLIC_SURFACE:
        assert hasattr(module, name), f"{name} must cross the boundary, so it must be public"
    assert sorted(module.__all__) == sorted(_PUBLIC_SURFACE)
    for definition in _MOVED_OUT:
        assert definition not in parent_source, f"{definition} must be GONE from the parent"
    assert _ROLES_MODULE_PATH.stem in parent_source


def test_an_executable_assigning_a_host_name_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plainest shape, and the one a YAML-only scan cannot see at all."""
    root = _tree(root=tmp_path)
    _executable(root=root, relative="refresh", body='REMOTE_HOST="poweredge-xubuntu"\n')

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert run.returncode == 1
    assert _tokens(run=run) == [("host-value", "poweredge-xubuntu")]


def test_an_executable_defaulting_a_variable_to_a_host_name_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`${VAR:-<host>}` — the shape three shipped tools actually carried.

    It is the dangerous one precisely because it looks like parameterisation: the
    role resolves the value from the inventory and renders it, so the default is
    reached only on a host the role has not converged, and then it names the
    wrong machine instead of refusing.
    """
    root = _tree(root=tmp_path)
    _executable(root=root, relative="refresh", body='HOST="${GATES_REMOTE_HOST:-vps}"\n')

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert _tokens(run=run) == [("host-value", "vps")]


def test_a_tailnet_name_in_an_executables_default_expansion_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tailnet name reached through `:-`, which a plain word-boundary scan misses.

    The tailnet pattern refuses a `-` before the name, so that a hyphenated word
    ending in a host name is not a match. Inside `${VAR:-vps.…}` the character
    immediately before the name IS that `-`, so the one place a shipped script
    carried a tailnet address was invisible to the pattern that exists to find it.
    """
    root = _tree(root=tmp_path)
    _executable(
        root=root,
        relative="verify",
        body='CANONICAL="${FABRO_CANONICAL_HOST:-vps.perch-rudd.ts.net:32276}"\n',
    )

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert _tokens(run=run) == [("tailnet-name", "vps.perch-rudd.ts.net")]


def test_an_executable_naming_a_host_after_an_option_or_inside_a_path_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The remaining two shapes: an option's argument, and a path component.

    Both in one case because both are the same claim — a shell line's fields, not
    its whole scalar, are where a value lives — and because asserting the exact
    finding list proves the split reports each hit once rather than per character
    class it happened to break on.
    """
    root = _tree(root=tmp_path)
    _executable(
        root=root,
        relative="backup",
        body=(
            "restic forget --host vps --tag scheduled\n"
            "KEY=$HOME/.cache/acceptance/poweredge-xubuntu/id_ed25519\n"
            'ssh -o ProxyJump=cwoolley@poweredge-xubuntu "true"\n'
        ),
    )

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert [(item["line"], item["token"]) for item in run.findings] == [
        (2, "vps"),
        (3, "poweredge-xubuntu"),
        (4, "poweredge-xubuntu"),
    ]


def test_provenance_and_longer_words_in_an_executable_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three negative controls, so the rule is known to be aimed and not merely loud.

    A `#` comment is provenance and stays (the maintainer ruled so on
    livespec-dev-tooling-prdxxe). A host named inside an operator-facing sentence
    is a mention, not a binding — the live example records where a measurement
    was taken, inside a refusal message. And a host name that is a PREFIX of a
    longer word is a path or an account, which prdxxe also ruled out of scope:
    the `vps-` file and unit names are paths the vps-info installers created.
    """
    root = _tree(root=tmp_path)
    _executable(
        root=root,
        relative="reclaim",
        body=(
            "# measured on vps: 1 MB unprivileged against 17163 MB as root\n"
            'warn "       measured on vps: 1 MB as a non-root user --"\n'
            'EXCLUDE="${VPS_RESTIC_EXCLUDE_FILE:-/etc/vps-restic-backup/excludes.txt}"\n'
            "SAMBA_USER=arq-vps-backup\n"
            "KEY=$HOME/.cache/acceptance/$KVM_HOST/id_ed25519\n"
        ),
    )

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert run.findings == []
    assert run.returncode == 0


def test_a_shebang_script_without_the_executable_bit_is_still_scanned(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mode bit is file hygiene; a shebang is intent, and the tree carries both.

    Measured in this repository's own acceptance tree: of the FAULTS case scripts
    that named a machine, `lib.sh` carried the executable bit and no shebang
    while `p05_p06.sh` carried a shebang and mode 0644. A scan keyed on either
    one alone would have read half of them as data.
    """
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/r/acceptance/case.sh",
        text="#!/usr/bin/env bash\nssh cwoolley@poweredge-xubuntu true\n",
    )

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert _tokens(run=run) == [("host-value", "poweredge-xubuntu")]


def test_a_file_that_is_neither_executable_nor_a_template_is_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Role documentation and plain data are prose about the role, not values in it.

    `HOST_VARS.md` is the generator source for a machine's own host_vars and so
    names machines on purpose, and a fault catalogue names the machine its suite
    gates. Neither is installed and neither is run.
    """
    root = _tree(root=tmp_path)
    _write(root=root, relative="ansible/roles/r/HOST_VARS.md", text="r_host: vps\n")
    _write(root=root, relative="ansible/roles/r/acceptance/FAULTS.md", text="on vps\n")
    _write(root=root, relative="ansible/roles/r/files/excludes.txt", text="vps\n")

    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)

    assert run.returncode == 0
    assert run.findings == []
