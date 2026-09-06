"""Outside-in test for `plan_record_conformance` — a positive control per verdict.

The ratified contract (`livespec-orchestrator-beads-fabro`
`SPECIFICATION/contracts.md` §"Plan-record conformance checks", v095) requires
that each of the eleven checks carry a positive control proving it can return a
hit, so every check id below owns a test that BUILDS the offending fixture and
asserts the id appears in the finding stream. The two WARN verdicts additionally
assert the run still exits 0, and the ERROR verdicts that it exits 1.

Modules are imported INSIDE the test bodies (never at module scope) so an
unimplemented tree fails on a genuine assertion — `assert path.is_file()` —
rather than dying at collection with an import error.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import NamedTuple, Protocol

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
_TENANT = "livespec-dev-tooling"
_EPIC = f"{_TENANT}-e1"
_OTHER_EPIC = f"{_TENANT}-e2"
_WORK_ITEM = f"{_TENANT}-w1"
_SESSION = "session-1 at 2026-09-06T00:00:00Z"
_EVIDENCE = (
    "plan-completeness-review-evidence\n"
    "evidence-id: ev-1\n"
    "reviewer-identity: reviewer-1\n"
    "separate-reviewer: true\n"
    "attests-complete-requirement-coverage: true\n"
    "timestamp: 2026-09-06T00:00:00Z\n\n"
    "every requirement has a carrier"
)


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


class _SubprocessRun(Protocol):
    """Typed stand-in for `subprocess.run` monkeypatches."""

    def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
        """Return the configured completed-process-like object."""
        ...


def _load(*, name: str) -> ModuleType:
    """Import one checks module fresh from its file path."""
    path = _CHECKS_DIR / f"{name}.py"
    assert path.is_file(), f"{path} should exist"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: a `@dataclass` in a file-loaded module resolves
    # its own `__module__` through `sys.modules` while building the field list,
    # and an unregistered name makes that lookup raise rather than miss.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_subprocess_run(*, result: SimpleNamespace) -> _SubprocessRun:
    """Return a typed `subprocess.run` replacement that never spawns."""

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = args
        _ = kwargs
        return result

    return _run


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the family RUN lever and the beads credential."""
    monkeypatch.setenv("LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE", "1")
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the arming env so the check self-skips."""
    monkeypatch.delenv("LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE", raising=False)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)


def _write_livespec_config(*, root: Path, prefix: str = _TENANT) -> None:
    """Create a minimal `.livespec.jsonc` carrying the store prefix."""
    body = "\n".join(
        (
            "{",
            '  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" },',
            '  "livespec-orchestrator-beads-fabro": {',
            f'    "connection": {{ "prefix": "{prefix}" }}',
            "  }",
            "}",
            "",
        )
    )
    _ = (root / ".livespec.jsonc").write_text(body, encoding="utf-8")


def _plan_record(*, root: Path, relative: str, anchor: str | None = None) -> None:
    """Create a plan-record directory, optionally carrying an anchor file."""
    directory = root / relative
    directory.mkdir(parents=True, exist_ok=True)
    if anchor is not None:
        _ = (directory / "associated_work_item_id").write_text(anchor, encoding="utf-8")


def _metadata(
    *,
    slug: str | None = None,
    next_action: object | None = None,
    last_session: str | None = None,
    plan_ref: str | None = None,
) -> dict[str, object]:
    """Build one record's metadata block from the keys the fixture declares."""
    metadata: dict[str, object] = {}
    if slug is not None:
        metadata["plan_slug"] = slug
    if next_action is not None:
        metadata["next_action"] = next_action
    if last_session is not None:
        metadata["last_session"] = last_session
    if plan_ref is not None:
        metadata["plan_ref"] = plan_ref
    return metadata


def _action(
    *, kind: str = "impl", ref: str = _WORK_ITEM, text: str = "Drive the item."
) -> dict[str, object]:
    """Build a typed `next_action` metadata object."""
    return {"kind": kind, "ref": ref, "text": text}


def _epic_record(
    *,
    item_id: str = _EPIC,
    status: str = "open",
    slug: str | None = None,
    next_action: object | None = None,
    last_session: str | None = _SESSION,
) -> dict[str, object]:
    """Build one same-tenant plan epic record."""
    return {
        "id": item_id,
        "type": "epic",
        "status": status,
        "metadata": _metadata(slug=slug, next_action=next_action, last_session=last_session),
    }


def _conforming_epic(*, slug: str = "live") -> dict[str, object]:
    """Build an open plan epic that breaks no verdict."""
    return _epic_record(slug=slug, next_action=_action())


def _task_record(
    *,
    item_id: str = _WORK_ITEM,
    slug: str | None = None,
    plan_ref: str | None = None,
    depends_on: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build one same-tenant non-epic record."""
    return {
        "id": item_id,
        "type": "task",
        "status": "open",
        "metadata": _metadata(slug=slug, plan_ref=plan_ref),
        "depends_on": list(depends_on),
    }


def _comment(*, text: str, created_at: str = "2026-09-06T01:00:00Z") -> dict[str, object]:
    """Build one ledger comment record."""
    return {"id": "c1", "text": text, "created_at": created_at}


def _zero_lifecycle(*, item_reader: object) -> int:
    """Stand in for a delegate that found no lifecycle violation."""
    _ = item_reader
    return 0


def _failing_lifecycle(*, item_reader: object) -> int:
    """Stand in for a delegate that found a lifecycle violation."""
    _ = item_reader
    return 1


def _run(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    items: list[dict[str, object]] | None = None,
    comments: dict[str, list[dict[str, object]]] | None = None,
    lifecycle: object = _zero_lifecycle,
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with every ledger reader injected."""
    module = _load(name="plan_record_conformance")

    def _items(*, repo: Path) -> list[dict[str, object]]:
        assert repo == cwd
        return list(items or [])

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        assert repo == cwd
        return list((comments or {}).get(item_id, []))

    monkeypatch.chdir(cwd)
    returncode = module.main(
        item_reader=_items, comment_reader=_comments, lifecycle_runner=lifecycle
    )
    captured = capsys.readouterr()
    return _CheckRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


def _armed_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Arm the family and return a repo root carrying the tenant config."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    return tmp_path


def test_unarmed_family_skips_and_names_every_check_id(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the lever the check self-skips, with the same shape as plan_epic_parity."""
    _disarm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _plan_record(root=tmp_path, relative="plan/live")

    result = _run(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[])

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skipped" in combined
    assert "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE" in combined
    assert "plan_slug_present" in combined
    assert "plan_comment_rate" in combined


def test_credential_without_lever_still_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The credential alone does not arm the family."""
    _disarm(monkeypatch)
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")
    _write_livespec_config(root=tmp_path)

    result = _run(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[])

    assert result.returncode == 0
    assert "skipped" in (result.stdout + result.stderr)


def test_conforming_tenant_reports_no_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A migrated tenant passes: anchors both ways, typed pointer, closed with evidence.

    The `unassigned` record is conforming too — it is the sanctioned
    research-before-work-items state, in which a directory of research exists and
    no epic carries its slug yet.
    """
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")
    _plan_record(root=root, relative="plan/research-only", anchor="unassigned\n")
    _plan_record(root=root, relative="plan/archive/done", anchor=f"{_OTHER_EPIC}\n")

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _conforming_epic(),
            _epic_record(item_id=_OTHER_EPIC, status="closed", slug="done"),
            _task_record(plan_ref=f"{_TENANT}/other-plan"),
        ],
        comments={
            _EPIC: [_comment(text=f"plan-handoff-entry\nauthor: a\n\nnext action: {_WORK_ITEM}")],
            _OTHER_EPIC: [_comment(text=_EVIDENCE)],
        },
    )

    assert result.returncode == 0, result.stderr
    assert '"verdict": "error"' not in result.stderr


def test_plan_slug_present_hits_an_epic_without_the_metadata(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: an epic carrying no `plan_slug`."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _run(cwd=root, monkeypatch=monkeypatch, capsys=capsys, items=[_epic_record(slug=None)])

    assert result.returncode == 1
    assert "plan_slug_present" in result.stderr
    assert _EPIC in result.stderr


def test_plan_slug_unique_hits_two_epics_sharing_a_slug(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: two epics carrying the same slug."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _epic_record(slug="shared", next_action=_action()),
            _epic_record(item_id=_OTHER_EPIC, slug="shared", next_action=_action()),
        ],
    )

    assert result.returncode == 1
    assert "plan_slug_unique" in result.stderr
    assert _OTHER_EPIC in result.stderr


def test_plan_slug_canonical_hits_a_non_canonical_value(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: a slug that is not its own canonicalization."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic_record(slug="Not_Canonical Slug-")],
    )

    assert result.returncode == 1
    assert "plan_slug_canonical" in result.stderr
    assert "not-canonical-slug" in result.stderr


def test_plan_slug_on_non_epic_hits_a_task_carrying_the_slug(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: a non-epic work item carrying `plan_slug`."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_task_record(slug="live"), {"type": "task", "status": "open"}],
    )

    assert result.returncode == 1
    assert "plan_slug_on_non_epic" in result.stderr
    assert _WORK_ITEM in result.stderr


def test_plan_ref_must_be_tenant_qualified_and_not_name_the_parent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `plan_ref` half of the same verdict: unqualified, and parent-shadowing."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    unqualified = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_task_record(plan_ref="bare-slug"), _task_record(item_id=f"{_TENANT}-w2")],
    )
    parent = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _epic_record(slug="live", next_action=_action()),
            _task_record(plan_ref=f"{_TENANT}/live", depends_on=(_EPIC,)),
        ],
    )

    assert unqualified.returncode == 1
    assert "not tenant-qualified" in unqualified.stderr
    assert parent.returncode == 1
    assert "already a child of" in parent.stderr


def test_plan_anchor_present_hits_a_missing_and_an_illegible_anchor(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: no anchor file, and a file that is not one legible line."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live")
    _plan_record(root=root, relative="plan/archive/two-lines", anchor=f"{_EPIC}\nextra\n")
    _plan_record(root=root, relative="plan/archive/foreign", anchor="overseer-x1\n")

    result = _run(cwd=root, monkeypatch=monkeypatch, capsys=capsys, items=[])

    assert result.returncode == 1
    assert "plan_anchor_present" in result.stderr
    assert "plan/live" in result.stderr
    assert "plan/archive/two-lines" in result.stderr
    assert "plan/archive/foreign" in result.stderr


def test_plan_anchor_consistent_hits_every_disagreement_shape(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: unknown id, non-epic id, slug mismatch, and premature unassigned."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/unknown", anchor=f"{_TENANT}-nope\n")
    _plan_record(root=root, relative="plan/non-epic", anchor=f"{_WORK_ITEM}\n")
    _plan_record(root=root, relative="plan/mismatch", anchor=f"{_EPIC}\n")
    _plan_record(root=root, relative="plan/adopted", anchor="unassigned\n")

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _epic_record(slug="elsewhere", next_action=_action()),
            _epic_record(item_id=_OTHER_EPIC, slug="adopted", next_action=_action()),
            _task_record(),
        ],
    )

    assert result.returncode == 1
    assert "plan_anchor_consistent" in result.stderr
    assert "anchor names no record" in result.stderr
    assert "anchor names non-epic record" in result.stderr
    assert "differs from the directory name" in result.stderr
    assert "while epic" in result.stderr


def test_plan_anchor_consistent_hits_the_epic_side_of_the_pair(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The converse direction: an epic whose slug names a directory anchored elsewhere."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_OTHER_EPIC}\n")

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _epic_record(slug="live", next_action=_action()),
            _epic_record(item_id=_OTHER_EPIC, slug="other", next_action=_action()),
        ],
    )

    assert result.returncode == 1
    assert "whose anchor holds" in result.stderr


def test_plan_lifecycle_parity_delegates_to_the_real_plan_epic_parity_check(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: an active plan record whose anchor epic is closed.

    The REAL delegate runs here — no injected runner — so the control proves the
    delegation wiring, not a stand-in.
    """
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", "1")
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")
    module = _load(name="plan_record_conformance")
    items = [_epic_record(status="closed", slug="live")]

    def _items(*, repo: Path) -> list[dict[str, object]]:
        _ = repo
        return items

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        _ = repo
        _ = item_id
        return []

    monkeypatch.chdir(root)
    returncode = module.main(item_reader=_items, comment_reader=_comments)
    captured = capsys.readouterr()

    assert returncode == 1
    assert "plan_lifecycle_parity" in captured.err
    assert "plan_epic_parity" in captured.err


def test_plan_lifecycle_parity_reports_the_delegate_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-zero delegate becomes an error verdict under the ratified check id."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[],
        lifecycle=_failing_lifecycle,
    )

    assert result.returncode == 1
    assert "plan_lifecycle_parity" in result.stderr
    assert "reported a plan-lifecycle violation" in result.stderr


def test_plan_close_evidence_hits_a_closed_record_without_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: an archived plan epic with no completeness-review evidence."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/archive/done", anchor=f"{_EPIC}\n")

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic_record(status="closed", slug="done")],
        comments={_EPIC: [_comment(text="plan-handoff-entry\nauthor: a\n\nnothing durable here")]},
    )

    assert result.returncode == 1
    assert "plan_close_evidence" in result.stderr
    assert _EPIC in result.stderr


def test_plan_next_action_typed_hits_an_absent_and_an_ill_typed_pointer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control: an open live plan epic with no pointer, then a broken one."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")

    absent = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic_record(slug="live")],
    )
    ill_typed = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _epic_record(
                slug="live",
                next_action=_action(kind="guess", ref="", text=""),
                last_session=None,
            )
        ],
    )

    assert absent.returncode == 1
    assert "carries no typed `next_action`" in absent.stderr
    assert ill_typed.returncode == 1
    assert "plan_next_action_typed" in ill_typed.stderr
    assert "is not one of" in ill_typed.stderr
    assert "carries no text" in ill_typed.stderr
    assert "carries no `last_session`" in ill_typed.stderr


def test_plan_next_action_typed_hits_the_ref_rules_of_each_kind(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`impl` and `spec-op` require a ref; `none` forbids one."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")

    empty_ref = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic_record(slug="live", next_action=_action(kind="spec-op", ref=""))],
    )
    none_with_ref = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic_record(slug="live", next_action=_action(kind="none"))],
    )

    assert empty_ref.returncode == 1
    assert "carries an empty ref" in empty_ref.stderr
    assert none_with_ref.returncode == 1
    assert "kind 'none' carries a ref" in none_with_ref.stderr


def test_plan_next_action_drift_warns_without_failing_the_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control for a WARN verdict: prose disagreeing with the typed pointer."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_conforming_epic()],
        comments={
            _EPIC: [
                _comment(text="plan-handoff-entry\nauthor: a\n\n- next action: ask the maintainer")
            ]
        },
    )

    assert result.returncode == 0, result.stderr
    assert "plan_next_action_drift" in result.stderr
    assert '"verdict": "warn"' in result.stderr


def test_plan_comment_rate_warns_past_the_default_threshold(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Positive control for the second WARN verdict: seven comments on one UTC day."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _plan_record(root=root, relative="plan/live", anchor=f"{_EPIC}\n")
    same_day = [_comment(text=f"note {index}") for index in range(7)]

    result = _run(
        cwd=root,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_conforming_epic()],
        comments={_EPIC: [*same_day, _comment(text="undated", created_at="")]},
    )

    assert result.returncode == 0, result.stderr
    assert "plan_comment_rate" in result.stderr
    assert "exceeds the record-rate threshold of 6" in result.stderr


def test_main_defaults_to_the_shared_ledger_readers(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no injection, `main()` reads through the shared `_plan_ledger` readers."""
    root = _armed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.delenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", raising=False)
    module = _load(name="plan_record_conformance")
    read_calls: list[str] = []

    def _items(*, repo: Path) -> list[dict[str, object]]:
        _ = repo
        read_calls.append("items")
        return [_epic_record(slug="unanchored", next_action=_action())]

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        _ = repo
        read_calls.append(item_id)
        return []

    monkeypatch.setattr(module, "bd_items_reader", _items)
    monkeypatch.setattr(module, "bd_comments_reader", _comments)
    monkeypatch.chdir(root)
    returncode = module.main()
    _ = capsys.readouterr()

    assert returncode == 0
    assert read_calls == ["items", _EPIC]


def test_plan_directories_reads_both_trees_and_ignores_stray_files(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan-store reader returns direct records only, and tolerates no `plan/`."""
    _ = monkeypatch
    dirs = _load(name="_plan_record_dirs")
    ledger = _load(name="_plan_ledger")
    tenant = ledger.tenant_id_re(tenant_prefix=_TENANT)
    _plan_record(root=tmp_path, relative="plan/live", anchor=f"{_EPIC}\n")
    _plan_record(root=tmp_path, relative="plan/archive/done", anchor="unassigned\n")
    _ = (tmp_path / "plan" / "stray.md").write_text("not a record\n", encoding="utf-8")

    empty = dirs.plan_directories(plan_dir=tmp_path / "absent", tenant_re=tenant)
    found = dirs.plan_directories(plan_dir=tmp_path / "plan", tenant_re=tenant)

    assert empty == []
    assert [(entry.relative, entry.archived, entry.anchor) for entry in found] == [
        ("plan/live", False, _EPIC),
        ("plan/archive/done", True, "unassigned"),
    ]


def test_no_archive_tree_is_not_a_failure(*, tmp_path: Path) -> None:
    """A repo with no `plan/archive/` reads its live records and stops."""
    dirs = _load(name="_plan_record_dirs")
    ledger = _load(name="_plan_ledger")
    _plan_record(root=tmp_path, relative="plan/live")

    found = dirs.plan_directories(
        plan_dir=tmp_path / "plan", tenant_re=ledger.tenant_id_re(tenant_prefix=_TENANT)
    )

    assert [(entry.slug, entry.raw, entry.anchor) for entry in found] == [("live", None, None)]


def test_comment_readers_tolerate_every_absent_shape() -> None:
    """The comment projections answer for records that carry none of their fields."""
    comments = _load(name="_plan_record_comments")

    assert comments.comment_text(comment={"text": 7}) == ""
    assert comments.comment_day(comment={"created_at": 7}) is None
    assert comments.comment_day(comment={"created_at": "2026-09"}) is None
    assert comments.comment_day(comment={"created_at": "2026-09-06T01:00:00Z"}) == "2026-09-06"
    assert comments.is_completeness_review_evidence(text="") is False
    assert comments.is_completeness_review_evidence(text=_EVIDENCE) is True
    assert (
        comments.is_completeness_review_evidence(
            text="plan-completeness-review-evidence\nmalformed line\n\nbody"
        )
        is False
    )
    assert (
        comments.is_completeness_review_evidence(
            text=_EVIDENCE.replace("separate-reviewer: true", "separate-reviewer: false")
        )
        is False
    )


def test_newest_handoff_action_needs_exactly_one_recorded_action() -> None:
    """Zero, several, and unparseable marker lines all read as no recorded action."""
    comments = _load(name="_plan_record_comments")
    header = "plan-handoff-entry\nauthor: a\n\n"

    assert comments.newest_handoff_action(comments=[_comment(text="scope event")]) is None
    assert comments.newest_handoff_action(comments=[_comment(text=f"{header}no marker")]) is None
    assert (
        comments.newest_handoff_action(
            comments=[_comment(text=f"{header}next action\nnext action:  ")]
        )
        is None
    )
    assert (
        comments.newest_handoff_action(
            comments=[_comment(text=f"{header}next action: one\nnext action: two")]
        )
        is None
    )
    assert (
        comments.newest_handoff_action(
            comments=[
                _comment(text=f"{header}next action: older"),
                _comment(text=f"{header}# Next Action: newer"),
            ]
        )
        == "newer"
    )


def test_typed_pointer_parsing_and_prose_comparison() -> None:
    """The pointer reader answers for absent, ill-typed, and well-formed metadata."""
    next_action = _load(name="_plan_record_next_action")

    assert next_action.parse_next_action(record={}) is None
    assert next_action.parse_next_action(record={"metadata": {"next_action": "prose"}}) is None
    parsed = next_action.parse_next_action(
        record={"metadata": {"next_action": {"kind": "impl", "ref": _WORK_ITEM, "text": 7}}}
    )
    assert parsed is not None
    assert parsed.text == ""
    assert next_action.matches(recorded=f"drive {_WORK_ITEM} to green", action=parsed) is True
    assert next_action.matches(recorded="something else", action=parsed) is False
    human = next_action.NextAction(kind="human", ref="", text="Ask the maintainer.")
    assert next_action.matches(recorded="ask   the MAINTAINER.", action=human) is True
    assert next_action.matches(recorded="ship it", action=human) is False
    assert next_action.typing_violations(action=human, epic=_epic_record()) == []


def test_timeline_findings_skip_a_record_without_an_id(*, tmp_path: Path) -> None:
    """A record with no id cannot be reported against, so it leaves the population.

    The SAME reader grades an identified epic beside the id-less one, so the
    recorder proves the skip positively — it names exactly who was read — rather
    than resting on a guard body that never runs and can therefore never fail.
    """
    timeline = _load(name="_plan_record_timeline")
    seen: list[str] = []

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        _ = repo
        seen.append(item_id)
        return []

    idless = timeline.timeline_findings(
        epics=[{"type": "epic", "status": "open"}],
        live_slugs=frozenset(),
        record_slugs=frozenset(),
        read_comments=_comments,
        repo=tmp_path,
    )
    identified = timeline.timeline_findings(
        epics=[_conforming_epic()],
        live_slugs=frozenset(),
        record_slugs=frozenset(),
        read_comments=_comments,
        repo=tmp_path,
    )

    assert idless == []
    assert identified == []
    assert seen == [_EPIC], "only the record carrying an id is read"


def test_finding_subject_helpers_tolerate_an_idless_record() -> None:
    """Both id projections answer for a record the caller has not yet validated."""
    slugs = _load(name="_plan_record_slugs")
    anchors = _load(name="_plan_record_anchors")

    assert slugs._id_of(record={}) == ""  # noqa: SLF001  — private projection under test
    assert anchors._joined_ids(records=[{}]) == ""  # noqa: SLF001  — private helper under test


def test_ledger_reader_passes_status_all_so_closed_epics_are_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bd list` defaults to open statuses; the fallback must ask for all of them."""
    ledger = _load(name="_plan_ledger")
    seen: list[str] = []

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = kwargs
        seen.append(repr(args[0]) if args else "")
        return SimpleNamespace(returncode=0, stdout='{"data":[{"id":"from-bd"}]}', stderr="")

    monkeypatch.setattr(ledger.subprocess, "run", _run)

    records = ledger.bd_items_reader(repo=tmp_path)

    assert records == [{"id": "from-bd"}]
    assert seen == [repr(("bd", "-C", str(tmp_path), "list", "--status", "all", "--json"))]


def test_comment_reader_reads_a_show_payload_and_tolerates_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared comment reader parses `bd show --json`, else answers with nothing."""
    ledger = _load(name="_plan_ledger")
    payload = '{"data":[{"id":"e1","comments":[{"id":"c1","text":"hi"},7]}]}'
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(result=SimpleNamespace(returncode=0, stdout=payload, stderr="")),
    )
    assert ledger.bd_comments_reader(repo=tmp_path, item_id="e1") == [{"id": "c1", "text": "hi"}]

    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(
            result=SimpleNamespace(returncode=0, stdout='{"data":[{"id":"e1"}]}', stderr="")
        ),
    )
    assert ledger.bd_comments_reader(repo=tmp_path, item_id="e1") == []

    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(result=SimpleNamespace(returncode=0, stdout="", stderr="")),
    )
    assert ledger.bd_comments_reader(repo=tmp_path, item_id="e1") == []

    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(result=SimpleNamespace(returncode=1, stdout="", stderr="boom")),
    )
    assert ledger.bd_comments_reader(repo=tmp_path, item_id="e1") == []


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load(name="plan_record_conformance")

    assert callable(module.main), "main should be importable without invocation"
