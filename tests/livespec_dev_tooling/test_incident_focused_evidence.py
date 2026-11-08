"""Focused evidence exercises real tests and rejects use as normal proof."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._green_token_evidence import read_evidence_text
from livespec_dev_tooling.incident_focused_evidence import (
    FocusedScope,
    ManualReproduction,
    collect_focused_evidence,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xluwqj


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Fixture")
    _git(tmp_path, "config", "user.email", "fixture@example.org")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/widget.py").write_text("def answer():\n    return 42\n")
    (tmp_path / "tests/test_widget.py").write_text(
        "from src.widget import answer\ndef test_answer():\n    assert answer() == 42\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "baseline")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "src/widget.py").write_text("def answer():\n    return 43\n")
    (tmp_path / "tests/test_widget.py").write_text(
        "from src.widget import answer\ndef test_answer():\n    assert answer() == 43\n"
    )
    _git(tmp_path, "add", ".")
    return tmp_path, base


def _context(root: Path, base: str) -> SimpleNamespace:
    return SimpleNamespace(
        mode="expedited-repair",
        identity=SimpleNamespace(
            incident_item_id="incident-1",
            attempt_id="1",
            phase="repair",
            repository="owner/project",
            base_sha=base,
            head_sha=_git(root, "rev-parse", "HEAD"),
            operation_id="repair-1",
        ),
    )


def _collect(root: Path, base: str, **kwargs: object) -> dict[str, object]:
    manual = kwargs.pop(
        "manual",
        ManualReproduction(procedure="call answer", expected="43", observed="43", outcome="passed"),
    )
    return collect_focused_evidence(
        repo_root=root,
        context=_context(root, base),
        scope=FocusedScope(
            tree_hash=_git(root, "write-tree"),
            source_prefixes=kwargs.pop("source_prefixes", ("src/",)),
            test_prefixes=kwargs.pop("test_prefixes", ("tests/",)),
            related_tests=kwargs.pop("related_tests", ("tests/test_widget.py",)),
            **kwargs,
        ),
        manual=manual,
    )


def test_collect_real_test_and_scoped_coverage(project: tuple[Path, str]) -> None:
    root, base = project
    (root / ".coverage").write_bytes(b"normal-data-must-survive")
    (root / ".livespec-coverage-reuse-token").write_text("normal-token")
    evidence = _collect(root, base)
    assert evidence["outcome"] == "passed"
    assert evidence["scope"] == "focused-tests-and-touched-files"
    assert evidence["coverage"]["src/widget.py"]["summary"]["percent_covered"] == 100
    assert evidence["manual"]["observed"] == "43"
    assert (root / ".coverage").read_bytes() == b"normal-data-must-survive"
    assert (root / ".livespec-coverage-reuse-token").read_text() == "normal-token"
    assert read_evidence_text(text=json.dumps(evidence)) is None


def test_real_failing_test_is_failed(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "tests/test_widget.py").write_text("def test_red():\n    assert False\n")
    _git(root, "add", ".")
    evidence = _collect(root, base)
    assert evidence["tests"]["returncode"] != 0
    assert evidence["outcome"] == "failed"


def test_missing_line_and_branch_coverage_are_recorded_risk(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "src/widget.py").write_text(
        "def answer(flag=True):\n    if flag:\n        return 43\n    return 99\n"
    )
    _git(root, "add", ".")
    evidence = _collect(root, base)
    assert evidence["tests"]["returncode"] == 0
    assert evidence["outcome"] == "incomplete"
    assert evidence["coverage"]["src/widget.py"]["missing_branches"]
    assert evidence["risks"]


def test_cumulative_scope_and_classification(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "src/earlier.py").write_text("VALUE = 1\n")
    (root / "src/generated.py").write_text("# @generated\nVALUE = 1\n")
    (root / "src/empty.py").write_text('"""Docs only."""\n')
    (root / "src/note.txt").write_text("note")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "earlier attempt")
    (root / "src/earlier.py").unlink()
    _git(root, "add", ".")
    evidence = _collect(root, base, prior_paths=("src/old.py",))
    assert evidence["paths"]["src/earlier.py"] == "deleted"
    assert evidence["paths"]["src/old.py"] == "deleted"
    assert evidence["paths"]["src/generated.py"] == "generated"
    assert evidence["paths"]["src/empty.py"] == "non-executable"
    assert evidence["paths"]["src/note.txt"] == "non-executable"


def test_shared_fixtures_require_explicit_related_selection(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "tests/conftest.py").write_text("SHARED = 1\n")
    _git(root, "add", ".")
    assert "shared test support" in _collect(root, base)["reason"]
    evidence = _collect(root, base, related_test_reason="widget is the affected fixture consumer")
    assert evidence["selection"]["related_test_reason"]


def test_nested_launchers_are_deferred_explicitly(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "tests/test_nested.py").write_text(
        "import subprocess\ndef test_nested():\n    subprocess.run(['pytest', 'tests'])\n"
    )
    _git(root, "add", ".")
    assert "nested suite launcher" in _collect(root, base)["reason"]
    evidence = _collect(
        root, base, deferred_tests=(("tests/test_nested.py", "full nested suite deferred"),)
    )
    assert evidence["outcome"] == "incomplete"
    assert evidence["selection"]["deferred_tests"]


def test_wrong_worktree_is_refused(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "src/widget.py").write_text("CHANGED = 1\n")
    assert "worktree differs" in _collect(root, base)["reason"]


@pytest.mark.parametrize(
    ("mode", "scope"), [("expedited-incident", "full-suite"), ("normal", "focused")]
)
def test_normal_readers_reject_partial_even_with_aggregate_fields(mode: str, scope: str) -> None:
    token = {
        "tree_hash": "tree",
        "mode": mode,
        "scope": scope,
        "pre_commit_aggregate": {
            "tree_hash": "tree",
            "run_id": "run",
            "output_checksum": "sum",
            "captured_at": "now",
        },
    }
    assert read_evidence_text(text=json.dumps(token)) is None


@pytest.mark.parametrize(
    ("mode", "scope"), [("expedited-repair", "full-suite"), ("normal", "focused")]
)
def test_normal_writers_refuse_partial_without_overwriting(
    project: tuple[Path, str], mode: str, scope: str
) -> None:
    import structlog

    from livespec_dev_tooling import green_token
    from livespec_dev_tooling._green_token_evidence import (
        ValidationScope,
        persist_pre_commit_evidence,
        write_evidence,
    )

    root, _ = project
    token = root / ".git" / "livespec-green-token.json"
    _ = token.write_text("preserve-existing-proof")
    validation = ValidationScope(mode=mode, scope=scope)
    log = structlog.get_logger()
    with pytest.raises(ValueError, match="normal full-suite"):
        write_evidence(
            path=token, tree_hash="tree", run_id="run", output_checksum="sum", validation=validation
        )
    assert (
        persist_pre_commit_evidence(
            path=token,
            tree_hash="tree",
            run_id="run",
            output_checksum="sum",
            log=log,
            validation=validation,
        )
        == 1
    )
    assert green_token.write_token(cwd=root, log=log, validation=validation) == 1
    assert (
        green_token.write_pre_commit_evidence(
            cwd=root, log=log, run_id="run", output_checksum="sum", validation=validation
        )
        == 1
    )
    assert token.read_text() == "preserve-existing-proof"


def test_green_token_reader_refuses_partial_on_matching_clean_tree(
    project: tuple[Path, str],
) -> None:
    import structlog

    from livespec_dev_tooling import green_token

    root, _ = project
    _ = _git(root, "commit", "-qm", "repair")
    log = structlog.get_logger()
    assert green_token.write_token(cwd=root, log=log) == 0
    assert green_token.check_token(cwd=root, log=log) == 0
    path = root / ".git" / "livespec-green-token.json"
    record = json.loads(path.read_text())
    record["mode"] = "expedited-repair"
    _ = path.write_text(json.dumps(record))
    assert green_token.check_token(cwd=root, log=log) == 1


def test_pre_commit_reader_accepts_only_normal_provenance(project: tuple[Path, str]) -> None:
    import structlog

    from livespec_dev_tooling import green_token

    root, _ = project
    assert (
        green_token.write_pre_commit_evidence(
            cwd=root, log=structlog.get_logger(), run_id="full-aggregate", output_checksum="sum"
        )
        == 0
    )
    evidence = green_token.read_pre_commit_evidence(cwd=root)
    assert evidence is not None
    assert evidence.tree_hash == _git(root, "write-tree")
    assert evidence.run_id == "full-aggregate"
    path = root / ".git" / "livespec-green-token.json"
    record = json.loads(path.read_text())
    record["scope"] = "focused-tests-and-touched-files"
    _ = path.write_text(json.dumps(record))
    assert green_token.read_pre_commit_evidence(cwd=root) is None


def test_nested_aggregate_metadata_is_rejected() -> None:
    token = {
        "pre_commit_aggregate": {
            "tree_hash": "tree",
            "run_id": "run",
            "output_checksum": "sum",
            "captured_at": "now",
            "scope": "focused",
        }
    }
    assert read_evidence_text(text=json.dumps(token)) is None


def test_untracked_executable_input_is_refused(project: tuple[Path, str]) -> None:
    root, base = project
    _ = (root / "src/untracked.py").write_text("VALUE = 1\n")
    assert "untracked source" in _collect(root, base)["reason"]


def test_non_launcher_pytest_literal_is_not_deferred(project: tuple[Path, str]) -> None:
    root, base = project
    _ = (root / "tests/test_word.py").write_text(
        'def test_word():\n    assert "pytest" == "pytest"\n'
    )
    _ = _git(root, "add", ".")
    assert _collect(root, base)["outcome"] == "passed"


def test_test_mutation_invalidates_exact_tree(project: tuple[Path, str]) -> None:
    root, base = project
    _ = (root / "tests/test_widget.py").write_text(
        "from pathlib import Path\nfrom src.widget import answer\n"
        "def test_answer():\n    assert answer() == 43\n"
        '    Path("src/widget.py").write_text("CHANGED = 1\\n")\n'
    )
    _ = _git(root, "add", ".")
    assert "incident tree changed during collection" in _collect(root, base)["risks"]


@pytest.mark.parametrize("timeout", [0, 60])
def test_unbounded_timeout_is_refused(project: tuple[Path, str], timeout: float) -> None:
    root, base = project
    assert "below sixty" in _collect(root, base, timeout=timeout)["reason"]


def test_timeout_records_incomplete_proof(project: tuple[Path, str]) -> None:
    root, base = project
    assert _collect(root, base, timeout=0.001)["outcome"] == "incomplete"


def test_broken_git_is_named_refusal(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n'
    )
    context = SimpleNamespace(mode="expedited-repair", identity=SimpleNamespace(head_sha="head"))
    result = collect_focused_evidence(
        repo_root=tmp_path,
        context=context,
        scope=FocusedScope(
            tree_hash="tree",
            source_prefixes=("src/",),
            test_prefixes=("tests/",),
            related_tests=("tests/test_x.py",),
        ),
        manual=ManualReproduction(
            procedure="call", expected="good", observed="good", outcome="passed"
        ),
    )
    assert result["outcome"] == "refused"
    assert "unavailable" in result["reason"]


@pytest.mark.parametrize("prefixes", [(), ("src/narrow/",)])
def test_source_scope_cannot_hide_touched_product(project, prefixes) -> None:
    root, base = project
    assert "configured source scope" in _collect(root, base, source_prefixes=prefixes)["reason"]


def test_unsupported_executable_is_incomplete(project) -> None:
    root, base = project
    (root / "src/recover.sh").write_text("#!/bin/sh\nexit 0\n")
    _git(root, "add", ".")
    evidence = _collect(root, base)
    assert evidence["outcome"] == "incomplete"
    assert evidence["paths"]["src/recover.sh"] == "unsupported-executable"


def test_nested_shared_fixture_is_refused(project) -> None:
    root, base = project
    (root / "tests/conftest.py").write_text("import pytest\npytest.main([])\n")
    _git(root, "add", ".")
    evidence = _collect(root, base, related_test_reason="widget fixture consumer")
    assert "nested suite launcher" in evidence["reason"]


def test_inherited_incident_flags_do_not_change_fixture_verdict(project, monkeypatch) -> None:
    root, base = project
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE_REVERT", "1")
    (root / "tests/test_widget.py").write_text(
        "import os\nfrom src.widget import answer\n"
        "def test_fixture():\n"
        "    assert 'EXPEDITED_INCIDENT_RESPONSE' not in os.environ\n"
        "    assert 'EXPEDITED_INCIDENT_RESPONSE_REVERT' not in os.environ\n"
        "    assert answer() == 43\n"
        "    assert False, 'real fixture refusal'\n"
    )
    _git(root, "add", ".")
    evidence = _collect(root, base)
    assert evidence["outcome"] == "failed"
    assert "real fixture refusal" in evidence["tests"]["output"]


@pytest.mark.parametrize("prior", ["../outside.py", "/outside.py"])
def test_scope_escape_is_refused(project: tuple[Path, str], prior: str) -> None:
    root, base = project
    assert "scope escapes" in _collect(root, base, prior_paths=(prior,))["reason"]


@pytest.mark.parametrize("prefixes", [(), ("/",)])
def test_test_scope_must_be_explicit(project: tuple[Path, str], prefixes: tuple[str, ...]) -> None:
    root, base = project
    assert "explicit test prefixes" in _collect(root, base, test_prefixes=prefixes)["reason"]


@pytest.mark.parametrize("deferred", [(("missing.py", "reason"),), (("tests/test_widget.py", ""),)])
def test_invalid_deferral_is_refused(
    project: tuple[Path, str], deferred: tuple[tuple[str, str], ...]
) -> None:
    root, base = project
    assert "invalid deferred" in _collect(root, base, deferred_tests=deferred)["reason"]


def test_deferring_every_test_cannot_pass(project: tuple[Path, str]) -> None:
    root, base = project
    evidence = _collect(root, base, deferred_tests=(("tests/test_widget.py", "unavailable"),))
    assert "explicit existing tests" in evidence["reason"]


def test_related_test_must_be_tracked(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "untracked_test.py").write_text("def test_extra():\n    assert True\n")
    evidence = _collect(root, base, related_tests=("untracked_test.py",))
    assert "exact tracked tree" in evidence["reason"]


@pytest.mark.parametrize("mode", ["normal", "emergency-revert"])
def test_non_repair_context_is_refused(project: tuple[Path, str], mode: str) -> None:
    root, base = project
    context = _context(root, base)
    context.mode = mode
    evidence = collect_focused_evidence(
        repo_root=root,
        context=context,
        scope=FocusedScope(
            tree_hash=_git(root, "write-tree"),
            source_prefixes=("src/",),
            test_prefixes=("tests/",),
            related_tests=("tests/test_widget.py",),
        ),
        manual=ManualReproduction(procedure="call", expected="43", observed="43", outcome="passed"),
    )
    assert "resolved expedited repair" in evidence["reason"]


@pytest.mark.parametrize(
    ("manual", "outcome"),
    [
        (
            ManualReproduction(procedure="call", expected="43", observed="wrong", outcome="failed"),
            "failed",
        ),
        (
            ManualReproduction(
                procedure="call", expected="43", observed="not observed", outcome="pending"
            ),
            "incomplete",
        ),
        (
            ManualReproduction(procedure="call", expected="", observed="43", outcome="passed"),
            "refused",
        ),
    ],
)
def test_manual_proof_must_be_complete_and_pass(
    project: tuple[Path, str], manual: ManualReproduction, outcome: str
) -> None:
    root, base = project
    assert _collect(root, base, manual=manual)["outcome"] == outcome


def test_non_test_child_command_is_allowed(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "tests/test_widget.py").write_text(
        "import subprocess\nfrom src.widget import answer\n"
        "def test_answer():\n    assert answer() == 43\n"
        "    assert subprocess.run(['/bin/true']).returncode == 0\n"
    )
    _git(root, "add", ".")
    assert _collect(root, base)["outcome"] == "passed"


@pytest.mark.parametrize("prefixes", [("tests/narrow/",), ("other/",), ("tests/", "other/")])
def test_test_scope_cannot_hide_changed_tests_or_helpers(
    project: tuple[Path, str], prefixes: tuple[str, ...]
) -> None:
    root, base = project
    (root / "tests/test_regression.py").write_text("def test_regression():\n    assert False\n")
    (root / "tests/conftest.py").write_text("SHARED = 1\n")
    _git(root, "add", ".")
    evidence = _collect(root, base, test_prefixes=prefixes)
    assert evidence["outcome"] == "refused"
    assert "configured test scope" in evidence["reason"]


def test_configured_nondefault_test_scope_is_supported(project: tuple[Path, str]) -> None:
    root, base = project
    (root / "tests").rename(root / "checks")
    (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\ntests_tree_prefix = "checks/"\n'
    )
    _git(root, "add", ".")
    evidence = _collect(
        root, base, test_prefixes=("checks/",), related_tests=("checks/test_widget.py",)
    )
    assert evidence["outcome"] == "passed"
    assert evidence["selection"]["tests"] == ["checks/test_widget.py"]


def test_a_large_touched_module_keeps_its_record_under_the_argument_limit(
    project: tuple[Path, str],
) -> None:
    # livespec-dev-tooling-l6u6cd: per-line coverage contexts made a 193 KB record that no
    # single argv string (128 KiB) could carry to the authority.
    root, base = project
    body = "".join(f"    x{n} = {n}\n" for n in range(6000))
    (root / "src/widget.py").write_text(f"def answer():\n{body}    return 43\n")
    _git(root, "add", ".")
    evidence = _collect(root, base)
    row = evidence["coverage"]["src/widget.py"]
    assert evidence["outcome"] == "passed"
    assert set(row) == {"summary", "missing_lines", "missing_branches"}
    assert len(json.dumps(evidence, sort_keys=True, separators=(",", ":"))) < 131072
