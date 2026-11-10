"""Production sources: claims are claims, serving versions are host reads, never receipts."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_fleet_sources import (
    core_manifest_reader,
    host_serving_reader,
    installed_controller,
    load_claims,
)

CLAIM = {
    "repository": "example/tooling",
    "surface": "Pre-push",
    "disposition": "implemented",
    "manifest_sha256": "a" * 64,
    "source_path": "installed/component.py",
    "release_build": "1.2.3",
    "proof_ref": "independent-host-proof:receipt-1",
    "owner": "controller-owner",
    "incident_item": "incident-1",
    "cumulative_scope": "b" * 64,
    "normal_factory_proof": "factory:scope",
}


def _write(*, tmp_path: Path, document: object) -> Path:
    path = tmp_path / "claims.json"
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_an_absent_claims_file_holds_no_claims_and_a_valid_one_never_carries_serving() -> None:
    assert load_claims(path=Path("/nonexistent/claims.json")) == Success(())


def test_valid_claims_load_with_an_empty_serving_build(tmp_path: Path) -> None:
    path = _write(
        tmp_path=tmp_path,
        document={"schema": 1, "evidence": [CLAIM, {**CLAIM, "reason": "because"}]},
    )
    claims = load_claims(path=path).unwrap()
    assert [claim.surface for claim in claims] == ["Pre-push", "Pre-push"]
    assert [claim.serving_build for claim in claims] == ["", ""]
    assert [claim.reason for claim in claims] == ["", "because"]
    assert claims[0].release_build == "1.2.3"


@pytest.mark.parametrize(
    "document",
    [
        {"schema": 2, "evidence": []},
        {"schema": 1},
        ["not", "an", "object"],
        {"schema": 1, "evidence": ["not-an-object"]},
        {"schema": 1, "evidence": [{**CLAIM, "serving_build": "1.2.3"}]},
        {"schema": 1, "evidence": [{**CLAIM, "owner": 7}]},
        {"schema": 1, "evidence": [{**CLAIM, "reason": 7}]},
        {"schema": 1, "evidence": [{k: v for k, v in CLAIM.items() if k != "owner"}]},
    ],
)
def test_malformed_claims_or_a_caller_supplied_serving_build_are_refused(
    tmp_path: Path, document: object
) -> None:
    assert isinstance(load_claims(path=_write(tmp_path=tmp_path, document=document)), Failure)


def test_unparseable_claims_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "claims.json"
    _ = path.write_text("{", encoding="utf-8")
    assert isinstance(load_claims(path=path), Failure)


def _answer(*, stdout: str = "", returncode: int = 0) -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=returncode, stdout=stdout, stderr=""))


def test_core_manifest_reader_reads_core_master_afresh_each_call() -> None:
    calls: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        calls.append(args)
        return _answer(stdout="manifest-bytes")

    read = core_manifest_reader(owner="example", run=run)
    assert read() == "manifest-bytes"
    assert read() == "manifest-bytes"
    assert len(calls) == 4
    assert any("example/livespec.git" in part for part in calls[0])
    assert calls[1][-1] == "HEAD:.livespec-fleet-manifest.jsonc"


def test_core_manifest_reader_reports_an_unavailable_read_as_none() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    assert core_manifest_reader(owner="example", run=run)() is None


def _serving(
    *, outcome: CommandOutcome, controllers: Path | None, loaded: tuple[str, str] | None = None
) -> tuple[Callable[[str, str], str | None], list[list[str]]]:
    seen: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        seen.append(args)
        return outcome

    reader = host_serving_reader(
        projects_root=Path("/projects"),
        controller_config_root=controllers,
        run=run,
        load_controller=lambda config: loaded if config.name == "tooling.json" else None,
    )
    return reader, seen


def test_an_installed_consumers_serving_version_is_read_from_its_own_interpreter() -> None:
    reader, seen = _serving(outcome=_answer(stdout="1.2.3\n"), controllers=None)
    for capability in ("gate-readers", "templates", "driver-hooks", "recovery-authorization"):
        assert reader("example/tooling", capability) == "1.2.3"
    assert seen[0][0] == "/projects/tooling/.venv/bin/python"


@pytest.mark.parametrize(
    "outcome",
    [
        _answer(stdout="", returncode=1),
        _answer(stdout="\n"),
        IOFailure(InvocationNotPerformed(argv=("x",), kind=BINARY_ABSENT, detail="x")),
    ],
)
def test_an_unreadable_installed_version_is_unverified(outcome: CommandOutcome) -> None:
    reader, _ = _serving(outcome=outcome, controllers=None)
    assert reader("example/tooling", "gate-readers") is None


def test_an_unknown_capability_is_never_verified() -> None:
    reader, seen = _serving(outcome=_answer(stdout="1.2.3"), controllers=None)
    assert reader("example/tooling", "") is None
    assert not seen


def test_the_controllers_serving_version_comes_only_from_its_protected_installation() -> None:
    root = Path("/controllers")
    for controllers, loaded, expected in (
        (None, ("example/tooling", "rel-9"), None),
        (root, ("example/tooling", "rel-9"), "rel-9"),
        (root, ("example/elsewhere", "rel-9"), None),
        (root, None, None),
    ):
        reader, seen = _serving(
            outcome=_answer(stdout="1.2.3"), controllers=controllers, loaded=loaded
        )
        assert reader("example/tooling", "independent-controller") == expected
        assert not seen


def test_installed_controller_reports_repository_and_release_or_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = SimpleNamespace(repository="example/tooling", release="rel-9")

    def load_installed(_cls: type[ControllerInstallation], *, config: Path) -> object:
        _ = config
        return installed

    def load_nothing(_cls: type[ControllerInstallation], *, config: Path) -> None:
        _ = config

    monkeypatch.setattr(ControllerInstallation, "load", classmethod(load_installed))
    assert installed_controller(config=Path("c.json")) == ("example/tooling", "rel-9")
    monkeypatch.setattr(ControllerInstallation, "load", classmethod(load_nothing))
    assert installed_controller(config=Path("c.json")) is None
