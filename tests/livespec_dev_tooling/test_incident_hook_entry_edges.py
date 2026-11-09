"""Repair hooks use real local fast gates and retain incomplete evidence."""

from __future__ import annotations

import io
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_entry as module
from livespec_dev_tooling.incident_hook_process import HookRefusalError, canonical


def _repository(*, root: Path, failure: int = 0) -> tuple[str, str]:
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.com"],
        ["checkout", "-b", "repair"],
        ["remote", "add", "origin", "https://github.com/owner/repo.git"],
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "app.py").write_text("value = 1\n")
    (root / "check-targets.txt").write_text(
        "check-fast # incident-timing: fast\ncheck-never # incident-timing: slow\n"
    )
    (root / "justfile").write_text(
        'check-fast:\n    python3 -c \'import os,sys; assert not any(k in os.environ for k in ["EXPEDITED_INCIDENT_RESPONSE","LIVESPEC_INCIDENT_AUTHORITY_QUERY"]); print("fast"); sys.exit('
        + str(failure)
        + ")'\ncheck-never:\n    touch slow-was-launched\n"
    )
    for args in (["add", "."], ["commit", "-qm", "fixture seed"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    (root / "app.py").write_text("# EXPEDITED_INCIDENT_RESPONSE flag: incident-1\nvalue = 2\n")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    return head, subprocess.run(
        ["git", "write-tree"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _wired(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, failure: int = 0
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    for key in tuple(os.environ):
        if key.startswith(("GIT_", "EXPEDITED_", "LIVESPEC_INCIDENT_")):
            monkeypatch.delenv(key, raising=False)
    head, tree = _repository(root=root, failure=failure)
    query = dict(
        repository="owner/repo",
        item="incident-1",
        attempt="attempt-1",
        phase="repair",
        operation="operation-1",
        generation=1,
        owner="operator:alice",
    )
    reading = dict(
        attempt=dict(
            repository="owner/repo",
            item_id="incident-1",
            attempt_id="attempt-1",
            phase="repair",
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base=head,
            head=head,
            pr_number=0,
            original_paths=["app.py"],
            landed_commits=[],
        ),
        committed_token_id="closed-1",  # noqa: S106 — public immutable record identifier.
        current_token_id="open-2",  # noqa: S106 — public immutable record identifier.
        is_current=True,
        operation_ids=["operation-1"],
    )
    receipts: list[dict[str, Any]] = []

    def invoke(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["query"] == query
        if kwargs["action"] == "read-current":
            return reading
        if kwargs["action"] == "read-local-gates":
            return dict(
                status="absent",
                receipt_id=kwargs["receipt_id"],
                receipt=None,
                checksum=None,
                committed_token_id=reading["committed_token_id"],
                current_token_id=reading["current_token_id"],
            )
        receipt = json.loads(kwargs["receipt"])
        assert receipt["tree"] == tree
        receipts.append(receipt)
        return dict(
            receipt_id=receipt["receipt_id"],
            checksum="sha256:" + "a" * 64,
            committed_token_id="closed-1",  # noqa: S106 — public immutable record identifier.
            current_token_id="open-2",  # noqa: S106 — public immutable record identifier.
        )

    monkeypatch.chdir(root)
    monkeypatch.setenv(module.EXPEDITED_INCIDENT_RESPONSE, "1")
    monkeypatch.setenv(module.QUERY_ENV, canonical(value=query))
    monkeypatch.setenv(module.LOCAL_OPERATION_ENV, "local-operation-1")
    monkeypatch.setattr(module, "invoke_authority", invoke)
    return reading, receipts


@pytest.mark.parametrize("failure", [0, 3])
def test_real_fast_gate_and_failure_are_persisted_without_slow_or_normal_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: int,
) -> None:
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "foreign.git"))
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch, failure=failure)
    assert module.main(argv=["pre-commit"]) == failure
    assert len(receipts) == 1
    assert [(r["name"], r["status"]) for r in receipts[0]["results"]] == [
        ("incident-carrier-scope", "passed"),
        ("check-fast", "failed" if failure else "passed"),
        ("check-never", "deferred"),
    ]
    assert not (tmp_path / "slow-was-launched").exists()
    assert not (tmp_path / ".livespec-coverage-reuse-token").exists()
    assert json.loads(capsys.readouterr().out)["normal_factory_proof"] is False


def test_commit_message_requires_audited_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    message = tmp_path / ".git/COMMIT_EDITMSG"
    message.write_text("fix: repair\n")
    assert module.main(argv=["commit-msg", str(message)]) == 78
    assert not receipts
    message.write_text("fix: repair\n\nFactory-Override: identified incident\n")
    assert module.main(argv=["commit-msg", str(message)]) == 0


def test_source_change_after_persistence_refuses_but_keeps_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority

    def changed(**kwargs: Any) -> dict[str, Any]:
        result = invoke(**kwargs)
        if kwargs["action"] == "record-local-gates":
            (tmp_path / "app.py").write_text("value = 3\n")
        return result

    monkeypatch.setattr(module, "invoke_authority", changed)
    assert module.main(argv=["pre-commit"]) == 78
    assert len(receipts) == 1


def test_ordinary_false_flag_does_not_consume_push_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(module.EXPEDITED_INCIDENT_RESPONSE, "0")
    monkeypatch.delenv(module.EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)

    class Unreadable:
        def read(self, *_args: object) -> str:
            raise AssertionError("ordinary stdin consumed")

    with pytest.raises(AssertionError, match="ordinary stdin consumed"):
        Unreadable().read()
    monkeypatch.setattr(sys, "stdin", Unreadable())
    assert module.main(argv=["pre-push"]) == 75


@pytest.mark.parametrize("value", ["bad", "1"])
def test_bad_flag_or_missing_identity_never_selects_normal_fallback(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(module.EXPEDITED_INCIDENT_RESPONSE, value)
    monkeypatch.delenv(module.EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)
    monkeypatch.delenv(module.QUERY_ENV, raising=False)
    assert module.main(argv=["pre-commit"]) == 78


def test_changed_current_generation_refuses_after_retaining_partial_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority

    def moved(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "read-current" and receipts:
            return reading | {"current_token_id": "new-generation"}
        return invoke(**kwargs)

    monkeypatch.setattr(module, "invoke_authority", moved)
    assert module.main(argv=["pre-commit"]) == 78
    assert len(receipts) == 1


def test_receipt_refusal_never_admits_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority

    def refused(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "record-local-gates":
            raise HookRefusalError("canonical receipt unavailable")
        return invoke(**kwargs)

    monkeypatch.setattr(module, "invoke_authority", refused)
    assert module.main(argv=["pre-commit"]) == 78
    assert not receipts


def test_module_cli_retains_ordinary_exit_and_unknown_hook_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(module.EXPEDITED_INCIDENT_RESPONSE, raising=False)
    monkeypatch.delenv(module.EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)
    assert module.main(argv=[]) == 78
    monkeypatch.setattr(sys, "argv", ["incident-hook", "pre-commit"])
    monkeypatch.delitem(sys.modules, module.__name__, raising=False)
    with pytest.raises(SystemExit, match="75"):
        runpy.run_module("livespec_dev_tooling.incident_hook_entry", run_name="__main__")


def test_real_git_pushurl_override_refuses_without_publishing_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    subprocess.run(["git", "commit", "-qm", "fixture repair"], cwd=tmp_path, check=True)
    reading["attempt"]["head"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True, check=True, capture_output=True
    ).stdout.strip()
    subprocess.run(
        ["git", "config", "remote.origin.pushurl", "https://github.com/foreign/repo.git"],
        cwd=tmp_path,
        check=True,
    )
    assert (
        subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=tmp_path,
            text=True,
            check=True,
            capture_output=True,
        ).stdout.strip()
        == "https://github.com/owner/repo.git"
    )
    head = reading["attempt"]["head"]
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(f"refs/heads/repair {head} refs/heads/repair {'0'*40}\n")
    )
    assert module.main(argv=["pre-push", "origin", "https://github.com/foreign/repo.git"]) == 78
    assert "resolved push destination" in capsys.readouterr().err
    assert not receipts


def test_empty_inventory_is_explicit_and_never_ordinary_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setattr(module, "inventory_gates", lambda **_kwargs: ())
    assert module.main(argv=["pre-commit"]) == 0
    assert receipts[0]["results"][-1]["name"] == "incident-inventory"


@pytest.mark.parametrize("wrong", ["receipt", "checksum", "normalroute", "tree"])
def test_inconsistent_receipt_route_or_tree_never_admits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong: str
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority

    def inconsistent(**kwargs: Any) -> dict[str, Any]:
        value = invoke(**kwargs)
        if kwargs["action"] == "record-local-gates":
            if wrong == "receipt":
                value["receipt_id"] = "different"
            if wrong == "checksum":
                value["checksum"] = "not-a-checksum"
        return value

    monkeypatch.setattr(module, "invoke_authority", inconsistent)
    if wrong == "normalroute":
        monkeypatch.setattr(module, "route_resolved_gates", lambda **_kwargs: None)
    if wrong == "tree":
        original = module.exact_tree

        def tree(**kwargs: Any) -> str:
            return "changed" if receipts else original(**kwargs)

        monkeypatch.setattr(module, "exact_tree", tree)
    assert module.main(argv=["pre-commit"]) == 78


def test_real_partial_git_commit_cannot_certify_the_ordinary_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, _receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY

    subprocess.run(["git", "config", "livespec.sandboxExempt", "true"], cwd=tmp_path, check=True)
    (tmp_path / "b.py").write_text("value = 3\n")
    subprocess.run(["git", "add", "b.py"], cwd=tmp_path, check=True)
    hook = tmp_path / ".git/hooks/pre-commit"
    hook.write_text(CANONICAL_HOOK_BODY)
    hook.chmod(0o755)
    binary = tmp_path / ".git/bin"
    binary.mkdir()
    script = binary / "mise"
    script.write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 0 ] && [ "$1" != "livespec_dev_tooling.incident_hook_entry" ]; do shift; done\nshift\nexec "$PYTHON_BIN" -m livespec_dev_tooling.incident_hook_entry "$@"\n'
    )
    script.chmod(0o755)
    environment = dict(
        os.environ,
        PATH=str(binary) + os.pathsep + os.environ["PATH"],
        PYTHON_BIN=sys.executable,
        PYTHONPATH=str(Path(module.__file__).resolve().parent.parent),
    )
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, text=True, capture_output=True
    ).stdout
    done = subprocess.run(
        ["git", "commit", "-m", "fix: partial repair", "--", "app.py"],
        cwd=tmp_path,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert done.returncode != 0
    assert "alternate Git operation index" in done.stderr
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, text=True, capture_output=True
        ).stdout
        == before
    )
    assert set(
        subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=tmp_path,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
    ) == {"app.py", "b.py"}


def test_actual_default_index_matches_exact_stage_and_malformed_index_option_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    assert module.main(argv=["pre-commit", "--git-index-file"]) == 78
    assert (
        module.main(argv=["pre-commit", "--git-index-file", str(tmp_path / ".git/alternate-index")])
        == 78
    )
    assert module.main(argv=["pre-commit", "--git-index-file", str(tmp_path / ".git/index")]) == 0
    assert len(receipts) == 1


def test_a_slow_receipt_lookup_never_counts_toward_the_scope_gate_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # livespec-dev-tooling-e62ss6 attempt 3: a 62 s read-local-gates at generation 15 made
    # the scope row a "passed" row of 60 s or more, which the authority refuses.
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority
    now = [1000.0]

    def slow_lookup(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "read-local-gates":
            now[0] += 61.0
        return invoke(**kwargs)

    monkeypatch.setattr(module, "invoke_authority", slow_lookup)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    assert module.main(argv=["pre-commit"]) == 0
    scope = receipts[0]["results"][0]
    assert (scope["name"], scope["status"]) == ("incident-carrier-scope", "passed")
    assert scope["duration_seconds"] < 60


def _revert_wired(
    *, monkeypatch: pytest.MonkeyPatch, landed: list[str], repair: str | None
) -> list[str]:
    for key in tuple(os.environ):
        if key.startswith(("GIT_", "EXPEDITED_", "LIVESPEC_INCIDENT_")):
            monkeypatch.delenv(key, raising=False)
    query = dict(
        repository="owner/repo",
        item="incident-1",
        attempt="attempt-1",
        phase="reverting",
        operation="operation-1",
        generation=1,
        owner="operator:alice",
    )
    reading = dict(
        attempt=dict(
            repository="owner/repo",
            item_id="incident-1",
            attempt_id="attempt-1",
            phase="reverting",
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base="a" * 40,
            head="b" * 40,
            landed_commits=landed,
        ),
        committed_token_id="closed-1",  # noqa: S106 — public immutable record identifier.
        current_token_id="open-2",  # noqa: S106 — public immutable record identifier.
        is_current=True,
    )
    actions: list[str] = []

    def invoke(**kwargs: Any) -> dict[str, Any]:
        actions.append(kwargs["action"])
        return reading

    monkeypatch.setenv(module.EXPEDITED_INCIDENT_RESPONSE_REVERT, "1")
    if repair is not None:
        monkeypatch.setenv(module.EXPEDITED_INCIDENT_RESPONSE, repair)
    monkeypatch.setenv(module.QUERY_ENV, canonical(value=query))
    monkeypatch.setenv(module.LOCAL_OPERATION_ENV, "local-operation-1")
    monkeypatch.setattr(module, "invoke_authority", invoke)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    return actions


@pytest.mark.parametrize("repair", [None, "1"])
@pytest.mark.parametrize("hook", ["pre-commit", "commit-msg", "pre-push"])
def test_revert_flag_hands_off_to_the_trusted_recovery_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook: str,
    repair: str | None,
) -> None:
    actions = _revert_wired(monkeypatch=monkeypatch, landed=["d" * 40, "c" * 40], repair=repair)
    status = module.main(argv=[hook])
    handoff = json.loads(capsys.readouterr().out)
    facts = [
        status == 79,
        actions == ["read-current"],
        handoff["handoff"] == "trusted-recovery-boundary",
        handoff["mode"] == "emergency-revert",
        handoff["recorded_incident_merge_sha"] == "c" * 40,
        handoff["incident_item_id"] == "incident-1",
        handoff["normal_factory_proof"] is False,
    ]
    assert all(facts), (status, actions, handoff)


@pytest.mark.parametrize("repair", [None, "1"])
def test_revert_flag_without_a_landed_incident_merge_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], repair: str | None
) -> None:
    actions = _revert_wired(monkeypatch=monkeypatch, landed=[], repair=repair)
    status = module.main(argv=["pre-commit"])
    captured = capsys.readouterr()
    facts = [
        status == 78,
        actions == ["read-current"],
        "missing-recorded-incident-merge" in captured.err,
        captured.out == "",
    ]
    assert all(facts), (status, actions, captured)
