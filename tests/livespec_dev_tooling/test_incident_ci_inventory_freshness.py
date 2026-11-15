"""The released adopter inventory is compared with each adopter's live default head."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULE = _ROOT / "livespec_dev_tooling" / "incident_ci_inventory_freshness.py"
_SCRIPT = _ROOT / "scripts" / "just" / "check-incident-ci-inventory-freshness.sh"


def test_a_changed_default_branch_names_its_source_head_and_member_difference(
    tmp_path: Path,
) -> None:
    assert _MODULE.is_file()
    freshness = importlib.import_module("livespec_dev_tooling.incident_ci_inventory_freshness")
    inventory = importlib.import_module("livespec_dev_tooling.incident_ci_inventory")
    committed = tmp_path / "thewoolleyman" / "adopter.json"
    committed.parent.mkdir()
    _ = committed.write_text(
        inventory.render_inventory(
            workflow=(
                "on: push\n"
                "jobs:\n"
                "  checks:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: just check-old\n"
            ),
            inventory="check-old # incident-timing: fast\n",
            source=inventory.InventorySource(repository="thewoolleyman/adopter", commit="a" * 40),
        ),
        encoding="utf-8",
    )
    finding = freshness.compare_entry(
        path=committed,
        snapshot=freshness.RepositorySnapshot(
            repository="thewoolleyman/adopter",
            head="b" * 40,
            workflow=(
                "on: push\n"
                "jobs:\n"
                "  checks:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: just check-new\n"
            ),
            inventory="check-new # incident-timing: slow\n",
        ),
    )

    assert finding == freshness.InventoryDifference(
        repository="thewoolleyman/adopter",
        recorded_source="a" * 40,
        current_head="b" * 40,
        added=("check-new",),
        removed=("check-old",),
        reclassified=(),
    )


def test_a_current_entry_reports_no_difference_and_a_wrong_repository_refuses(
    tmp_path: Path,
) -> None:
    assert _MODULE.is_file()
    freshness = importlib.import_module("livespec_dev_tooling.incident_ci_inventory_freshness")
    inventory = importlib.import_module("livespec_dev_tooling.incident_ci_inventory")
    entry = tmp_path / "owner" / "repo.json"
    entry.parent.mkdir()
    workflow = (
        "on: push\n"
        "jobs:\n"
        "  checks:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: just check-fast\n"
    )
    targets = "check-fast # incident-timing: fast\n"
    _ = entry.write_text(
        inventory.render_inventory(
            workflow=workflow,
            inventory=targets,
            source=inventory.InventorySource(repository="owner/repo", commit="c" * 40),
        ),
        encoding="utf-8",
    )
    snapshot = freshness.RepositorySnapshot(
        repository="owner/repo", head="c" * 40, workflow=workflow, inventory=targets
    )

    assert freshness.compare_entry(path=entry, snapshot=snapshot) is None

    wrong = freshness.RepositorySnapshot(
        repository="owner/other", head="c" * 40, workflow=workflow, inventory=targets
    )
    with pytest.raises(ValueError, match="records owner/repo, not owner/other") as refused:
        _ = freshness.compare_entry(path=entry, snapshot=wrong)
    assert str(refused.value) == f"{entry} records owner/repo, not owner/other"


def test_a_timing_change_is_reported_as_a_reclassification(tmp_path: Path) -> None:
    assert _MODULE.is_file()
    freshness = importlib.import_module("livespec_dev_tooling.incident_ci_inventory_freshness")
    inventory = importlib.import_module("livespec_dev_tooling.incident_ci_inventory")
    entry = tmp_path / "owner" / "repo.json"
    entry.parent.mkdir()
    workflow = (
        "on: push\n"
        "jobs:\n"
        "  checks:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: just check-fast\n"
    )
    _ = entry.write_text(
        inventory.render_inventory(
            workflow=workflow,
            inventory="check-fast # incident-timing: fast\n",
            source=inventory.InventorySource(repository="owner/repo", commit="d" * 40),
        ),
        encoding="utf-8",
    )

    difference = freshness.compare_entry(
        path=entry,
        snapshot=freshness.RepositorySnapshot(
            repository="owner/repo",
            head="e" * 40,
            workflow=workflow,
            inventory="check-fast # incident-timing: slow\n",
        ),
    )

    assert difference is not None
    assert difference.reclassified == ("check-fast: fast -> slow",)


def test_every_committed_entry_is_audited_and_rendered_with_its_two_commits(
    tmp_path: Path,
) -> None:
    assert _MODULE.is_file()
    freshness = importlib.import_module("livespec_dev_tooling.incident_ci_inventory_freshness")
    inventory = importlib.import_module("livespec_dev_tooling.incident_ci_inventory")
    entries = tmp_path / "entries"
    workflow = (
        "on: push\n"
        "jobs:\n"
        "  checks:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: just ${{ matrix.target }}\n"
    )
    for repository, commit, target in (
        ("owner/current", "f" * 40, "check-current"),
        ("owner/stale", "a" * 40, "check-old"),
    ):
        entry = entries / f"{repository}.json"
        entry.parent.mkdir(parents=True, exist_ok=True)
        _ = entry.write_text(
            inventory.render_inventory(
                workflow=workflow.replace("${{ matrix.target }}", target),
                inventory=f"{target} # incident-timing: fast\n",
                source=inventory.InventorySource(repository=repository, commit=commit),
            ),
            encoding="utf-8",
        )

    snapshots = {
        "owner/current": freshness.RepositorySnapshot(
            repository="owner/current",
            head="f" * 40,
            workflow=workflow.replace("${{ matrix.target }}", "check-current"),
            inventory="check-current # incident-timing: fast\n",
        ),
        "owner/stale": freshness.RepositorySnapshot(
            repository="owner/stale",
            head="b" * 40,
            workflow=workflow.replace("${{ matrix.target }}", "check-new"),
            inventory="check-new # incident-timing: slow\n",
        ),
    }
    readings = freshness.audit_entries(directory=entries, read_snapshot=snapshots.__getitem__)

    assert readings == (
        freshness.InventoryCurrent(
            repository="owner/current", recorded_source="f" * 40, current_head="f" * 40
        ),
        freshness.InventoryDifference(
            repository="owner/stale",
            recorded_source="a" * 40,
            current_head="b" * 40,
            added=("check-new",),
            removed=("check-old",),
            reclassified=(),
        ),
    )
    assert freshness.render_report(readings=readings) == (
        f"current\towner/current\trecorded_source={'f' * 40}\tcurrent_head={'f' * 40}",
        f"stale\towner/stale\trecorded_source={'a' * 40}\tcurrent_head={'b' * 40}",
        "added\towner/stale\tcheck-new",
        "removed\towner/stale\tcheck-old",
    )


def test_the_entry_command_refuses_a_stale_render_and_the_sweep_invokes_it_for_every_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _MODULE.is_file()
    assert _SCRIPT.is_file()
    freshness = importlib.import_module("livespec_dev_tooling.incident_ci_inventory_freshness")
    inventory = importlib.import_module("livespec_dev_tooling.incident_ci_inventory")
    entry = tmp_path / "entry.json"
    workflow = tmp_path / "ci.yml"
    targets = tmp_path / "check-targets.txt"
    _ = entry.write_text(
        inventory.render_inventory(
            workflow="on: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - run: just check-old\n",
            inventory="check-old # incident-timing: fast\n",
            source=inventory.InventorySource(repository="owner/repo", commit="a" * 40),
        ),
        encoding="utf-8",
    )
    _ = workflow.write_text(
        "on: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - run: just check-new\n",
        encoding="utf-8",
    )
    _ = targets.write_text("check-new # incident-timing: slow\n", encoding="utf-8")

    assert (
        freshness.main(
            argv=(
                str(entry),
                "owner/repo",
                "b" * 40,
                str(workflow),
                str(targets),
            )
        )
        == 1
    )
    assert capsys.readouterr().out.splitlines() == [
        f"stale\towner/repo\trecorded_source={'a' * 40}\tcurrent_head={'b' * 40}",
        "added\towner/repo\tcheck-new",
        "removed\towner/repo\tcheck-old",
    ]
    _ = workflow.write_text(
        "on: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - run: just check-old\n",
        encoding="utf-8",
    )
    _ = targets.write_text("check-old # incident-timing: fast\n", encoding="utf-8")
    assert (
        freshness.main(
            argv=(
                str(entry),
                "owner/repo",
                "a" * 40,
                str(workflow),
                str(targets),
            )
        )
        == 0
    )
    assert capsys.readouterr().out == (
        f"current\towner/repo\trecorded_source={'a' * 40}\tcurrent_head={'a' * 40}\n"
    )
    script = _SCRIPT.read_text(encoding="utf-8")
    assert "find livespec_dev_tooling/data/incident-ci-inventory -type f -name '*.json'" in script
    assert "python -m livespec_dev_tooling.incident_ci_inventory_freshness" in script
