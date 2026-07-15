"""Outside-in test for `livespec_dev_tooling/checks/self_hosted_routing.py`.

The check is a SECURITY guard: reading only a repo's own
`.github/workflows/*.yml` / `*.yaml`, it fails (exit 1) when any workflow that
routes a FORBIDDEN trigger (`pull_request_target`, `workflow_run`,
`issue_comment`, `repository_dispatch`, `merge_group`, `workflow_dispatch`)
also has a job whose `runs-on` references the `local-ci` self-hosted label. It
is a no-op (exit 0) for a repo with no `local-ci` job.

`main()` is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` + `rc =
main()`) rather than via a `sys.executable` subprocess, mirroring
`test_no_todo_registry` — no `COVERAGE_PROCESS_START` child, no `.coverage.*`
race under the parallel dispatcher, and materially faster. The pure parsers in
the private sibling `_self_hosted_routing_parse` are exercised directly for
precise branch coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import self_hosted_routing
from livespec_dev_tooling.checks._self_hosted_routing_parse import (
    runs_on_values,
    strip_yaml_comments,
    workflow_triggers,
)

__all__: list[str] = []


def _write_workflow(*, tmp_path: Path, name: str, body: str) -> Path:
    """Write a workflow file under `tmp_path/.github/workflows/`."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / name
    _ = path.write_text(body, encoding="utf-8")
    return path


def _run_main(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    """Invoke `main()` in-process under `tmp_path`; return (returncode, stderr)."""
    monkeypatch.chdir(tmp_path)
    rc = self_hosted_routing.main()
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def _findings(*, combined: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line diagnostics from captured output."""
    return [json.loads(line) for line in combined.splitlines() if line.strip().startswith("{")]


# --- Real fleet forms: both livespec `local-ci` workflows must PASS ---------


_CI_FROMJSON_LOCAL_CI = (
    "name: CI\n"
    "on:\n"
    "  pull_request:\n"
    "  push:\n"
    "    branches: [master]\n"
    "jobs:\n"
    "  check:\n"
    '    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || \'["self-hosted","local-ci"]\') }}\n'
    "    steps:\n"
    "      - run: just check\n"
)

_SHADOW_LIST_LOCAL_CI = (
    "# ci-selfhosted-shadow.yml — NON-GATING local self-hosted CI shadow lane.\n"
    "#   * triggers ONLY on push to ci-shadow/** —\n"
    "#     NEVER pull_request / merge_group / workflow_dispatch, so it is not a\n"
    "#     status check on any PR and cannot gate a merge.\n"
    "name: CI self-hosted shadow (non-gating)\n"
    "on:\n"
    "  push:\n"
    "    branches:\n"
    '      - "ci-shadow/**"\n'
    "jobs:\n"
    "  slot:\n"
    "    runs-on: [self-hosted, local-ci]\n"
    "    steps:\n"
    "      - run: echo hi\n"
)


def test_fromjson_local_ci_with_only_allowed_triggers_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The livespec ci.yml form (fromJSON local-ci, on: pull_request+push) → exit 0."""
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=_CI_FROMJSON_LOCAL_CI)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"fromJSON local-ci on allowed triggers should pass; combined={combined!r}"


def test_shadow_list_local_ci_with_comment_naming_forbidden_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shadow lane: `[self-hosted, local-ci]` + push-only, header comment NAMES forbidden → exit 0.

    Proves comment immunity — the `# NEVER ... workflow_dispatch` header must
    NOT be read as a real trigger (the exact false positive a raw grep hits).
    """
    _ = _write_workflow(tmp_path=tmp_path, name="shadow.yml", body=_SHADOW_LIST_LOCAL_CI)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"push-only local-ci with a forbidden-naming comment should pass; {combined!r}"


# --- The security hole: forbidden trigger reaches a local-ci job → FAIL ------


def test_workflow_dispatch_to_local_ci_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`workflow_dispatch` + a `local-ci` job → exit 1, error diagnostic naming the trigger."""
    body = (
        "name: bad\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="bad.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"workflow_dispatch to a local-ci job must fail; combined={combined!r}"
    findings = _findings(combined=combined)
    assert len(findings) == 1, f"expected one finding; got {findings!r}"
    assert (
        findings[0].get("level") == "error"
    ), f"security guard must be error-level; {findings[0]!r}"
    assert findings[0].get("forbidden_triggers") == ["workflow_dispatch"]
    assert findings[0].get("workflow") == ".github/workflows/bad.yml"


def test_flow_list_multiple_forbidden_triggers_reported_sorted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`on: [merge_group, workflow_run]` + local-ci → both reported, sorted."""
    body = (
        "name: bad2\n"
        "on: [merge_group, workflow_run, push]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="bad2.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    findings = _findings(combined=combined)
    assert findings[0].get("forbidden_triggers") == [
        "merge_group",
        "workflow_run",
    ], f"push is allowed and must be excluded; forbidden must be sorted; got {findings[0]!r}"


def test_scalar_forbidden_trigger_to_local_ci_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scalar `on: repository_dispatch` + a block-list local-ci runs-on → exit 1."""
    body = (
        "name: bad3\n"
        "on: repository_dispatch\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on:\n"
        "      - self-hosted\n"
        "      - local-ci\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="bad3.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"scalar repository_dispatch to block-list local-ci must fail; {combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("forbidden_triggers") == ["repository_dispatch"]


# --- The privileged second tier must NOT be flagged (keyed on local-ci) ------


def test_privileged_orchestrator_tier_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `[self-hosted, livespec-orchestrator]` job on workflow_dispatch is out of scope → exit 0.

    The gate runner is a deliberately-privileged, separately-tested tier; keying
    on `local-ci` (not generic `self-hosted`) exempts it automatically.
    """
    body = (
        "name: gate\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "  repository_dispatch:\n"
        "jobs:\n"
        "  golden:\n"
        "    runs-on: [self-hosted, livespec-orchestrator]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="gate.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"a non-local-ci self-hosted job is out of scope; combined={combined!r}"


def test_local_ci_with_only_allowed_triggers_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`local-ci` job on `pull_request` + `schedule` (both allowed) → exit 0."""
    body = (
        "name: ok\n"
        "on:\n"
        "  pull_request:\n"
        "  schedule:\n"
        "    - cron: '0 0 * * *'\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="ok.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"pull_request/schedule are allowed for local-ci; combined={combined!r}"


# --- No-op cases -------------------------------------------------------------


def test_no_workflows_dir_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo with no `.github/workflows/` directory → exit 0 (genuine no-op)."""
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"no workflows dir should be a no-op; combined={combined!r}"


def test_no_local_ci_job_anywhere_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A forbidden trigger on an `ubuntu-latest` (non-local-ci) job → exit 0 (the normal fleet case)."""
    body = (
        "name: normal\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="normal.yaml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"non-local-ci job must be a no-op even on a forbidden trigger; {combined!r}"


def test_mixed_clean_and_bad_workflows_reports_only_the_bad(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean `.yaml` alongside a bad `.yml` → one finding for the bad file only.

    Exercises both globs, the skip-clean branch, and the append-bad branch of
    the collector in one scan.
    """
    _ = _write_workflow(tmp_path=tmp_path, name="clean.yaml", body=_CI_FROMJSON_LOCAL_CI)
    bad = (
        "name: bad\n"
        "on:\n"
        "  issue_comment:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="bad.yml", body=bad)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    findings = _findings(combined=combined)
    assert len(findings) == 1, f"only the bad workflow should be flagged; got {findings!r}"
    assert findings[0].get("workflow") == ".github/workflows/bad.yml"


# --- Pure parser unit coverage: strip_yaml_comments -------------------------


def test_strip_removes_trailing_comment() -> None:
    assert "comment" not in strip_yaml_comments(source="key: value  # comment")


def test_strip_removes_whole_line_comment() -> None:
    assert strip_yaml_comments(source="# whole") == ""


def test_strip_preserves_hash_without_leading_space() -> None:
    """`x#y` (no space before `#`) is part of the scalar, not a comment."""
    assert strip_yaml_comments(source="u: http://x#y") == "u: http://x#y"


def test_strip_preserves_hash_inside_single_quotes() -> None:
    assert strip_yaml_comments(source="a: 'x # y'") == "a: 'x # y'"


def test_strip_preserves_hash_inside_double_quotes() -> None:
    assert strip_yaml_comments(source='a: "x # y"') == 'a: "x # y"'


def test_strip_single_quote_inside_double_is_not_a_toggle() -> None:
    """An apostrophe inside a double-quoted scalar does not open a single-quote span."""
    assert strip_yaml_comments(source='a: "he\'s # ok"') == 'a: "he\'s # ok"'


def test_strip_double_quote_inside_single_is_not_a_toggle() -> None:
    """A double quote inside a single-quoted scalar does not open a double-quote span."""
    assert strip_yaml_comments(source="a: 'say \"x\" # ok'") == "a: 'say \"x\" # ok'"


def test_strip_returns_plain_line_unchanged() -> None:
    assert strip_yaml_comments(source="plain: line") == "plain: line"


# --- Pure parser unit coverage: workflow_triggers ---------------------------


def test_triggers_flow_list() -> None:
    assert workflow_triggers(stripped="on: [push, pull_request]") == frozenset(
        {"push", "pull_request"}
    )


def test_triggers_flow_list_unclosed_is_tolerated() -> None:
    """A malformed (unclosed) flow list still yields its tokens."""
    assert workflow_triggers(stripped="on: [push, workflow_run") == frozenset(
        {"push", "workflow_run"}
    )


def test_triggers_empty_flow_list() -> None:
    assert workflow_triggers(stripped="on: []") == frozenset()


def test_triggers_scalar() -> None:
    assert workflow_triggers(stripped="on: push") == frozenset({"push"})


def test_triggers_block_mapping_ignores_deeper_keys() -> None:
    """Block form: only the first-child trigger keys count; `branches:`/bullets do not."""
    stripped = (
        "name: x\n"
        "on:\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  x:\n"
    )
    assert workflow_triggers(stripped=stripped) == frozenset({"push", "workflow_dispatch"})


def test_triggers_block_mapping_at_eof() -> None:
    """A block-form `on:` that runs to end-of-file (no trailing dedent) still parses."""
    assert workflow_triggers(stripped="on:\n  push:\n  workflow_dispatch:\n") == frozenset(
        {"push", "workflow_dispatch"}
    )


def test_triggers_absent_on_key_is_empty() -> None:
    assert workflow_triggers(stripped="name: x\njobs:\n  a:\n") == frozenset()


# --- Pure parser unit coverage: runs_on_values ------------------------------


def test_runs_on_inline_flow_list() -> None:
    stripped = "jobs:\n  a:\n    runs-on: [self-hosted, local-ci]\n    container: foo\n"
    assert runs_on_values(stripped=stripped) == ["[self-hosted, local-ci]"]


def test_runs_on_block_list_gathers_bullets_across_blank() -> None:
    stripped = "jobs:\n  a:\n    runs-on:\n      - self-hosted\n\n      - local-ci\n"
    values = runs_on_values(stripped=stripped)
    assert len(values) == 1
    assert "local-ci" in values[0]


def test_runs_on_absent_yields_empty_list() -> None:
    assert runs_on_values(stripped="name: x\njobs:\n  a:\n    steps: []\n") == []
