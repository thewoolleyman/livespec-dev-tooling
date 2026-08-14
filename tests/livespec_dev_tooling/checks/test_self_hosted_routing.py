"""Outside-in test for `livespec_dev_tooling/checks/self_hosted_routing.py`.

The check is a SECURITY guard over a repo's own `.github/workflows/*.yml` /
`*.yaml`. It fails (exit 1) on either of two independent holes:

1. FORBIDDEN TRIGGER REACHES A GATING SELF-HOSTED JOB. A workflow whose `on:`
   set contains any of `pull_request_target`, `workflow_run`, `issue_comment`,
   `repository_dispatch`, `merge_group`, `workflow_dispatch` AND whose
   `runs-on` references a GATING self-hosted label. The gating label set is
   consumer-declared (`gating_self_hosted_labels`) UNIONED with the built-in
   default `local-ci`, so declaring a new label can never remove coverage of
   an existing one.
2. FAIL-OPEN ROUTING. A `runs-on` repo-variable expression whose fallback
   literal names a self-hosted label. Deleting the repo variable would then
   route the merge gate to self-hosted capacity that may not exist; the
   fallback MUST name hosted capacity instead.

It is a no-op (exit 0) for a repo with no gating self-hosted job and no
self-hosted fallback.

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
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from livespec_dev_tooling.checks import self_hosted_routing
from livespec_dev_tooling.checks._self_hosted_routing_parse import (
    fail_open_reason,
    repo_variable_fallback,
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


def _write_gating_labels(*, tmp_path: Path, labels: tuple[str, ...]) -> None:
    """Declare `gating_self_hosted_labels` in a `pyproject.toml` at `tmp_path`."""
    declared = ", ".join(f'"{label}"' for label in labels)
    body = f"[tool.livespec_dev_tooling]\ngating_self_hosted_labels = [{declared}]\n"
    _ = (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")


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


# --- Real fleet forms --------------------------------------------------------

# livespec's CURRENT ci.yml form: the repo-variable fallback names HOSTED
# capacity, so deleting the variable fails CLOSED to `ubuntu-latest`.
_CI_FROMJSON_HOSTED_FALLBACK = (
    "name: CI\n"
    "on:\n"
    "  pull_request:\n"
    "  push:\n"
    "    branches: [master]\n"
    "jobs:\n"
    "  check:\n"
    "    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]') }}\n"
    "    steps:\n"
    "      - run: just check\n"
)

# The RETIRED form livespec carried before the fail-closed repair: the fallback
# names self-hosted capacity, so deleting the variable routed the merge gate to
# a runner that may not exist.
_CI_FROMJSON_SELF_HOSTED_FALLBACK = (
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


def test_hosted_fallback_with_only_allowed_triggers_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (c): a `runs-on` fallback naming hosted capacity → exit 0."""
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=_CI_FROMJSON_HOSTED_FALLBACK)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"a hosted fail-closed fallback should pass; combined={combined!r}"


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


# --- Hole 1: forbidden trigger reaches a gating self-hosted job → FAIL -------


def test_workflow_dispatch_to_local_ci_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (d)/(i): `workflow_dispatch` + a `local-ci` job → exit 1, naming the trigger."""
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
    assert findings[0].get("gating_labels") == ["local-ci"]


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


def test_quoted_on_key_forbidden_trigger_to_local_ci_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A quoted `"on":` key + `workflow_dispatch` + a local-ci job → exit 1.

    YAML 1.1 reads a bare `on` as the boolean `true`, so authors legitimately
    quote the key as `"on":` (or `'on':`). The guard must see the trigger block
    under a quoted key exactly as it does under the bare key — else a forbidden
    trigger hides behind the quoting.
    """
    body = (
        "name: bad-quoted\n"
        '"on":\n'
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="quoted.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"workflow_dispatch under a quoted on-key must fail; combined={combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("forbidden_triggers") == ["workflow_dispatch"]


# --- The consumer-declared gating label set ---------------------------------


def test_declared_label_with_forbidden_trigger_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (a): a NEWLY-DECLARED gating label + a forbidden trigger → exit 1.

    This is the blind spot the change closes. Before the label set became
    consumer-declared, a repo adopting a dedicated runner label silently lost
    the forbidden-trigger guard on exactly the jobs it governs.
    """
    _write_gating_labels(tmp_path=tmp_path, labels=("hetzner-prod",))
    body = (
        "name: hetzner\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, hetzner-prod]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="hetzner.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"a declared gating label must be guarded; combined={combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("gating_labels") == ["hetzner-prod"]


def test_undeclared_label_with_forbidden_trigger_is_out_of_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A self-hosted label nobody declared is out of scope → exit 0.

    The negative half of the test above: coverage follows the DECLARATION, so
    the check cannot silently widen to labels a consumer never nominated.
    """
    body = (
        "name: other\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, some-other-label]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="other.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"an undeclared self-hosted label is out of scope; combined={combined!r}"


def test_declaring_a_label_does_not_drop_the_default_local_ci(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (d): declaring a new label UNIONS with `local-ci`, never replaces it.

    A security guard must not lose coverage through configuration. A consumer
    that declares only its new dedicated label still has every `local-ci` job
    guarded.
    """
    _write_gating_labels(tmp_path=tmp_path, labels=("hetzner-prod",))
    body = (
        "name: still-guarded\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, local-ci]\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="still.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"declaring a label must not drop local-ci coverage; combined={combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("gating_labels") == ["local-ci"]


def test_privileged_orchestrator_tier_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (e): `[self-hosted, livespec-orchestrator]` on workflow_dispatch → exit 0.

    The gate runner is a deliberately-privileged tier that v192's Scope section
    carves out of the Event-routing clause and delegates to the owning
    repository's own specification. It is absent from the default gating set,
    so it is exempt unless a consumer explicitly nominates it.
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
    assert rc == 0, f"the privileged tier is out of scope; combined={combined!r}"


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


# --- Hole 2: a fail-open repo-variable fallback → FAIL ----------------------


def test_self_hosted_fallback_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (b): a fallback naming self-hosted capacity → exit 1, naming the value.

    Only allowed triggers are present, so this isolates the fail-open finding
    from the forbidden-trigger one.
    """
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=_CI_FROMJSON_SELF_HOSTED_FALLBACK)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"a self-hosted fallback must fail; combined={combined!r}"
    findings = _findings(combined=combined)
    assert len(findings) == 1, f"expected exactly one fail-open finding; got {findings!r}"
    assert findings[0].get("level") == "error"
    assert findings[0].get("workflow") == ".github/workflows/ci.yml"
    assert "self-hosted" in str(findings[0].get("runs_on"))
    assert findings[0].get("reason") == "fallback names self-hosted capacity"


def test_unquoted_self_hosted_fallback_fails_without_raising(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (h): the UNQUOTED fallback that crashed the first implementation.

    A `vars.X || <bare-token>` expression carries no quote after `||`. The
    superseded implementation's regex returned no match there while a `cast()`
    stood in for the runtime check, so `.group()` raised `AttributeError` — a
    security check crashing rather than returning a verdict. The guard must
    reach a verdict on this shape, and here that verdict is a FINDING.
    """
    body = (
        "name: unquoted\n"
        "on:\n"
        "  pull_request:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ${{ vars.CI_RUNNER_LABELS || self-hosted }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="unquoted.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"an unquoted self-hosted fallback must fail, not crash; {combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("reason") == "fallback names self-hosted capacity"


def test_empty_fallback_is_reported_not_silently_passed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fallback operator with NO literal after it is reported, never a silent pass.

    The totality rule has two halves: never raise, and never pass silently on
    something the guard could not resolve. An expression that offers a fallback
    and then supplies nothing is unresolvable, so it is named rather than
    waved through.
    """
    body = (
        "name: empty\n"
        "on:\n"
        "  pull_request:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ${{ vars.CI_RUNNER_LABELS || }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="empty.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"an unresolvable fallback must be reported; combined={combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("reason") == "fallback literal is unresolvable"


def test_declared_label_named_in_fallback_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fallback naming a DECLARED gating label (without the bare `self-hosted`) fails."""
    _write_gating_labels(tmp_path=tmp_path, labels=("hetzner-prod",))
    body = (
        "name: decl\n"
        "on:\n"
        "  pull_request:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"hetzner-prod\"]') }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="decl.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1, f"a declared gating label in a fallback must fail; combined={combined!r}"
    findings = _findings(combined=combined)
    assert findings[0].get("reason") == "fallback names self-hosted capacity"


def test_repeated_identical_fallback_reported_once_per_workflow(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two jobs sharing one offending `runs-on` value yield one finding, not two."""
    body = (
        "name: twice\n"
        "on:\n"
        "  pull_request:\n"
        "jobs:\n"
        "  a:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"self-hosted\"]') }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
        "  b:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"self-hosted\"]') }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="twice.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    findings = _findings(combined=combined)
    assert len(findings) == 1, f"identical values must dedupe within a workflow; {findings!r}"


# --- No-op cases -------------------------------------------------------------


def test_no_workflows_dir_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo with no `.github/workflows/` directory → exit 0 (genuine no-op)."""
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"no workflows dir should be a no-op; combined={combined!r}"


def test_no_self_hosted_job_anywhere_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance (f): a forbidden trigger on an `ubuntu-latest` job → exit 0.

    The normal fleet case: a repo with no self-hosted job and no self-hosted
    fallback is a clean no-op, so this check never reddens a sibling that has
    nothing to guard.
    """
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
    assert rc == 0, f"non-self-hosted job must be a no-op even on a forbidden trigger; {combined!r}"


def test_hosted_fallback_on_forbidden_trigger_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hosted fallback is fine even under a forbidden trigger → exit 0.

    The fail-open finding is about the FALLBACK, and the forbidden-trigger
    finding is about a self-hosted LABEL actually being referenced. Neither
    applies here, and the two rules must not leak into one another.
    """
    body = (
        "name: hosted-dispatch\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]') }}\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="hosted.yml", body=body)
    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, f"a hosted fallback is never a finding; combined={combined!r}"


def test_router_call_on_forbidden_trigger_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hosted router remains a gating route, not an exemption from trigger safety.

    Its output is deliberately dynamic, so a `runs-on`-only scan would miss a
    `workflow_dispatch` caller and permit it to select local capacity.  The
    router invocation itself must therefore carry the same forbidden-trigger
    protection as a literal local-ci `runs-on` expression.
    """
    body = (
        "name: unsafe-router\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  select-ci-runner:\n"
        "    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/"
        "reusable-ci-runner-router.yml@v1\n"
        "    with:\n"
        '      local-runner-labels: \'["self-hosted","local-ci"]\'\n'
        "      trusted: true\n"
    )
    _ = _write_workflow(tmp_path=tmp_path, name="unsafe-router.yml", body=body)

    rc, combined = _run_main(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1
    findings = _findings(combined=combined)
    assert findings[0].get("workflow") == ".github/workflows/unsafe-router.yml"
    assert "ci-runner-router" in str(findings[0].get("gating_labels"))


def test_mixed_clean_and_bad_workflows_reports_only_the_bad(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean `.yaml` alongside a bad `.yml` → one finding for the bad file only.

    Exercises both globs, the skip-clean branch, and the append-bad branch of
    the collector in one scan.
    """
    _ = _write_workflow(tmp_path=tmp_path, name="clean.yaml", body=_CI_FROMJSON_HOSTED_FALLBACK)
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


# --- Totality: a verdict for ANY `runs-on`, and never an exception -----------


_MALFORMED_RUNS_ON: tuple[str, ...] = (
    "${{ vars.CI_RUNNER_LABELS || self-hosted }}",
    "${{ vars.CI_RUNNER_LABELS || }}",
    "${{ vars.X || 'ubuntu-latest' }}",
    "${{ fromJSON(vars.X || '[\"self-hosted\"]') }}",
    '${{ fromJSON(vars.X || "[\\"self-hosted\\"]") }}',
    "${{ vars.X ||",
    "|| vars.X",
    "vars.X ||",
    "[self-hosted, local-ci]",
    "ubuntu-latest",
    "",
    "   ",
    "${{ matrix.os }}",
    "${{ vars.A || vars.B || 'x' }}",
    "'''",
    '"',
    "}}",
    "((((",
)


@pytest.mark.parametrize("value", _MALFORMED_RUNS_ON)
def test_repo_variable_fallback_returns_a_verdict_for_known_malformed_forms(*, value: str) -> None:
    """Acceptance (g), enumerated half: each recorded malformed form yields a verdict.

    The corpus is a STARTING SET, not the specification — the property test
    below is what constrains the whole input space. `None` (no fallback
    offered) and `str` (the fallback text, possibly empty) are the only two
    outcomes; an exception is not one of them.
    """
    result = repo_variable_fallback(value=value)
    assert result is None or isinstance(result, str), f"unexpected verdict {result!r}"


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(value=st.text())
def test_repo_variable_fallback_never_raises_for_any_text(*, value: str) -> None:
    """Acceptance (g): TOTALITY over the whole input space — a verdict, never a raise.

    Enumerating input cases is what let the first implementation ship a crash:
    every stated control used a QUOTED fallback, so an unquoted one passed
    them all and still raised. The property is stated over arbitrary text
    precisely so no enumeration has to be complete.
    """
    result = repo_variable_fallback(value=value)
    assert result is None or isinstance(result, str), f"unexpected verdict {result!r}"


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(value=st.text())
def test_runs_on_verdict_never_raises_for_any_text(*, value: str) -> None:
    """The parent's fail-open verdict is total over arbitrary `runs-on` text too.

    `repo_variable_fallback` being total is necessary but not sufficient — the
    caller that interprets its result must be total as well, or the crash just
    moves one frame up.
    """
    reason = fail_open_reason(
        value=value, self_hosted_labels=frozenset({"local-ci", "self-hosted"})
    )
    assert reason is None or isinstance(reason, str), f"unexpected verdict {reason!r}"


# --- Pure parser unit coverage: repo_variable_fallback ----------------------


def test_fallback_absent_without_vars_reference() -> None:
    """No `vars.` reference → no fallback offered at all."""
    assert repo_variable_fallback(value="ubuntu-latest") is None


def test_fallback_absent_without_or_operator() -> None:
    """A `vars.` reference with no `||` → no fallback offered."""
    assert repo_variable_fallback(value="${{ vars.CI_RUNNER_LABELS }}") is None


def test_fallback_strips_json_array_quotes_and_expression_tail() -> None:
    """The canonical `fromJSON(vars.X || '[...]')` form resolves to the bare array text."""
    value = "${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]') }}"
    assert repo_variable_fallback(value=value) == '["ubuntu-latest"]'


def test_fallback_resolves_unquoted_token() -> None:
    """An unquoted fallback token resolves to that token — the attempt-1 crash shape."""
    assert repo_variable_fallback(value="${{ vars.X || ubuntu-latest }}") == "ubuntu-latest"


def test_fallback_resolves_single_quoted_scalar() -> None:
    assert repo_variable_fallback(value="${{ vars.X || 'ubuntu-latest' }}") == "ubuntu-latest"


def test_fallback_empty_when_nothing_follows_the_operator() -> None:
    """The unresolvable case is an EMPTY string, distinct from `None` (none offered)."""
    assert repo_variable_fallback(value="${{ vars.X || }}") == ""


def test_fallback_takes_the_last_alternative_in_a_chain() -> None:
    """`a || b || c` falls back to `c` — the value used when every earlier term is empty."""
    assert repo_variable_fallback(value="${{ vars.A || vars.B || 'x' }}") == "x"


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


def test_triggers_double_quoted_on_key_block_mapping() -> None:
    """A `"on":` (double-quoted) block key resolves its trigger names."""
    assert workflow_triggers(stripped='"on":\n  push:\n  workflow_dispatch:\n') == frozenset(
        {"push", "workflow_dispatch"}
    )


def test_triggers_single_quoted_on_key_scalar() -> None:
    """A `'on':` (single-quoted) scalar resolves its single trigger."""
    assert workflow_triggers(stripped="'on': push") == frozenset({"push"})


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
