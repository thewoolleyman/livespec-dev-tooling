"""Outside-in test for `livespec_dev_tooling/checks/ci_matrix_completeness.py`.

Per epic `livespec-cf4bcu` (fleet-ci-aggregate-coverage) slice 1, the
drift-guard asserts, from a repo's OWN committed files, that CI runs (a)
and gates (b) the whole canonical `just check` aggregate:

- (a) the CI-covered canonical slug set (per-job matrix targets plus `just
  <canonical-slug>` run-line invocations) is a superset of the justfile
  `check:` aggregate's canonical slugs;
- (b) a `ci-green` job exists and its `needs:` covers every GATING job — a
  job running any `just <target>` command (canonical OR not) or carrying a
  `strategy.matrix.target` list. (b) is deliberately broader than (a)'s
  canonical scope so a dedicated non-canonical gating job (e2e-cli,
  acceptance, check-doctor-static) is still required in `ci-green.needs`
  (`livespec-dev-tooling-o6b`).

The scan ALWAYS runs; the `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST` lever
only flips findings from WARNING (exit 0) to ERROR (exit 4).

Tests inject a synthetic canonical set via `--canonical-from` so they stay
hermetic from the live `checks/` package and from sibling-PR landings.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "ci_matrix_completeness.py"

# Env vars that change `ci_matrix_completeness`'s VERDICT rather than its behavior.
# Cleared from every subprocess unless the test names one, so a test's expected exit
# code cannot depend on the host that runs it.
_AMBIENT_SEVERITY_VARS = ("LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST",)


def _run_check(
    *,
    cwd: Path,
    extra_argv: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(_CHECK)]
    if extra_argv is not None:
        argv.extend(extra_argv)
    # ⛔ THE AMBIENT SEVERITY VARS ARE CLEARED UNLESS A TEST SETS THEM EXPLICITLY.
    # `env=None` previously meant `run_env=None`, i.e. INHERIT the whole ambient
    # environment — and this repo's CI sets
    # `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST: "true"` for every `matrix.target` in
    # the metadata job group. So the check under test flipped from warn (exit 0) to
    # FAIL (exit 4) purely because of where it ran, and the 17 tests here that assert
    # `returncode == 0` failed in CI while passing locally.
    #
    # It was LATENT, not new: that var has been set for the whole job group for some
    # time, and `ci.yml` still asserts it is "Harmless for the other metadata legs —
    # they do not read this var". That became FALSE once
    # `check-check-coverage-incremental` began selecting this file, which happens
    # whenever a change touches `ci_matrix_completeness.py`. A leg that SPAWNS the
    # check reads the var transitively.
    #
    # Severity must be a property of the TEST, never of the host. The pass-through
    # keeps everything the interpreter needs (PATH, HOME, venv vars) and removes only
    # the flags that change the check's verdict.
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


def _write_canonical_json(*, cwd: Path, slugs: list[str], name: str = "canonical.json") -> Path:
    path = cwd / name
    _ = path.write_text(json.dumps({"slugs": slugs}), encoding="utf-8")
    return path


def _justfile_with_targets(*, targets: list[str]) -> str:
    """Render a minimal `justfile` whose `check:` recipe wires `targets`."""
    indented = "\n".join(f"        {t}" for t in targets)
    return (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        f"{indented}\n"
        "    )\n"
        '    for t in "${targets[@]}"; do\n'
        '        just "$t" || exit 1\n'
        "    done\n"
    )


def _write_justfile(*, cwd: Path, body: str) -> Path:
    path = cwd / "justfile"
    _ = path.write_text(body, encoding="utf-8")
    return path


def _matrix_job(*, key: str, targets: list[str], needs: str | None = None) -> str:
    """A per-target matrix job running `just ${{ matrix.target }}`."""
    bullets = "\n".join(f"          - {t}" for t in targets)
    lines = [f"  {key}:"]
    if needs is not None:
        lines.append(f"    needs: {needs}")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    strategy:")
    lines.append("      fail-fast: false")
    lines.append("      matrix:")
    lines.append("        target:")
    lines.append(bullets)
    lines.append("    steps:")
    lines.append("      - run: just ${{ matrix.target }}")
    return "\n".join(lines) + "\n"


def _dedicated_job(*, key: str, slug: str, needs: str | None = None) -> str:
    """A single job running one `just <slug>`."""
    lines = [f"  {key}:"]
    if needs is not None:
        lines.append(f"    needs: {needs}")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append(f"      - run: just {slug}")
    return "\n".join(lines) + "\n"


def _non_just_job(*, key: str, run_cmd: str, needs: str | None = None) -> str:
    """A job running a NON-`just` command (telemetry export, auto-merge, setup).

    Such a job runs no gating `just <target>` and carries no `matrix.target`,
    so it is not gating and `ci-green.needs` need not list it.
    """
    lines = [f"  {key}:"]
    if needs is not None:
        lines.append(f"    needs: {needs}")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append(f"      - run: {run_cmd}")
    return "\n".join(lines) + "\n"


def _ci_green_job(*, needs: str) -> str:
    """The all-green gate job whose `needs:` fans in the check-bearing jobs."""
    lines = [
        "  ci-green:",
        f"    needs: {needs}",
        "    if: always()",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - name: gate",
        "        if: ${{ contains(needs.*.result, 'failure') }}",
        "        run: exit 1",
    ]
    return "\n".join(lines) + "\n"


def _write_ci_yml(*, cwd: Path, jobs: list[str], trailer: str = "") -> Path:
    workflows = cwd / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    body = "name: CI\non: [push]\njobs:\n" + "".join(jobs) + trailer
    path = workflows / "ci.yml"
    _ = path.write_text(body, encoding="utf-8")
    return path


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line findings from the check's stderr."""
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def _fully_wired_jobs() -> list[str]:
    """A matrix job (alpha, beta) + a dedicated gamma job + a complete ci-green."""
    return [
        _matrix_job(key="check", targets=["check-alpha", "check-beta"], needs="setup"),
        _dedicated_job(key="check-gamma-job", slug="check-gamma", needs="setup"),
        _ci_green_job(needs="[check, check-gamma-job]"),
    ]


def test_fully_wired_repo_passes(*, tmp_path: Path) -> None:
    """CI matrix and dedicated jobs cover the aggregate; ci-green.needs complete -> exit 0."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    _ = _write_ci_yml(cwd=tmp_path, jobs=_fully_wired_jobs())
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 for a fully-wired repo; got {result.returncode}, stderr={result.stderr!r}"


def test_ci_matrix_omits_aggregate_slug_reports_finding_a(*, tmp_path: Path) -> None:
    """A canonical aggregate slug run nowhere in CI → finding (a); warn-default → exit 0."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    # CI runs only alpha + beta (matrix); gamma is nowhere. ci-green.needs
    # covers the sole check-bearing job so (b) is not implicated.
    jobs = [
        _matrix_job(key="check", targets=["check-alpha", "check-beta"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [f for f in findings if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"]
    assert len(missing) == 1, f"expected one missing-aggregate-slug finding; got {missing!r}"
    assert missing[0].get("slug") == "check-gamma"
    assert missing[0].get("level") == "warning", f"expected WARNING level; got {missing[0]!r}"


def test_world_gate_aggregate_slug_absent_from_ci_is_not_flagged(*, tmp_path: Path) -> None:
    """A world-gate canonical slug in the aggregate but nowhere in CI is NOT a finding (a).

    World-gate checks (`check-master-ci-green`, `check-branch-protection-alignment`)
    verify master/world state — not the PR change — enforce at pre-push under the
    maintainer's admin-scoped `gh` token, and are deliberately excluded from the
    CI-mirror requirement (`canonical_checks.world_gate_check_slugs`; see
    `livespec/.ai/ci-gate-discipline.md` §"verify the CHANGE vs verify the WORLD").
    They stay canonical and stay wired in the `just check` aggregate — only
    assertion (a)'s "must run in CI" requirement drops them.

    Fixture: the aggregate wires `check-alpha`, `check-beta`, and the real
    world-gate `check-master-ci-green`; CI runs only `check-alpha`. The regular
    `check-beta` absent from CI is STILL flagged (proving the exclusion is
    world-gate-specific, not a blanket suppression); the world-gate absent from
    CI is NOT flagged.
    """
    slugs = ["check-alpha", "check-beta", "check-master-ci-green"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing_slugs = {
        f.get("slug")
        for f in findings
        if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"
    }
    assert "check-master-ci-green" not in missing_slugs, (
        "a world-gate slug absent from CI must NOT be flagged as a missing aggregate "
        f"slug (it is pre-push-only); got missing={missing_slugs!r}"
    )
    assert "check-beta" in missing_slugs, (
        "a regular canonical slug absent from CI must STILL be flagged — the exclusion "
        f"is world-gate-specific, not blanket; got missing={missing_slugs!r}"
    )


def test_ci_green_needs_incomplete_reports_finding_b(*, tmp_path: Path) -> None:
    """Full matrix coverage but ci-green.needs omits a check-bearing job → finding (b)."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    # gamma IS covered (dedicated job) so (a) is clean; ci-green.needs omits
    # that check-bearing dedicated job.
    jobs = [
        _matrix_job(key="check", targets=["check-alpha", "check-beta"], needs="setup"),
        _dedicated_job(key="check-gamma-job", slug="check-gamma", needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    incomplete = [f for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"]
    assert (
        len(incomplete) == 1
    ), f"expected one ci-green-needs-incomplete finding; got {incomplete!r}"
    assert incomplete[0].get("job") == "check-gamma-job"
    # (a) must be clean: gamma is covered by the dedicated job.
    missing = [f for f in findings if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"]
    assert missing == [], f"expected no (a) findings; got {missing!r}"


def test_ci_green_job_missing_reports_finding(*, tmp_path: Path) -> None:
    """No `ci-green` job at all → ci-green-job-missing finding naming the check-bearing jobs."""
    slugs = ["check-alpha", "check-beta"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [_matrix_job(key="check", targets=["check-alpha", "check-beta"], needs="setup")]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absent = [f for f in findings if f.get("failure_mode") == "ci-green-job-missing"]
    assert len(absent) == 1, f"expected one ci-green-job-missing finding; got {absent!r}"
    assert absent[0].get("check_bearing_jobs") == ["check"]


def test_lever_set_flips_findings_to_error_and_exit_4(*, tmp_path: Path) -> None:
    """With the lever set, the same findings emit at ERROR and exit 4."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha", "check-beta"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(
        cwd=tmp_path,
        extra_argv=["--canonical-from", "canonical.json"],
        env={"LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST": "1"},
    )
    assert (
        result.returncode == 4
    ), f"expected exit 4 with lever set; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [f for f in findings if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"]
    assert len(missing) == 1
    assert (
        missing[0].get("level") == "error"
    ), f"expected ERROR level with lever set; got {missing[0]!r}"
    assert missing[0].get("failing") is True


def test_non_canonical_slug_ignored_by_a_but_its_job_gating_for_b(*, tmp_path: Path) -> None:
    """A non-canonical `just <slug>` counts for neither (a)'s coverage — yet its job IS gating for (b).

    Post-o6b: assertion (a) stays canonical-scoped (a non-canonical
    `check-lint` neither covers the aggregate nor surfaces as missing), while
    assertion (b) broadens — the dedicated `lint` job runs a `just <target>`,
    so it is gating and MUST appear in `ci-green.needs`. Before o6b this same
    scenario tripped nothing, which was the bug.
    """
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    # `check-lint` is NOT canonical here. The matrix covers the whole aggregate
    # (check-alpha), so (a) is clean; ci-green.needs omits the gating `lint`
    # job, so (b) trips. Both jobs omit `needs:` (a standalone-job shape).
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"]),
        _dedicated_job(key="lint", slug="check-lint"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    # (a): a non-canonical slug never surfaces as a missing-aggregate finding.
    missing = [f for f in findings if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"]
    assert missing == [], f"expected no (a) findings; got {missing!r}"
    # (b): the non-canonical gating `lint` job must be required in ci-green.needs.
    incomplete = [f for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"]
    assert {f.get("job") for f in incomplete} == {"lint"}, f"got {incomplete!r}"


def test_non_canonical_gating_jobs_required_in_ci_green_needs(*, tmp_path: Path) -> None:
    """Real fleet non-canonical gating jobs (e2e-cli, check-doctor-static) must be in ci-green.needs (o6b).

    They run `just e2e-cli` / `just check-doctor-static` — non-canonical
    targets — so before o6b they were not check-bearing and could be omitted
    from `ci-green.needs`, letting a RED e2e-cli/doctor-static merge under a
    require-only-`ci-green` protection. Each omitted gating job now yields a
    (b) finding; `check-doctor-static`/`e2e-cli` are NOT canonical here (the
    injected canonical set is only `check-alpha`), so this proves (b) is
    broader than (a)'s canonical scope.
    """
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _dedicated_job(key="e2e-cli", slug="e2e-cli", needs="setup"),
        _dedicated_job(key="check-doctor-static", slug="check-doctor-static", needs="setup"),
        # ci-green fans in only the matrix job, omitting BOTH gating jobs.
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 under warn-default; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    incomplete = {
        f.get("job") for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"
    }
    assert incomplete == {"e2e-cli", "check-doctor-static"}, f"got {incomplete!r}"


def test_telemetry_and_auto_merge_jobs_auto_excluded_from_b(*, tmp_path: Path) -> None:
    """export-telemetry / enable-auto-merge run no `just` target → not gating → not required (o6b).

    They are excluded with NO hardcoded denylist: neither runs a `just
    <target>` command nor carries a `matrix.target`, so omitting them from
    `ci-green.needs` yields no (b) finding.
    """
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _non_just_job(
            key="export-telemetry",
            run_cmd="bash .github/scripts/export-ci-telemetry.sh",
            needs="check",
        ),
        _non_just_job(key="enable-auto-merge", run_cmd="gh pr merge --auto --rebase"),
        # ci-green fans in only the gating `check` job; the two non-gating jobs
        # are correctly absent and must NOT trip (b).
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0; telemetry/auto-merge are not gating; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    incomplete = [f for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"]
    assert incomplete == [], f"telemetry/auto-merge must auto-exclude from (b); got {incomplete!r}"


def test_comment_line_in_non_matrix_job_skipped_by_gating_scan(*, tmp_path: Path) -> None:
    """A comment line in a non-matrix job's body is skipped; its `just <target>` still makes it gating.

    A matrix job short-circuits the gating scan on its `matrix.target` list, so
    the comment-skip branch of the broadened `just <target>` scan is reached
    only via a dedicated (non-matrix) job — this exercises that branch.
    """
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    gate_with_comment = (
        "  e2e-cli:\n"
        "    needs: setup\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      # a note before the gating invocation\n"
        "      - run: just e2e-cli\n"
    )
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        gate_with_comment,
        _ci_green_job(needs="[check]"),  # omits the gating e2e-cli
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    incomplete = {
        f.get("job") for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"
    }
    assert incomplete == {"e2e-cli"}, f"got {incomplete!r}"


def test_scalar_and_block_needs_shapes_parsed(*, tmp_path: Path) -> None:
    """ci-green with a block-list `needs:` covering scalar-`needs:` jobs → exit 0."""
    slugs = ["check-alpha", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    ci_green_block = (
        "  ci-green:\n"
        "    needs:\n"
        "      - check\n"
        "      - check-gamma-job\n"
        "    if: always()\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: exit 0\n"
    )
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _dedicated_job(key="check-gamma-job", slug="check-gamma", needs="setup"),
        ci_green_block,
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 with block-list needs; got {result.returncode}, stderr={result.stderr!r}"


def test_empty_flow_needs_yields_incomplete_when_check_bearing_exists(*, tmp_path: Path) -> None:
    """`needs: []` covers nothing, so a check-bearing job trips (b)."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _ci_green_job(needs="[]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    incomplete = [f for f in findings if f.get("failure_mode") == "ci-green-needs-incomplete"]
    assert {f.get("job") for f in incomplete} == {"check"}, f"got {incomplete!r}"


def test_comments_and_blanks_in_ci_and_targets_filtered(*, tmp_path: Path) -> None:
    """Comment/blank lines in the matrix target list, run body, and targets array are skipped."""
    slugs = ["check-alpha", "check-beta"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    justfile_body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        # leading comment\n"
        "        bootstrap\n"
        "        check-alpha  # inline trailing comment\n"
        "\n"
        "        check-beta\n"
        "    )\n"
        '    for t in "${targets[@]}"; do just "$t"; done\n'
    )
    _ = _write_justfile(cwd=tmp_path, body=justfile_body)
    matrix_with_comment = (
        "  check:\n"
        "    needs: setup\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          # a comment inside the target list\n"
        "          - check-alpha\n"
        "\n"
        "          - check-beta\n"
        "    steps:\n"
        "      # a comment line in the run body\n"
        "      - run: just ${{ matrix.target }}\n"
    )
    jobs = [matrix_with_comment, _ci_green_job(needs="[check]")]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with comments/blanks filtered; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_top_level_key_after_jobs_still_parses_jobs(*, tmp_path: Path) -> None:
    """A top-level key after the jobs table ends the section without losing the last job."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    _ = _write_ci_yml(cwd=tmp_path, jobs=_fully_wired_jobs(), trailer="concurrency: ci-group\n")
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with a trailing top-level key; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_missing_justfile_reports_absence(*, tmp_path: Path) -> None:
    """No justfile at cwd → justfile_not_found finding."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha"])
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "justfile_not_found"]
    assert len(absence) == 1, f"expected one justfile_not_found finding; got {absence!r}"


def test_missing_check_recipe_reports_absence(*, tmp_path: Path) -> None:
    """Justfile without a `check:` recipe → check_recipe_not_found finding."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha"])
    _ = _write_justfile(
        cwd=tmp_path, body="default:\n    @just --list\n\nfmt:\n    ruff format .\n"
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "check_recipe_not_found"]
    assert len(absence) == 1, f"expected one check_recipe_not_found finding; got {absence!r}"


def test_targets_array_missing_reports_absence(*, tmp_path: Path) -> None:
    """`check:` recipe without a `targets=(...)` array → targets_array_not_found finding."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha"])
    _ = _write_justfile(
        cwd=tmp_path,
        body=(
            "default:\n"
            "    @just --list\n"
            "\n"
            "check:\n"
            "    #!/usr/bin/env bash\n"
            '    echo "no targets array here"\n'
        ),
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1, f"expected one targets_array_not_found finding; got {absence!r}"


def test_unclosed_targets_array_reports_absence(*, tmp_path: Path) -> None:
    """`targets=(...)` never closed → targets_array_not_found finding."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha"])
    _ = _write_justfile(
        cwd=tmp_path,
        body=(
            "default:\n"
            "    @just --list\n"
            "\n"
            "check:\n"
            "    #!/usr/bin/env bash\n"
            "    set -uo pipefail\n"
            "    targets=(\n"
            "        check-alpha\n"
            "    # never closed (no `)` line before EOF)\n"
        ),
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1


def test_recipe_body_stops_at_next_recipe_header(*, tmp_path: Path) -> None:
    """A recipe after `check:` terminates the body scan (the break branch)."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        check-alpha\n"
        "    )\n"
        '    for t in "${targets[@]}"; do just "$t"; done\n'
        "\n"
        "fmt:\n"
        "    ruff format .\n"
    )
    _ = _write_justfile(cwd=tmp_path, body=body)
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when another recipe follows `check:`; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_missing_ci_yml_reports_absence(*, tmp_path: Path) -> None:
    """A wired justfile but no `.github/workflows/ci.yml` → ci_yml_not_found finding."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "ci_yml_not_found"]
    assert len(absence) == 1, f"expected one ci_yml_not_found finding; got {absence!r}"


def test_no_jobs_header_yields_ci_green_missing(*, tmp_path: Path) -> None:
    """A ci.yml with no `jobs:` table → no jobs → ci-green-job-missing (empty canonical isolates it)."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=[])
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-alpha"]))
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    _ = (workflows / "ci.yml").write_text("name: CI\non: [push]\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absent = [f for f in findings if f.get("failure_mode") == "ci-green-job-missing"]
    assert len(absent) == 1, f"expected ci-green-job-missing; got {findings!r}"
    assert absent[0].get("check_bearing_jobs") == []


def test_jobs_header_with_no_child_jobs_yields_ci_green_missing(*, tmp_path: Path) -> None:
    """A `jobs:` table whose only content is a comment → no jobs parsed."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=[])
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-alpha"]))
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    _ = (workflows / "ci.yml").write_text(
        "name: CI\non: [push]\njobs:\n  # no jobs yet\n", encoding="utf-8"
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absent = [f for f in findings if f.get("failure_mode") == "ci-green-job-missing"]
    assert len(absent) == 1, f"expected ci-green-job-missing; got {findings!r}"


def test_jobs_section_without_valid_job_header_parses_no_jobs(*, tmp_path: Path) -> None:
    """A `jobs:` table whose lines are a comment + a non-`key:` line → zero jobs parsed.

    Exercises the loop's `current_name is None` paths in `_parse_ci_jobs`: a
    line before any job header (the leading comment) and a body with no header
    at all (so the final append is skipped).
    """
    _ = _write_canonical_json(cwd=tmp_path, slugs=[])
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-alpha"]))
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    _ = (workflows / "ci.yml").write_text(
        "name: CI\non: [push]\njobs:\n  # a note\n  scalar-without-colon value\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    absent = [f for f in findings if f.get("failure_mode") == "ci-green-job-missing"]
    assert len(absent) == 1, f"expected ci-green-job-missing; got {findings!r}"
    assert absent[0].get("check_bearing_jobs") == []


def test_default_canonical_source_is_live_package(*, tmp_path: Path) -> None:
    """Without `--canonical-from`, the live canonical set is used (this module's own slug)."""
    # The justfile wires exactly this module's own canonical slug; the live
    # canonical set contains it (this module exists), so it is the sole
    # `required` slug. CI runs it nowhere → one (a) finding for it.
    own_slug = "check-ci-matrix-completeness"
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=[own_slug]))
    jobs = [
        _matrix_job(key="check", targets=["check-other"], needs="setup"),
        _ci_green_job(needs="[setup]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0
    findings = _parse_findings(stderr=result.stderr)
    missing = {
        f.get("slug")
        for f in findings
        if f.get("failure_mode") == "ci-matrix-missing-aggregate-slug"
    }
    assert own_slug in missing, (
        f"expected {own_slug} in missing-aggregate-slug findings under live canonical; "
        f"got {missing!r}"
    )


def test_malformed_canonical_json_treated_as_empty(*, tmp_path: Path) -> None:
    """`--canonical-from` JSON whose `slugs` is not a list → empty canonical → no (a) findings."""
    bad = tmp_path / "canonical.json"
    _ = bad.write_text(json.dumps({"slugs": "not-a-list"}), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-anything"]))
    jobs = [
        _matrix_job(key="check", targets=["check-anything"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when canonical set is empty; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_non_dict_canonical_json_treated_as_empty(*, tmp_path: Path) -> None:
    """`--canonical-from` JSON that is not an object at all → empty canonical → exit 0."""
    bad = tmp_path / "canonical.json"
    _ = bad.write_text(json.dumps(["check-alpha", "check-beta"]), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-alpha"]))
    jobs = [
        _matrix_job(key="check", targets=["check-alpha"], needs="setup"),
        _ci_green_job(needs="[check]"),
    ]
    _ = _write_ci_yml(cwd=tmp_path, jobs=jobs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when canonical json is a non-dict; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    combined = result.stdout.lower()
    assert "ci-matrix-completeness" in combined or "usage" in combined
