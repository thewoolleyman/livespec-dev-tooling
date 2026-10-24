"""Outside-in test for `livespec_dev_tooling/dev_host_fabro_client_bins_declared.py`.

This repository's `SPECIFICATION/non-functional-requirements.md` states how a dev
host carries pinned Fabro client builds (v088), and its "Committed bins name a
declared path" clause is what this check asserts:
every `dispatcher.factories.<name>.bin` this repository commits in its root
`.livespec.jsonc` MUST equal the `path` of one `fabro_client_builds` entry, and the
check MUST report itself VACUOUS rather than as a pass when no `bin` is committed.
Work-item `livespec-dev-tooling-lirki2`.

WHY THE VACUOUS ARM IS A TEST AND NOT A COMMENT. A repository that commits no `bin`
makes this check inspect nothing, and an exit 0 from a run that inspected nothing
certifies nothing. The two are indistinguishable from the exit status alone, which
is exactly why the clause names the distinction: a reader who sees only green has to
be able to tell "every bin is declared" from "there were no bins". So the arm asserts
the `verdict="vacuous"` event, not merely the status.

WHY THE MISSING-INVENTORY ARM FAILS CLOSED. A committed `bin` with no readable
`fabro_client_builds` declaration is the arrival state the implementation rider
warned about — the check red on arrival because the inventory entry landed in a
later pull request. The honest answer there is a refusal naming the absent file, NOT
an empty declared set that would make every bin read as undeclared with no cause
given, and NOT a pass earned by the declaration being unreadable.

THE COMMITTED TREE IS AN ARM. The repository commits one `bin` today — the petri
carrier client — so the committed arm is the one assertion a synthetic fixture
cannot make: that THIS tree's own `.livespec.jsonc` and its own
`ansible/inventory/group_vars/dev_hosts.yml` agree. A fixture-only suite would stay
green through exactly the drift this check exists to catch.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "dev_host_fabro_client_bins_declared.py"

_CONFIG_RELATIVE = ".livespec.jsonc"
_GROUP_VARS_RELATIVE = "ansible/inventory/group_vars/dev_hosts.yml"

_LEGACY_BIN = "/synthetic-dev-host/clients/legacy/fabro"
_PETRI_BIN = "/synthetic-dev-host/clients/petri/fabro"


def _config(*, bins: dict[str, str]) -> str:
    """A `.livespec.jsonc` carrying `bins` under the orchestrator's dispatcher block.

    Written with `//` line comments and a comment whose text contains a `bin` that is
    NOT declared, because a reader that strips comments by a naive scan would read
    that example as a committed value and refuse a tree that commits nothing of the
    kind.
    """
    factories = ",\n".join(
        f'          "{name}": {{ "registry": true, "bin": "{path}" }}'
        for name, path in bins.items()
    )
    return (
        "// Project-local livespec configuration.\n"
        "{\n"
        '  "spec_root": "SPECIFICATION",\n'
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "dispatcher": {\n'
        '      "default_factory": "petri",\n'
        "      // An EXAMPLE, not a committed value:\n"
        '      //   "bin": "/synthetic-dev-host/clients/never-declared/fabro"\n'
        '      "factories": {\n'
        f"{factories}\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def _group_vars(*, declared: list[str]) -> str:
    """A `dev_hosts.yml` declaring `declared`, with the surrounding keys a real one has."""
    entries = "".join(
        f"  - path: {path}\n"
        f"    source: /control-node/staged/{index}/fabro\n"
        f"    sha256: {str(index) * 64}\n"
        for index, path in enumerate(declared)
    )
    return (
        "---\n"
        "# Group variables for `dev_hosts`.\n"
        "\n"
        "fabro_factory_registry:\n"
        "  petri:\n"
        "    host: a-host\n"
        "    unit_name: fabro-server\n"
        "\n"
        "fabro_client_builds:\n"
        f"{entries}"
        "\n"
        "# A trailing key at column zero, which closes the block above.\n"
        "some_other_group_value: true\n"
    )


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), (
        f"{_CHECK_PATH.name} must exist: it is the check the ratified clause names as "
        f"`check-dev-host-fabro-client-bins-declared`, and without it every committed "
        f"`bin` in this repository names a path nothing holds the inventory to"
    )
    spec = importlib.util.spec_from_file_location("fabro_client_bins_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    returncode: int
    events: list[dict[str, object]]


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and parse its events."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return _CheckRun(returncode=rc, events=events)


def _write(*, root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _tree(*, root: Path, bins: dict[str, str], declared: list[str]) -> Path:
    _write(root=root, relative=_CONFIG_RELATIVE, text=_config(bins=bins))
    _write(root=root, relative=_GROUP_VARS_RELATIVE, text=_group_vars(declared=declared))
    return root


def _kinds(*, run: _CheckRun) -> list[object]:
    return [event["kind"] for event in run.events if "kind" in event]


def _verdicts(*, run: _CheckRun) -> list[object]:
    return [event["verdict"] for event in run.events if "verdict" in event]


def test_this_repositorys_own_committed_bin_names_a_declared_path(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The committed arm: THIS tree's `.livespec.jsonc` and inventory agree.

    The one assertion no fixture can make. The repository commits a `bin` for the
    petri factory, so this arm is not vacuous either — and it asserts that too,
    because a run that stopped finding the committed bin would otherwise pass here
    for the wrong reason.
    """
    run = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0, run.events
    assert _kinds(run=run) == []
    assert "vacuous" not in _verdicts(run=run), (
        "this repository commits a dispatcher factory `bin`, so this check must have "
        "something to inspect here; a vacuous verdict means the reader stopped finding "
        f"it and the green below is earned by reading nothing: {run.events}"
    )


def test_a_tree_whose_every_bin_names_a_declared_path_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two committed bins, both declared, and one declared path no bin names."""
    root = _tree(
        root=tmp_path,
        bins={"legacy": _LEGACY_BIN, "petri": _PETRI_BIN},
        declared=[_LEGACY_BIN, _PETRI_BIN, "/synthetic-dev-host/clients/spare/fabro"],
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0, run.events
    assert _kinds(run=run) == []
    assert "vacuous" not in _verdicts(run=run)


def test_a_bin_that_names_no_declared_path_fails_naming_the_factory_and_the_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal names WHICH factory and WHAT it points at, against a declared sibling.

    The petri bin IS declared in the same arm, so a check that refused every bin
    regardless cannot pass this.
    """
    root = _tree(
        root=tmp_path,
        bins={"legacy": _LEGACY_BIN, "petri": _PETRI_BIN},
        declared=[_PETRI_BIN],
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["bin-names-no-declared-path"]
    finding = run.events[0]
    assert finding["factory"] == "legacy"
    assert finding["bin"] == _LEGACY_BIN
    assert finding["declared"] == [_PETRI_BIN]


def test_a_bin_that_only_resembles_a_declared_path_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Equality is the rule the clause states, not a prefix or a basename match.

    A `bin` one directory below a declared path, and a declared path that merely
    CONTAINS the bin, both have to fail: a routing table that resolves to a sibling
    of the staged build is a routing table pointing at a file GitOps never placed.
    """
    root = _tree(
        root=tmp_path,
        bins={"petri": _PETRI_BIN},
        declared=[f"{_PETRI_BIN}.incoming", "/synthetic-dev-host/clients/petri"],
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["bin-names-no-declared-path"]


def test_a_tree_that_commits_no_bin_reports_itself_vacuous(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clause's own words: vacuous rather than a pass.

    The inventory still declares a build, so the arm cannot pass merely because there
    was nothing anywhere to read.
    """
    root = _tree(root=tmp_path, bins={}, declared=[_PETRI_BIN])
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0, run.events
    assert _kinds(run=run) == []
    assert _verdicts(run=run) == ["vacuous"]


def test_a_committed_bin_with_no_declaration_file_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The arrival state the rider named: the bin is committed, the inventory is not.

    It must refuse NAMING the absent file. An empty declared set would read as "no
    build is declared", which is a different finding with a different remedy.
    """
    root = tmp_path
    _write(root=root, relative=_CONFIG_RELATIVE, text=_config(bins={"petri": _PETRI_BIN}))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["declaration-file-absent"]
    assert run.events[0]["path"] == _GROUP_VARS_RELATIVE


def test_a_missing_declaration_file_with_no_committed_bin_is_still_vacuous(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing to inspect is nothing to inspect, whether or not the inventory exists.

    The clause makes the VACUOUS verdict a property of the committed bins, so a
    repository that declares no build and commits no bin is not in breach of anything
    — and must not be refused for a file it has no obligation to carry.
    """
    root = tmp_path
    _write(root=root, relative=_CONFIG_RELATIVE, text=_config(bins={}))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0, run.events
    assert _verdicts(run=run) == ["vacuous"]


def test_an_unreadable_configuration_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.livespec.jsonc` that does not parse is a reading that was never taken.

    Both halves are refusals, and they are named apart: an ABSENT configuration and
    one that will not parse have different remedies, and neither may read as "this
    repository commits no bin".
    """
    root = tmp_path
    _write(root=root, relative=_GROUP_VARS_RELATIVE, text=_group_vars(declared=[_PETRI_BIN]))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["configuration-absent"]

    _write(root=root, relative=_CONFIG_RELATIVE, text='{ "spec_root": ')
    unparseable = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert unparseable.returncode == 1
    assert _kinds(run=unparseable) == ["configuration-unparseable"]


def test_a_declaration_that_carries_no_builds_key_is_read_as_declaring_none(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file exists and declares nothing, which the clause permits — so the bin fails.

    The distinction from the absent-file arm is the FINDING, not the status: a present
    file that declares no build is an inventory an operator can read and fix in place.
    """
    root = tmp_path
    _write(root=root, relative=_CONFIG_RELATIVE, text=_config(bins={"petri": _PETRI_BIN}))
    _write(root=root, relative=_GROUP_VARS_RELATIVE, text=_group_vars(declared=[]))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["bin-names-no-declared-path"]
    assert run.events[0]["declared"] == []


def test_the_reader_takes_only_the_paths_inside_the_builds_block(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `path:` key of another group value is not a declared build path.

    The inventory file is shared with every other role's group values, so a reader
    that took every `path:` in it would accept a `bin` the `fabro_client` role never
    stages — the quietest way for this check to certify the wrong file. The arm also
    carries a commented-out entry and a quoted value, because both appear in real
    inventories and only one of them declares anything.
    """
    root = tmp_path
    _write(root=root, relative=_CONFIG_RELATIVE, text=_config(bins={"petri": _PETRI_BIN}))
    _write(
        root=root,
        relative=_GROUP_VARS_RELATIVE,
        text=(
            "---\n"
            "fabro_client_builds:\n"
            f"  # - path: {_PETRI_BIN}\n"
            '  - path: "/synthetic-dev-host/clients/quoted/fabro"\n'
            "    source: /control-node/staged/0/fabro\n"
            f"    sha256: {'0' * 64}\n"
            "\n"
            "some_other_role_value:\n"
            f"  path: {_PETRI_BIN}\n"
        ),
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["bin-names-no-declared-path"]
    assert run.events[0]["declared"] == ["/synthetic-dev-host/clients/quoted/fabro"], (
        "the quoted entry inside the block is the ONE declared path: the commented "
        "entry declares nothing and the trailing group value's `path:` belongs to "
        "another role"
    )


def test_a_dispatcher_block_of_an_unexpected_shape_yields_no_bin_rather_than_an_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `dispatcher` whose factories are not a mapping of mappings declares no bin.

    The reader WALKS the whole document, so it meets every mapping in it and cannot
    assume the one named `dispatcher` has the shape the orchestrator gives it: a
    half-written edit, a different plugin's own `dispatcher` key, or a factory
    carried as a bare string all reach this code. Each must read as "this declares
    no bin" — which is VACUOUS and says so — rather than raising, because a
    traceback out of a check is indistinguishable at the aggregate from a
    violation, and the operator would go looking for a routing fault that is not
    there.
    """
    root = tmp_path
    _write(
        root=root,
        relative=_CONFIG_RELATIVE,
        text=(
            "{\n"
            '  "a-plugin": { "dispatcher": { "factories": "not-a-mapping" } },\n'
            '  "another-plugin": { "dispatcher": { "factories": { "legacy": "a-bare-string" } } },\n'
            '  "a-third": { "dispatcher": "not-a-mapping-either" }\n'
            "}\n"
        ),
    )
    _write(root=root, relative=_GROUP_VARS_RELATIVE, text=_group_vars(declared=[_PETRI_BIN]))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0, run.events
    assert _kinds(run=run) == []
    assert _verdicts(run=run) == ["vacuous"]


def test_a_factory_that_declares_no_bin_contributes_none_beside_one_that_does(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A factory mapping without a `bin` is skipped, and its sibling's `bin` still counts.

    `bin` is optional on a factory entry, so a registry-backed entry that names none
    is the ordinary shape, not a malformed one. It must contribute no finding, while
    the sibling's undeclared `bin` is still refused. A reader that stopped at the
    first entry carrying no `bin` would pass this tree for the wrong reason.
    """
    root = tmp_path
    _write(
        root=root,
        relative=_CONFIG_RELATIVE,
        text=(
            "{\n"
            '  "livespec-orchestrator-beads-fabro": { "dispatcher": { "factories": {\n'
            '    "legacy": { "registry": true },\n'
            f'    "petri": {{ "registry": true, "bin": "{_PETRI_BIN}" }}\n'
            "  } } }\n"
            "}\n"
        ),
    )
    _write(root=root, relative=_GROUP_VARS_RELATIVE, text=_group_vars(declared=[_LEGACY_BIN]))
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _kinds(run=run) == ["bin-names-no-declared-path"]
    assert run.events[0]["factory"] == "petri"
