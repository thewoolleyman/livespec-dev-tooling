"""Integration coverage for filing root fixes from flake-retry records."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

_REPO_ROOT = Path(__file__).resolve().parents[2]


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
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    filed = filer.file_root_fixes(repo_root=tmp_path, runner=runner)

    assert filed == (nodeid_without_fix,)
    assert [call[:3] for call in calls] == [
        ["bd", "list", "--status"],
        ["bd", "create", f"root-fix: {nodeid_without_fix}"],
    ]


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
        return Success(GateCommandResult(returncode=0, stdout="[]", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner) == (nodeid,)

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

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner) == ()
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
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    assert filer.file_root_fixes(repo_root=tmp_path, runner=runner) == (nodeid,)
    assert calls[-1][2] == f"root-fix: {nodeid}"


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
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner)


def test_the_reader_refuses_a_non_array_ledger_response(*, tmp_path: Path) -> None:
    """The ledger's JSON shape is checked before deduplication starts."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"

    def runner(*, argv: list[str], cwd: Path, **_: object) -> Success[GateCommandResult]:
        del argv, cwd
        return Success(GateCommandResult(returncode=0, stdout="{}", stderr=""))

    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(TypeError):
        _ = filer.file_root_fixes(repo_root=tmp_path, runner=runner)


def _one_filed_nodeid(**_: object) -> tuple[str, ...]:
    return ("test.py::test_flaky",)


def test_the_host_cli_reports_the_nodeids_it_files(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The host invocation uses the reader and returns a successful exit code."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_filer.py"
    assert module_path.is_file(), "the host-side flake reader must be shipped"
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")
    monkeypatch.setattr(filer, "file_root_fixes", _one_filed_nodeid)

    assert filer.main(argv=["--repo-root", "/tmp/retry-reader"]) == 0
