"""Unit coverage for the delegated gate Job authority-skip check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import delegated_job_authority_skip

__all__: list[str] = []

_LEVER = "LIVESPEC_FAIL_IF_DELEGATED_JOB_RUNS_AUTHORITY_MEMBERS"
_MEMBER = "check-ledger-thing"

_CHECK_RECIPE = (
    "check:\n"
    "    #!/usr/bin/env bash\n"
    '    read -ra skip_targets <<< "${SKIP_TARGETS:-}"\n'
    '    bash scripts/runner.sh "${skip_targets[@]}"\n'
    "\n"
    "check-skipping *skip_targets:\n"
    '    bash scripts/runner.sh "$@"\n'
    "\n"
    "check-pre-commit-gated-tree:\n"
    "    bash scripts/gated.sh\n"
    "\n"
    "check-pre-push:\n"
    "    bash scripts/gated.sh\n"
)
_NO_SKIP_READ_RECIPE = "check:\n    #!/usr/bin/env bash\n    bash scripts/runner.sh\n"
_UNHONOURED_GATED = "just check-skipping\n"
_INVENTORY = f"check-alpha\n{_MEMBER}  # authority: ledger\n"


def _repository(
    *,
    root: Path,
    pyproject: str = "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
    justfile: str | None = _CHECK_RECIPE,
    inventory: str | None = _INVENTORY,
    gated: str = _UNHONOURED_GATED,
) -> Path:
    """Lay out a consumer repository whose delegated Job runs `scripts/gated.sh`."""
    _ = (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    if justfile is not None:
        _ = (root / "justfile").write_text(justfile, encoding="utf-8")
    if inventory is not None:
        _ = (root / "check-targets.txt").write_text(inventory, encoding="utf-8")
    (root / "scripts").mkdir()
    _ = (root / "scripts" / "runner.sh").write_text("true\n", encoding="utf-8")
    _ = (root / "scripts" / "gated.sh").write_text(gated, encoding="utf-8")
    return root


def _run(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], armed: bool
) -> tuple[int, list[dict[str, object]]]:
    """Run `main` inside `root`; return its exit status and the findings it logged."""
    monkeypatch.chdir(root)
    monkeypatch.delenv(_LEVER, raising=False)
    if armed:
        monkeypatch.setenv(_LEVER, "true")
    status = delegated_job_authority_skip.main()
    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
    return status, [json.loads(line) for line in lines]


@pytest.mark.parametrize(
    ("pyproject", "inventory"),
    [
        ("[tool.livespec_dev_tooling]\ndelegated_pre_commit = false\n", _INVENTORY),
        ("[tool.livespec_dev_tooling]\ndelegated_pre_commit = 'yes'\n", _INVENTORY),
        ("not [toml", _INVENTORY),
        (
            "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\ngate_check_suite = 5\n",
            _INVENTORY,
        ),
        ("[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n", "check-alpha\n"),
        ("[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n", None),
    ],
)
def test_nothing_to_judge_passes_with_no_finding(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pyproject: str,
    inventory: str | None,
) -> None:
    """No enabled path, an unreadable opt-in or suite, no authority member, or no inventory reports nothing."""
    root = _repository(root=tmp_path, pyproject=pyproject, inventory=inventory)

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert (status, logged) == (0, [])


def test_pre_commit_bypass_names_path_job_recipe_and_member(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The finding carries the delegated path, the Job recipe, the member and the route."""
    root = _repository(root=tmp_path)

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert status == 1
    assert len(logged) == 1
    finding = logged[0]
    assert finding["level"] == "error"
    assert finding["delegated_path"] == "pre-commit"
    assert finding["job_recipe"] == "check-pre-commit-gated-tree"
    assert finding["member"] == _MEMBER
    assert finding["route"] == [
        "just check-pre-commit-gated-tree",
        "scripts/gated.sh",
        "just check-skipping",
        "scripts/runner.sh",
    ]


def test_unarmed_findings_are_warnings_and_do_not_fail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Warn-default: the same finding is logged at warning level and the check exits 0."""
    root = _repository(root=tmp_path)

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=False)

    assert status == 0
    assert [(entry["level"], entry["member"]) for entry in logged] == [("warning", _MEMBER)]


def test_pre_push_runs_the_declared_suite_and_pre_commit_replaces_its_last_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both paths enabled: each is traced over its own Job recipes."""
    root = _repository(
        root=tmp_path,
        pyproject=(
            "[tool.livespec_dev_tooling]\n"
            "delegated_pre_commit = true\n"
            "delegated_gate = true\n"
            'gate_check_suite = ["bootstrap", "hook_gate=1 check-pre-push"]\n'
        ),
    )

    _, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert [(entry["delegated_path"], entry["job_recipe"]) for entry in logged] == [
        ("pre-commit", "check-pre-commit-gated-tree"),
        ("pre-push", "check-pre-push"),
    ]


def test_the_shared_fall_through_suite_is_traced_when_none_is_declared(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An undeclared suite is the shared pre-push sequence, whose last step is `check-pre-push`."""
    root = _repository(
        root=tmp_path, pyproject="[tool.livespec_dev_tooling]\ndelegated_gate = true\n"
    )

    _, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert [(entry["delegated_path"], entry["job_recipe"]) for entry in logged] == [
        ("pre-push", "check-pre-push")
    ]


def test_a_route_that_reads_the_skip_variable_is_not_reported(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Job script that reads the list before reaching the runner draws no finding."""
    root = _repository(
        root=tmp_path,
        gated='read -ra mine <<< "${SKIP_TARGETS:-}"\njust check-skipping "${mine[@]}"\n',
    )

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert (status, logged) == (0, [])


def test_no_recognised_skip_variable_is_left_to_the_delegated_client(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The client refuses locally when the `check` recipe reads no skip list, so no Job exists."""
    root = _repository(root=tmp_path, justfile=_NO_SKIP_READ_RECIPE)

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert (status, logged) == (0, [])


@pytest.mark.parametrize("justfile", [None, "other:\n    true\n"])
def test_a_tree_with_no_check_recipe_is_reported_per_path(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    justfile: str | None,
) -> None:
    """Without a `check` recipe the client submits the Job skipping nothing; say so."""
    root = _repository(
        root=tmp_path,
        pyproject=(
            "[tool.livespec_dev_tooling]\n"
            "delegated_pre_commit = true\n"
            "delegated_gate = true\n"
        ),
        justfile=justfile,
    )

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert status == 1
    assert [entry["delegated_path"] for entry in logged] == ["pre-commit", "pre-push"]
    assert all("no `check` recipe" in str(entry["event"]) for entry in logged)


def test_unreadable_authority_declarations_are_reported_per_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed declaration is named, because the client then skips no member."""
    root = _repository(root=tmp_path, inventory="check-alpha  # authority: sometimes\n")

    status, logged = _run(root=root, monkeypatch=monkeypatch, capsys=capsys, armed=True)

    assert status == 1
    assert len(logged) == 1
    assert logged[0]["delegated_path"] == "pre-commit"
    assert "cannot read the authority declarations" in str(logged[0]["event"])
    assert "check-alpha" in str(logged[0]["event"])
