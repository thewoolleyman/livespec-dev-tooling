"""Outside-in test for `livespec_dev_tooling/checks/ci_gate_parity.py`.

The companion to `ci_matrix_completeness`: from a repo's OWN
`.github/workflows/ci.yml`, it asserts the livespec invariant PR gate ≡
master gate — no GATING job (one in the `ci-green` gate's `needs:`) may
condition its real steps on a changeset `.py`-detection output (`py_changed`),
which would run it on a `push` to master but skip/reduce it on a doc-only
`pull_request`.

The scan ALWAYS runs; the `LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST` lever
only flips findings from WARNING (exit 0) to ERROR (exit 4). That var is
CLEARED from every subprocess unless a test sets it explicitly, so a test's
expected exit code cannot depend on the host that runs it (this repo's CI arms
the lever for the whole metadata batch, exactly as it does the ci-matrix
lever — see the ci_matrix_completeness test for the full rationale).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "ci_gate_parity.py"

# Env vars that change the check's VERDICT rather than its behavior. Cleared
# from every subprocess unless a test names one.
_AMBIENT_SEVERITY_VARS = ("LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST",)


def _run_check(
    *,
    cwd: Path,
    extra_argv: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(_CHECK)]
    if extra_argv is not None:
        argv.extend(extra_argv)
    run_env: dict[str, str] = {**os.environ, **(env or {})}
    for var in _AMBIENT_SEVERITY_VARS:
        if env is None or var not in env:
            run_env.pop(var, None)
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line findings from the check's stderr."""
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def _write_ci_yml(*, cwd: Path, jobs: list[str]) -> Path:
    workflows = cwd / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    body = "name: CI\non:\n  pull_request:\n  push:\n    branches: [master]\njobs:\n" + "".join(
        jobs
    )
    path = workflows / "ci.yml"
    _ = path.write_text(body, encoding="utf-8")
    return path


def _setup_detector_job() -> str:
    """The retired `detect-py-changes` setup job — NOT gating (absent from ci-green.needs)."""
    return (
        "  setup:\n"
        "    name: detect-py-changes\n"
        "    runs-on: ubuntu-latest\n"
        "    outputs:\n"
        "      py_changed: ${{ steps.detect.outputs.py_changed }}\n"
        "    steps:\n"
        "      - id: detect\n"
        '        run: echo "py_changed=true" >> "$GITHUB_OUTPUT"\n'
    )


def _py_conditioned_matrix_job(*, key: str) -> str:
    """A gating matrix job whose real steps are `py_changed`-conditioned (the skip shape)."""
    return (
        f"  {key}:\n"
        "    needs: setup\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          - check-alpha\n"
        "    steps:\n"
        "      # a note before the conditioned steps\n"
        "      - name: Skip when no .py changes\n"
        "        if: needs.setup.outputs.py_changed != 'true'\n"
        '        run: echo "::notice::skipped"\n'
        "      - name: run the check\n"
        "        if: needs.setup.outputs.py_changed == 'true'\n"
        "        run: just ${{ matrix.target }}\n"
    )


def _clean_gating_job(*, key: str, slug: str) -> str:
    """A gating job that runs its `just <slug>` UNCONDITIONALLY (no py_changed gate)."""
    return (
        f"  {key}:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: run\n"
        f"        run: just {slug}\n"
    )


def _ci_green_job(*, needs: str) -> str:
    return (
        "  ci-green:\n"
        f"    needs: {needs}\n"
        "    if: always()\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: gate\n"
        "        if: ${{ contains(needs.*.result, 'failure') }}\n"
        "        run: exit 1\n"
    )


def test_gating_py_conditioned_job_is_flagged(*, tmp_path: Path) -> None:
    """A gating job (in ci-green.needs) whose steps are py_changed-conditioned → finding; warn → exit 0."""
    jobs = [
        _setup_detector_job(),
        _py_conditioned_matrix_job(key="check-python"),
        _ci_green_job(needs="[check-python]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path)
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    skew = [f for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"]
    assert len(skew) == 1, f"expected one gate-skew finding; got {skew!r}"
    assert skew[0].get("job") == "check-python"
    assert skew[0].get("level") == "warning", f"expected WARNING level; got {skew[0]!r}"


def test_lever_set_flips_finding_to_error_and_exit_4(*, tmp_path: Path) -> None:
    """With the lever set, the same finding emits at ERROR and the check exits 4."""
    jobs = [
        _setup_detector_job(),
        _py_conditioned_matrix_job(key="check-python"),
        _ci_green_job(needs="[check-python]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, env={"LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST": "1"})
    assert (
        result.returncode == 4
    ), f"expected exit 4 with lever set; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    skew = [f for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"]
    assert len(skew) == 1
    assert skew[0].get("job") == "check-python"
    assert skew[0].get("level") == "error", f"expected ERROR level with lever set; got {skew[0]!r}"
    assert skew[0].get("failing") is True


def test_clean_ci_yml_has_no_findings(*, tmp_path: Path) -> None:
    """Gating jobs that run unconditionally (no py_changed gate) → no findings, exit 0."""
    jobs = [
        _clean_gating_job(key="check-python", slug="check-alpha"),
        _clean_gating_job(key="check-metadata", slug="check-beta"),
        _ci_green_job(needs="[check-python, check-metadata]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path)
    assert (
        result.returncode == 0
    ), f"expected exit 0 for a clean ci.yml; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    skew = [f for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"]
    assert skew == [], f"a clean ci.yml must produce no gate-skew findings; got {skew!r}"


def test_release_gate_pr_only_if_is_not_flagged(*, tmp_path: Path) -> None:
    """A gating job conditioned on head_ref/event (PR-only strictness, no py_changed) → NOT flagged.

    This is ADDITIONAL PR strictness, one-directional-safe, never a skip that
    weakens the PR gate below master — the `py_changed` token is the
    discriminator and this `if:` carries none.
    """
    release_gate = (
        "  release-gate-pre-tag:\n"
        "    needs: setup\n"
        "    if: startsWith(github.head_ref, 'release-please--')\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: run\n"
        "        if: github.event_name == 'pull_request'\n"
        "        run: just check-release-gate\n"
    )
    jobs = [
        _setup_detector_job(),
        release_gate,
        _ci_green_job(needs="[release-gate-pre-tag]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, env={"LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST": "1"})
    assert result.returncode == 0, (
        "a PR-only / head_ref `if:` with no py_changed token is additional PR "
        f"strictness, never a gate skip; got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    skew = [f for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"]
    assert skew == [], f"release-gate-pre-tag must not be flagged; got {skew!r}"


def test_non_gating_job_with_py_conditioning_is_not_flagged(*, tmp_path: Path) -> None:
    """A py_changed-conditioned job ABSENT from ci-green.needs (export-telemetry) → NOT flagged.

    The `setup` detector and an `export-telemetry` job are not gates
    (`ci-green.needs` omits them), so even carrying py_changed conditioning
    they cannot weaken the merge gate and are out of scope.
    """
    export_telemetry = (
        "  export-telemetry:\n"
        "    needs: [setup, check-python]\n"
        "    if: needs.setup.outputs.py_changed == 'true'\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: export\n"
        "        run: bash .github/scripts/export-ci-telemetry.sh\n"
    )
    jobs = [
        _setup_detector_job(),
        _clean_gating_job(key="check-python", slug="check-alpha"),
        export_telemetry,
        # ci-green fans in only the clean gating job; setup + export-telemetry
        # are correctly absent, so their py_changed conditioning is out of scope.
        _ci_green_job(needs="[check-python]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, env={"LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST": "1"})
    assert result.returncode == 0, (
        "a py_changed-conditioned NON-gating job must not be flagged; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    skew = [f for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"]
    assert skew == [], f"non-gating py_changed jobs must not be flagged; got {skew!r}"


def test_job_level_if_py_conditioned_is_flagged(*, tmp_path: Path) -> None:
    """A gating job whose JOB-LEVEL `if:` (not a step) references py_changed → finding."""
    job_level = (
        "  check-python:\n"
        "    needs: setup\n"
        "    if: needs.setup.outputs.py_changed == 'true'\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: run\n"
        "        run: just check-alpha\n"
    )
    jobs = [
        _setup_detector_job(),
        job_level,
        _ci_green_job(needs="[check-python]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    skew = {
        f.get("job") for f in findings if f.get("failure_mode") == "ci-gate-py-conditioned-skip"
    }
    assert skew == {"check-python"}, f"a job-level py_changed `if:` must flag the job; got {skew!r}"


def test_missing_ci_yml_yields_no_findings(*, tmp_path: Path) -> None:
    """No `.github/workflows/ci.yml` → no merge gate to check → no findings, exit 0."""
    result = _run_check(cwd=tmp_path, env={"LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST": "1"})
    assert (
        result.returncode == 0
    ), f"expected exit 0 with no ci.yml; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    assert findings == [], f"absent ci.yml must produce no findings; got {findings!r}"


def test_no_ci_green_job_yields_no_findings(*, tmp_path: Path) -> None:
    """A ci.yml with jobs but NO `ci-green` gate → no gating jobs → no findings, exit 0.

    An absent `ci-green` is `ci_matrix_completeness`'s assertion (b) finding,
    not this parity check's to re-report.
    """
    jobs = [
        _setup_detector_job(),
        _py_conditioned_matrix_job(key="check-python"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, env={"LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST": "1"})
    assert (
        result.returncode == 0
    ), f"expected exit 0 with no ci-green job; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    assert findings == [], f"no ci-green gate must produce no findings; got {findings!r}"


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    combined = result.stdout.lower()
    assert "ci-gate-parity" in combined or "usage" in combined
