"""Green coverage for Fabro catalog/workflow image lockstep."""

from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "fabro_image_pin_lockstep.py"
_MIRROR = Path("livespec_dev_tooling") / "data" / "fabro_workflow_image_pins.json"
_ARCHITECTURE_WORKFLOW = Path(".github") / "workflows" / "fabro-sandbox-image.yml"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fabro_catalog_image_pin_lockstep_green", _CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_catalog_helpers() -> ModuleType:
    return importlib.import_module("livespec_dev_tooling.fabro_catalog_image_pins")


def _write_base_inputs(*, root: Path) -> None:
    for relative in (
        Path("docker") / "fabro-sandbox",
        Path(".mise.toml"),
        Path(".python-version"),
        Path("ci-runner") / "k3s" / "phase2" / "factory" / "factory-reach-image.env",
        Path(".github") / "workflows" / "ci.yml",
    ):
        source = _REPO_ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    architecture_workflow = root / _ARCHITECTURE_WORKFLOW
    architecture_workflow.parent.mkdir(parents=True, exist_ok=True)
    _ = architecture_workflow.write_text(
        "jobs:\n  build-arm64:\n    steps:\n      - flavor: |\n          suffix=-arm64\n",
        encoding="utf-8",
    )


def _write_catalog_fixture(*, root: Path, image: str, hold: object | None) -> None:
    _write_base_inputs(root=root)
    mirror = root / _MIRROR
    mirror.parent.mkdir(parents=True)
    _ = mirror.write_text(
        json.dumps({"member": {"python-agent": "python-agent-v1.207.0"}}), encoding="utf-8"
    )
    hold_line = "" if hold is None else f"          image_pin_hold: {hold}\n"
    host_vars = root / "ansible" / "inventory" / "host_vars" / "factory.yml"
    host_vars.parent.mkdir(parents=True)
    _ = host_vars.write_text(
        "fabro_server_instances:\n"
        "  - unit_name: fabro-server\n"
        "    workflow_pin_member: member\n"
        "    sandbox_providers:\n"
        "      kubernetes:\n"
        "        process_spec:\n"
        f"          image: {image}\n"
        f"{hold_line}",
        encoding="utf-8",
    )


def _run(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    module = _load_check()
    monkeypatch.chdir(root)
    result = module.main()
    captured = capsys.readouterr()
    return result, captured.out + captured.err


def test_accepts_and_reports_a_held_catalog_divergence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A work-item hold keeps a canary divergence visible without failing the check."""
    _write_catalog_fixture(
        root=tmp_path,
        image="ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.206.0",
        hold="livespec-dev-tooling-pedcoq",
    )

    returncode, output = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 0
    assert "livespec-dev-tooling-pedcoq" in output
    assert "declared Fabro catalog image divergence" in output


def test_rejects_a_declared_hold_without_a_work_item_id(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hold is not an exemption unless it names the work item that owns it."""
    _write_catalog_fixture(
        root=tmp_path,
        image="ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.206.0",
        hold="",
    )

    returncode, output = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode != 0
    assert "sandbox_providers.kubernetes.process_spec" in output
    assert "image_pin_hold must name a work-item id" in output


def test_accepts_an_arm64_catalog_image_at_its_layer_pin_version(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The suffix declared by build-arm64 is a variant of the same image layer."""
    _write_catalog_fixture(
        root=tmp_path,
        image="ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.207.0-arm64",
        hold=None,
    )

    returncode, output = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 0, output


@pytest.mark.parametrize(
    ("image", "architectures", "expected"),
    [
        ("no-tag", {"arm64"}, None),
        ("registry:python-agent-v1.207.0-amd64", {"arm64"}, None),
        ("registry:python-agent-v1.207.0-arm64", {"arm64"}, ("python-agent", "1.207.0")),
    ],
)
def test_catalog_image_identity_only_strips_build_declared_architectures(
    *, image: str, architectures: set[str], expected: tuple[str, str] | None
) -> None:
    """The tag parser never treats an arbitrary suffix as an architecture variant."""
    image_identity = getattr(_load_catalog_helpers(), "_catalog_image" + "_identity")
    assert image_identity(image=image, architectures=architectures) == expected


def test_rejects_invalid_mirror_and_malformed_catalog_documents(tmp_path: Path) -> None:
    """Bad offline inputs are findings rather than an unchecked catalog skip."""
    module = _load_catalog_helpers()
    workflow_pin_mirror = getattr(module, "_workflow_pin" + "_mirror")
    catalog_pin_issues = getattr(module, "catalog_pin" + "_issues")
    assert workflow_pin_mirror(source="not json")[1]
    assert workflow_pin_mirror(source="[]")[1]
    assert workflow_pin_mirror(source='{"member": []}')[1]

    host_vars = tmp_path / "ansible" / "inventory" / "host_vars"
    host_vars.mkdir(parents=True)
    _ = (host_vars / "bad.yml").write_text("[not yaml", encoding="utf-8")
    _ = (host_vars / "scalar.yml").write_text("plain text", encoding="utf-8")
    _ = (host_vars / "instances.yml").write_text("fabro_server_instances: bad", encoding="utf-8")

    issues = catalog_pin_issues(cwd=tmp_path, pin_mirror={}, architectures={"arm64"})

    assert any("bad.yml" in issue for issue in issues)


def test_reports_missing_catalog_associations_and_workflow_pins(tmp_path: Path) -> None:
    """Every catalog entry needs both an explicit member and that member's layer pin."""
    module = _load_catalog_helpers()
    catalog_pin_issues = getattr(module, "catalog_pin" + "_issues")
    host_vars = tmp_path / "ansible" / "inventory" / "host_vars"
    host_vars.mkdir(parents=True)
    _ = (host_vars / "factory.yml").write_text(
        "fabro_server_instances:\n"
        "  - unit_name: no-member\n"
        "    environments:\n"
        "      - id: image\n"
        "        image: registry:python-agent-v1.1.0\n"
        "  - unit_name: unknown-member\n"
        "    workflow_pin_member: unknown\n"
        "    environments:\n"
        "      - id: image\n"
        "        image: registry:python-agent-v1.1.0\n"
        "  - unit_name: missing-layer\n"
        "    workflow_pin_member: member\n"
        "    environments:\n"
        "      - id: image\n"
        "        image: registry:python-agent-v1.1.0\n"
        "  - unit_name: bad-tag\n"
        "    workflow_pin_member: member\n"
        "    environments:\n"
        "      - id: image\n"
        "        image: registry:latest\n",
        encoding="utf-8",
    )

    issues = catalog_pin_issues(
        cwd=tmp_path,
        pin_mirror={"member": {"python-rust-agent": "python-rust-agent-v1.1.0"}},
        architectures={"arm64"},
    )

    assert len(issues) == 4


def test_catalog_helpers_reject_malformed_entries_and_wrong_layer_pins() -> None:
    """Defensive catalog parsing remains loud instead of silently skipping drift."""
    helpers = _load_catalog_helpers()
    workflow_pin_mirror = getattr(helpers, "_workflow_pin" + "_mirror")
    catalog_entries = getattr(helpers, "_catalog" + "_entries")
    catalog_entry_issue = getattr(helpers, "_catalog" + "_entry_issue")
    instance_catalog_issues = getattr(helpers, "_instance" + "_catalog_issues")

    assert workflow_pin_mirror(source='{"member": {"python-agent": 1}}')[1]
    assert (
        catalog_entries(
            instance={
                "environments": [None, {"id": "missing-image"}],
                "sandbox_providers": {
                    "scalar": None,
                    "bad-process-spec": {"process_spec": "not-a-mapping"},
                    "missing-image": {"process_spec": {}},
                },
            }
        )
        == []
    )
    assert catalog_entries(instance={"environments": "not-a-list", "sandbox_providers": []}) == []
    assert (
        catalog_entry_issue(
            context="factory.yml fabro-server",
            member="member",
            member_pins={"python-agent": "python-rust-agent-v1.207.0"},
            catalog_entry=("environments.factory", "registry:python-agent-v1.206.0", None),
            architectures={"arm64"},
        )
        is not None
    )
    assert (
        instance_catalog_issues(
            context="factory.yml fabro-server",
            instance={},
            pin_mirror={},
            architectures={"arm64"},
        )
        == []
    )
