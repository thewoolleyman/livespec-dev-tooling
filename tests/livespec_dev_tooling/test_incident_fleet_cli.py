"""The runnable fleet audit command and the one incident enablement step."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from livespec_dev_tooling._incident_fleet_types import FleetAudit
from livespec_dev_tooling.incident_fleet_audit import SURFACES
from livespec_dev_tooling.incident_fleet_cli import enable_repository, main

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
DIGEST = hashlib.sha256(MANIFEST.encode()).hexdigest()
GUIDANCE = ("Agent tool and stop guards", "Operator factory routing")


def _claim(*, repository: str, surface: str) -> dict[str, str]:
    notes = repository.endswith("notes")
    return {
        "repository": repository,
        "surface": surface,
        "disposition": "implemented",
        "manifest_sha256": DIGEST,
        "source_path": "installed/component.py",
        "release_build": "1.0.0",
        "proof_ref": "independent-host-proof:receipt-1",
        "owner": "controller-owner",
        "incident_item": "" if notes else "incident-1",
        "cumulative_scope": "" if notes else "b" * 64,
        "normal_factory_proof": "" if notes else "factory:scope",
    }


def _write_claims(*, root: Path) -> None:
    claims = [_claim(repository="example/tooling", surface=s) for s in SURFACES] + [
        _claim(repository="example/notes", surface=s) for s in GUIDANCE
    ]
    path = root / "config" / "incident-fleet-evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps({"schema": 1, "evidence": claims}), encoding="utf-8")


def _serving(*, unreadable: str = "") -> Callable[[str, str], str | None]:
    return lambda _repository, capability: None if capability == unreadable else "1.0.0"


def _run(
    *,
    tmp_path: Path,
    argv: list[str],
    manifest: str | None = MANIFEST,
    unreadable: str = "",
    claims: bool = True,
) -> int:
    root = tmp_path / "livespec-dev-tooling"
    root.mkdir(exist_ok=True)
    if claims:
        _write_claims(root=root)
    return main(
        argv=argv,
        root=root,
        projects_root=tmp_path,
        state_dir=tmp_path / "state",
        read_manifest=lambda: manifest,
        read_serving=_serving(unreadable=unreadable),
    )


def test_audit_prints_every_row_the_ready_list_and_exits_zero_when_all_classified(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path=tmp_path, argv=["audit"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len([line for line in lines if line.startswith("row\t")]) == len(SURFACES) + 37
    assert "row\texample/tooling\tPre-push\timplemented\t1.0.0" in lines
    assert "ready\texample/tooling" in lines


def test_audit_exits_non_zero_and_names_the_consumer_lacking_controller_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = _run(tmp_path=tmp_path, argv=["audit"], unreadable="independent-controller")
    lines = capsys.readouterr().out.splitlines()
    assert status != 0
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in lines
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller"
        in lines
    )
    assert "ready\t-" in lines


def test_audit_of_an_unauthenticated_manifest_lists_zero_ready_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path=tmp_path, argv=["audit"], manifest=None) != 0
    out = capsys.readouterr().out
    assert "unauthenticated" in out
    assert "ready\t-" in out


def test_unreadable_claims_are_reported_and_fail_the_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "livespec-dev-tooling"
    (root / "config").mkdir(parents=True)
    _ = (root / "config" / "incident-fleet-evidence.json").write_text("{", encoding="utf-8")
    assert _run(tmp_path=tmp_path, argv=["audit"], claims=False) != 0
    assert "finding\tevidence claims:" in capsys.readouterr().out


def test_enablement_enables_a_repository_on_the_fresh_ready_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path=tmp_path, argv=["enable", "example/tooling"]) == 0
    assert capsys.readouterr().out == "enabled\texample/tooling\n"
    record = json.loads((tmp_path / "state" / "example__tooling.json").read_text(encoding="utf-8"))
    assert record == {"repository": "example/tooling", "manifest_sha256": DIGEST}


def test_enablement_refuses_a_repository_missing_from_the_ready_list_and_enables_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = _run(
        tmp_path=tmp_path, argv=["enable", "example/tooling"], unreadable="independent-controller"
    )
    err = capsys.readouterr().err
    assert status != 0
    assert "example/tooling" in err
    assert "independent-controller" in err
    assert not (tmp_path / "state").exists()


def test_enablement_refuses_an_unknown_repository_and_an_unauthenticated_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path=tmp_path, argv=["enable", "example/foreign"]) != 0
    assert "example/foreign" in capsys.readouterr().err
    assert _run(tmp_path=tmp_path, argv=["enable", "example/tooling"], manifest=None) != 0
    assert not (tmp_path / "state").exists()


def test_enable_repository_takes_the_audit_it_is_given_only_by_its_ready_list() -> None:
    audit = FleetAudit(
        manifest_sha256="a" * 64, rows=(), findings=("x/y: gap",), ready_repositories=()
    )
    status, line = enable_repository(repository="x/y", audit=audit, state_dir=Path("/nonexistent"))
    assert status == 1
    assert line == "refused\tx/y: missing evidence: x/y: gap"


def test_the_justfile_ships_the_operator_recipes() -> None:
    text = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    assert "\nincident-fleet-audit:\n" in text
    assert "livespec_dev_tooling.incident_fleet_cli audit" in text
    assert "\nincident-enable repository:\n" in text
    assert 'livespec_dev_tooling.incident_fleet_cli enable "$1"' in text


def _fixture_host(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, core_readable: bool) -> Path:
    """A fake git that serves core's manifest, and fake installed consumer interpreters."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture = tmp_path / "manifest.jsonc"
    _ = fixture.write_text(MANIFEST, encoding="utf-8")
    git = bin_dir / "git"
    show = f'cat "{fixture}"; exit 0' if core_readable else "exit 128"
    script = "\n".join(
        (
            "#!/bin/sh",
            'case " $* " in',
            '  *" clone "*) for last; do :; done; mkdir -p "$last"; exit 0;;',
            f"  *' show '*) {show};;",
            "esac",
            "exit 1",
            "",
        )
    )
    _ = git.write_text(script, encoding="utf-8")
    git.chmod(0o755)
    for name in ("tooling", "notes"):
        interpreter = tmp_path / name / ".venv" / "bin" / "python"
        interpreter.parent.mkdir(parents=True)
        _ = interpreter.write_text("#!/bin/sh\necho 1.0.0\n", encoding="utf-8")
        interpreter.chmod(0o755)
    root = tmp_path / "livespec-dev-tooling"
    root.mkdir()
    _write_claims(root=root)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LIVESPEC_INCIDENT_CONTROLLER_CONFIG_ROOT", str(tmp_path / "controllers"))
    return root


def _production(*, tmp_path: Path, root: Path, argv: list[str]) -> int:
    """Run with the production readers: real git transport and real interpreter probes."""
    return main(argv=argv, root=root, projects_root=tmp_path, state_dir=tmp_path / "state")


@pytest.mark.integration
def test_with_production_readers_an_unreadable_controller_is_left_out_named_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fixture_host(tmp_path=tmp_path, monkeypatch=monkeypatch, core_readable=True)
    assert _production(tmp_path=tmp_path, root=root, argv=["audit"]) != 0
    out = capsys.readouterr().out
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in out
    assert "row\texample/tooling\tPre-push\timplemented\t1.0.0" in out
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller" in out
    )
    assert "ready\t-" in out
    assert _production(tmp_path=tmp_path, root=root, argv=["enable", "example/tooling"]) != 0
    err = capsys.readouterr().err
    assert "example/tooling" in err
    assert "independent-controller" in err
    assert not (tmp_path / "state").exists()


@pytest.mark.integration
def test_with_production_readers_an_unauthenticated_manifest_lists_zero_ready_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fixture_host(tmp_path=tmp_path, monkeypatch=monkeypatch, core_readable=False)
    assert _production(tmp_path=tmp_path, root=root, argv=["audit"]) != 0
    out = capsys.readouterr().out
    assert "unauthenticated" in out
    assert "ready\t-" in out
