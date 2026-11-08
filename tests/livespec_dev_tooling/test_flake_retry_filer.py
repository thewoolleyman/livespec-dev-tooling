"""Integration coverage for filing root fixes from flake-retry records."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = Path("/plugins/livespec-orchestrator-beads-fabro/abc123")
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"


def _ok(*, stdout: str = "") -> Success[GateCommandResult]:
    return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _write_records(*, repo_root: Path, nodeids: tuple[str, ...]) -> None:
    records = repo_root / "tmp" / "flake-retries"
    _ = records.mkdir(parents=True)
    _ = (records / "retries.jsonl").write_text(
        "".join(json.dumps({"nodeid": nodeid}) + "\n" for nodeid in nodeids),
        encoding="utf-8",
    )


def test_the_reader_skips_an_open_root_fix_and_files_the_other_nodeid(*, tmp_path: Path) -> None:
    """Two retry records with one open root fix create precisely one new item."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"

    records = tmp_path / "tmp" / "flake-retries"
    _ = records.mkdir(parents=True)
    nodeid_with_fix = "tests/test_example.py::test_already_tracked"
    nodeid_without_fix = "tests/test_example.py::test_needs_root_fix"
    _ = (records / "retries.jsonl").write_text(
        "".join(
            json.dumps({"attempts": 2, "nodeid": nodeid, "outcome": "passed"}) + "\n"
            for nodeid in (nodeid_with_fix, nodeid_without_fix)
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        calls.append(argv)
        if argv[1] == "list":
            return Success(
                GateCommandResult(
                    returncode=0,
                    stdout=json.dumps(
                        [
                            {
                                "status": "ready",
                                "title": f"root-fix: {nodeid_with_fix}",
                            }
                        ]
                    ),
                    stderr="",
                )
            )
        if argv[1] == "create":
            return _ok(stdout=json.dumps({"id": "dt-new"}))
        return _ok()

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    filed = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)

    assert filed == (nodeid_without_fix,)
    assert [call[:3] for call in calls] == [
        ["bd", "list", "--status"],
        ["bd", "create", f"root-fix: {nodeid_without_fix}"],
        ["python3", "-c", calls[2][2]],
    ]
    assert "--json" in calls[1]
    assert "apply_intake_dor" in calls[2][2]
    assert calls[2][3:] == [str(_PLUGIN_ROOT), "dt-new"]


def test_a_filed_root_fix_carries_a_definition_of_done_naming_the_nodeid(*, tmp_path: Path) -> None:
    """The factory can dispatch the item because its description grades the retried node id."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"
    records = tmp_path / "tmp" / "flake-retries"
    _ = records.mkdir(parents=True)
    nodeid = "tests/test_example.py::test_needs_root_fix"
    _ = (records / "retries.jsonl").write_text(
        json.dumps({"nodeid": nodeid}) + "\n", encoding="utf-8"
    )
    calls: list[list[str]] = []

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        calls.append(argv)
        return _ok(stdout=json.dumps({"id": "dt-new"}) if argv[1] == "create" else "[]")

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT) == (
        nodeid,
    )

    create = next(call for call in calls if call[1] == "create")
    description = create[create.index("--description") + 1]
    assert description == (
        f"Root-cause fix for retried test node id: {nodeid}\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        "References: ## Testing approach\n"
        "\n"
        f"- Test node id `{nodeid}` passes on its first attempt in a run of the "
        "repository's test suite, with no flake-retry record written for it.\n"
    )


def test_the_reader_returns_cleanly_when_no_retry_records_exist(*, tmp_path: Path) -> None:
    """No retry records are a successful no-op after the live ledger is read."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"
    calls: list[list[str]] = []

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        calls.append(argv)
        return Success(GateCommandResult(returncode=0, stdout="[]", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT) == ()
    assert calls == [["bd", "list", "--status", "all", "--json"]]


def test_the_reader_ignores_closed_and_non_root_fix_ledger_rows(*, tmp_path: Path) -> None:
    """Only a non-closed root-fix title de-duplicates a retry node id."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"
    records = tmp_path / "tmp" / "flake-retries"
    _ = records.mkdir(parents=True)
    nodeid = "tests/test_example.py::test_closed_fix"
    _ = (records / "retries.jsonl").write_text(
        json.dumps({"nodeid": nodeid}) + "\n", encoding="utf-8"
    )
    calls: list[list[str]] = []

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        calls.append(argv)
        if argv[1] == "list":
            return Success(
                GateCommandResult(
                    returncode=0,
                    stdout=json.dumps(
                        [
                            {"status": "closed", "title": f"root-fix: {nodeid}"},
                            {"status": "ready", "title": "ordinary task"},
                            [],
                        ]
                    ),
                    stderr="",
                )
            )
        if argv[1] == "create":
            return _ok(stdout=json.dumps([{"id": "dt-new"}]))
        return _ok()

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT) == (
        nodeid,
    )
    assert calls[1][2] == f"root-fix: {nodeid}"


@pytest.mark.parametrize(
    "result",
    [
        Failure(GateCommandNotRun(argv=("bd",), detail="not on PATH")),
        Success(GateCommandResult(returncode=1, stdout="", stderr="refused")),
    ],
)
def test_the_reader_refuses_a_ledger_command_that_did_not_succeed(
    *, tmp_path: Path, result: object
) -> None:
    """A failed ledger query never reads as an empty list of existing root fixes."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"

    def runner(*, argv: list[str], cwd: Path, **_: object) -> object:
        del argv, cwd
        return result

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(OSError, match="^$"):
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)


def test_the_reader_refuses_a_non_array_ledger_response(*, tmp_path: Path) -> None:
    """The ledger's JSON shape is checked before deduplication starts."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del argv, cwd
        return Success(GateCommandResult(returncode=0, stdout="{}", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(TypeError):
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)


def _one_filed_nodeid(**_: object) -> tuple[str, ...]:
    return ("test.py::test_flaky",)


def _fixed_plugin_root(**_: object) -> Path:
    return _PLUGIN_ROOT


def test_the_host_cli_reports_the_nodeids_it_files(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The host invocation uses the reader and returns a successful exit code."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")
    monkeypatch.setattr(filer, "file_root_fixes", _one_filed_nodeid)
    monkeypatch.setattr(filer, "registered_plugin_root", _fixed_plugin_root)

    assert filer.main(argv=["--repo-root", "/tmp/retry-reader"]) == 0


def test_the_host_cli_marks_a_completed_reader_pass(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A timer invocation leaves durable evidence that the reader completed."""
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")
    monkeypatch.setattr(filer, "file_root_fixes", _one_filed_nodeid)
    monkeypatch.setattr(filer, "registered_plugin_root", _fixed_plugin_root)
    state_dir = tmp_path / "reader-state"

    assert (
        filer.main(argv=["--repo-root", str(tmp_path / "repo"), "--state-dir", str(state_dir)]) == 0
    )
    assert (state_dir / "last-successful-pass").is_file()


def test_the_host_cli_names_the_reader_and_age_when_its_pass_is_stale(
    *, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A separate health invocation makes a dead reader visible to operators."""
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")
    state_dir = tmp_path / "reader-state"
    _ = state_dir.mkdir()
    marker = state_dir / "last-successful-pass"
    _ = marker.touch()
    os.utime(marker, (0, 0))

    assert (
        filer.main(
            argv=[
                "--state-dir",
                str(state_dir),
                "--interval-seconds",
                "60",
                "--check-staleness",
            ]
        )
        == 1
    )
    output = capsys.readouterr().err
    assert "flake-retry-filer" in output
    assert "age_seconds" in output


def test_the_dev_host_role_arms_the_reader_and_its_staleness_signal() -> None:
    """The reader is an unattended host service, never a remembered manual command."""
    role = _REPO_ROOT / "ansible" / "roles" / "flake_retry_filer"
    tasks = (role / "tasks" / "main.yml").read_text(encoding="utf-8")
    reader_service = (role / "templates" / "livespec-flake-retry-filer.service.j2").read_text(
        encoding="utf-8"
    )
    staleness_service = (
        role / "templates" / "livespec-flake-retry-filer-staleness.service.j2"
    ).read_text(encoding="utf-8")

    assert "Enable and start the flake-retry filer timers" in tasks
    assert "/usr/local/bin/with-livespec-env.sh" in reader_service
    assert "--check-staleness" in staleness_service


def test_each_filed_root_fix_is_routed_through_intake_by_its_own_id(*, tmp_path: Path) -> None:
    """Every created item is triaged by the orchestrator, never left in backlog."""
    nodeids = ("tests/test_a.py::test_one", "tests/test_b.py::test_two")
    _write_records(repo_root=tmp_path, nodeids=nodeids)
    created: list[str] = []
    routed: list[str] = []

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        if argv[1] == "create":
            created.append(argv[2])
            return _ok(stdout=json.dumps({"id": f"dt-{len(created)}"}))
        if argv[1] == "-c":
            routed.append(argv[4])
        return _ok(stdout="[]")

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    filed = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)

    assert filed == nodeids
    assert routed == ["dt-1", "dt-2"]


@pytest.mark.parametrize("created_body", ["{}", "[]", '{"id": 7}', '"dt-1"'])
def test_the_reader_refuses_a_create_response_without_an_item_id(
    *, tmp_path: Path, created_body: str
) -> None:
    """An item whose id cannot be read cannot be triaged, so the filing stops loudly."""
    _write_records(repo_root=tmp_path, nodeids=("tests/test_a.py::test_one",))

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        return _ok(stdout=created_body if argv[1] == "create" else "[]")

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(TypeError):
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)


def test_the_reader_refuses_an_intake_routing_that_did_not_succeed(*, tmp_path: Path) -> None:
    """A refused triage is an error, not a silently backlogged root-fix item."""
    _write_records(repo_root=tmp_path, nodeids=("tests/test_a.py::test_one",))

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del cwd
        if argv[1] == "-c":
            return Success(GateCommandResult(returncode=1, stdout="", stderr="refused"))
        return _ok(stdout=json.dumps({"id": "dt-1"}) if argv[1] == "create" else "[]")

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(OSError, match="^$"):
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner, plugin_root=_PLUGIN_ROOT)


def _write_registry(*, path: Path, entries: dict[str, list[dict[str, str]]]) -> None:
    _ = path.write_text(json.dumps({"version": 2, "plugins": entries}), encoding="utf-8")


def test_the_registered_plugin_root_is_the_install_recorded_for_the_repository(
    *, tmp_path: Path
) -> None:
    """The orchestrator build is read from the host's plugin registry for this project."""
    registry = tmp_path / "installed_plugins.json"
    repo = tmp_path / "repo"
    _ = repo.mkdir()
    _write_registry(
        path=registry,
        entries={
            "livespec@livespec": [{"projectPath": str(repo), "installPath": "/wrong/core"}],
            _PLUGIN_KEY: [
                {"projectPath": str(tmp_path / "elsewhere"), "installPath": "/wrong/other"},
                {"projectPath": str(repo), "installPath": str(_PLUGIN_ROOT)},
            ],
        },
    )
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.registered_plugin_root(repo_root=repo, registry=registry) == _PLUGIN_ROOT


def test_the_registered_plugin_root_refuses_a_repository_with_no_install(*, tmp_path: Path) -> None:
    """Without a registered build the intake gate cannot run, so nothing is filed."""
    registry = tmp_path / "installed_plugins.json"
    _write_registry(path=registry, entries={_PLUGIN_KEY: []})
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(OSError, match="^$"):
        _ = filer.registered_plugin_root(repo_root=tmp_path, registry=registry)
