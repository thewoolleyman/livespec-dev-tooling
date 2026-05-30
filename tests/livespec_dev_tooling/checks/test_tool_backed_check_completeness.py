"""Outside-in test for `livespec_dev_tooling/checks/tool_backed_check_completeness.py`.

Per epic `li-pyright-gate` (work-item `li-pyright-gate-wi3`), the
meta-check asserts every tool-backed check (lint, format, types,
coverage) is a LITERAL member of BOTH the consumer's `just check`
`targets=(...)` array AND a CI workflow's `matrix.target` list.

Failure modes covered:

- Tool-backed slug missing from the justfile targets array →
  exit 4 with a `missing_from_justfile` finding.
- Tool-backed slug missing from every CI matrix → exit 4 with a
  `missing_from_ci` finding.
- Slug missing from BOTH surfaces → exit 4 with both findings.
- Justfile missing entirely → exit 4 + `justfile_not_found`.
- `check:` recipe missing → exit 4 + `check_recipe_not_found`.
- `targets=(...)` array missing / unclosed → exit 4 +
  `targets_array_not_found`.
- `.github/workflows` directory missing → exit 4 +
  `workflows_dir_not_found`.

Acceptance behaviors:

- Every tool-backed slug present on BOTH surfaces → exit 0.
- Comments / blanks / inline trailing comments inside the targets
  array are filtered; non-`check-` targets are ignored.
- `.yaml`-extension workflow files are parsed alongside `.yml`.

Tests inject a synthetic tool-backed slug set via the check's
`--tool-backed-from` flag so they stay hermetic from the fixed
policy default and from sibling-PR landings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "tool_backed_check_completeness.py"


def _run_check(
    *,
    cwd: Path,
    extra_argv: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(_CHECK)]
    if extra_argv is not None:
        argv.extend(extra_argv)
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_tool_backed_json(*, cwd: Path, slugs: list[str]) -> Path:
    path = cwd / "tool-backed.json"
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


def _write_ci_workflow(*, cwd: Path, matrix_targets: list[str], name: str = "ci.yml") -> Path:
    """Write a minimal CI workflow whose `matrix.target` lists `matrix_targets`."""
    workflows = cwd / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    bullets = "\n".join(f"          - {t}" for t in matrix_targets)
    body = (
        "name: CI\n"
        "on: [push]\n"
        "jobs:\n"
        "  check-python:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        f"{bullets}\n"
        "    steps:\n"
        "      - run: just ${{ matrix.target }}\n"
    )
    path = workflows / name
    _ = path.write_text(body, encoding="utf-8")
    return path


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line findings from the check's stderr."""
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def test_all_present_on_both_surfaces_passes(*, tmp_path: Path) -> None:
    """Every tool-backed slug literal on BOTH surfaces → exit 0."""
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 when all present on both surfaces; got {result.returncode}, stderr={result.stderr!r}"


def test_missing_from_justfile_fails(*, tmp_path: Path) -> None:
    """A tool-backed slug absent from the justfile targets array → exit 4 + finding."""
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    # justfile wires only check-lint; check-format missing.
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-lint"]))
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert (
        result.returncode == 4
    ), f"expected exit 4 on missing-from-justfile; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [f for f in findings if f.get("failure_mode") == "missing_from_justfile"]
    assert len(missing) == 1, f"expected one missing_from_justfile finding; got {missing!r}"
    assert missing[0].get("slug") == "check-format"


def test_missing_from_ci_fails(*, tmp_path: Path) -> None:
    """A tool-backed slug absent from every CI matrix → exit 4 + finding."""
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    # CI lists only check-lint; check-format missing.
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=["check-lint"])
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert (
        result.returncode == 4
    ), f"expected exit 4 on missing-from-ci; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [f for f in findings if f.get("failure_mode") == "missing_from_ci"]
    assert len(missing) == 1, f"expected one missing_from_ci finding; got {missing!r}"
    assert missing[0].get("slug") == "check-format"


def test_missing_from_both_surfaces_emits_both_findings(*, tmp_path: Path) -> None:
    """A slug absent from both surfaces → exit 4 with both findings."""
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-lint"]))
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=["check-lint"])
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    modes = {f.get("failure_mode") for f in findings if f.get("slug") == "check-format"}
    assert modes == {
        "missing_from_justfile",
        "missing_from_ci",
    }, f"expected both findings for check-format; got {modes!r}"


def test_missing_justfile_fails(*, tmp_path: Path) -> None:
    """No justfile at cwd → exit 4 + justfile_not_found finding."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "justfile_not_found"]
    assert len(absence) == 1, f"expected one justfile_not_found finding; got {absence!r}"


def test_justfile_without_check_recipe_fails(*, tmp_path: Path) -> None:
    """Justfile present but no `check:` recipe → exit 4 + check_recipe_not_found."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(
        cwd=tmp_path, body="default:\n    @just --list\n\nfmt:\n    ruff format .\n"
    )
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "check_recipe_not_found"]
    assert len(absence) == 1, f"expected one check_recipe_not_found finding; got {absence!r}"


def test_targets_array_missing_fails(*, tmp_path: Path) -> None:
    """`check:` recipe exists but has no `targets=(...)` array → exit 4 + finding."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
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
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1, f"expected one targets_array_not_found finding; got {absence!r}"


def test_unclosed_targets_array_fails(*, tmp_path: Path) -> None:
    """`targets=(...)` array never closed → exit 4 + targets_array_not_found."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
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
            "        check-lint\n"
            "    # never closed (no `)` line before EOF)\n"
        ),
    )
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1


def test_missing_workflows_dir_fails(*, tmp_path: Path) -> None:
    """No `.github/workflows` dir → exit 4 + workflows_dir_not_found."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "workflows_dir_not_found"]
    assert len(absence) == 1, f"expected one workflows_dir_not_found finding; got {absence!r}"


def test_comments_blanks_and_non_check_targets_filtered(*, tmp_path: Path) -> None:
    """Blank lines, `#` comments, inline trailing comments, and non-`check-` targets are filtered."""
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        # leading comment\n"
        "        bootstrap\n"
        "        check-lint  # inline trailing comment\n"
        "\n"
        "        check-format\n"
        "        fmt\n"
        "    )\n"
        '    for t in "${targets[@]}"; do just "$t"; done\n'
    )
    _ = _write_justfile(cwd=tmp_path, body=body)
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with comments/blanks/non-check targets filtered; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_ci_matrix_in_yaml_extension_file_parsed(*, tmp_path: Path) -> None:
    """A `.yaml`-extension workflow's matrix is parsed alongside `.yml` files."""
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    # Provide the tool-backed slug ONLY in a `.yaml`-extension workflow.
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs, name="other.yaml")
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when slug is in a .yaml workflow; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_default_tool_backed_set_is_policy_default(*, tmp_path: Path) -> None:
    """Without `--tool-backed-from`, the fixed policy slug set is enforced."""
    # Wire NONE of the policy slugs and assert all four are reported
    # missing from the justfile (proves the default tuple is loaded).
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-other"]))
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=["check-other"])
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 4
    findings = _parse_findings(stderr=result.stderr)
    missing_justfile = {
        f.get("slug") for f in findings if f.get("failure_mode") == "missing_from_justfile"
    }
    assert missing_justfile == {
        "check-lint",
        "check-format",
        "check-types",
        "check-coverage",
    }, f"expected the four policy slugs reported missing; got {missing_justfile!r}"


def test_malformed_tool_backed_json_treated_as_empty(*, tmp_path: Path) -> None:
    """`--tool-backed-from` JSON without a list-shaped `slugs` field → empty set → exit 0.

    With an empty tool-backed set there is nothing to enforce, so any
    well-formed justfile + CI passes. Exercises the not-a-list fallback
    in `_load_tool_backed_slugs`.
    """
    bad = tmp_path / "tool-backed.json"
    _ = bad.write_text(json.dumps({"slugs": "not-a-list"}), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-anything"]))
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=["check-anything"])
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when tool-backed set is empty; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_recipe_body_stops_at_next_recipe_header(*, tmp_path: Path) -> None:
    """A `check:` recipe followed by another recipe → body extraction stops at the next header.

    Exercises the `break` branch inside `_extract_check_recipe_body`
    where a non-indented `name:` line terminates the body scan.
    """
    slugs = ["check-lint"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        check-lint\n"
        "    )\n"
        '    for t in "${targets[@]}"; do just "$t"; done\n'
        "\n"
        "fmt:\n"
        "    ruff format .\n"
    )
    _ = _write_justfile(cwd=tmp_path, body=body)
    _ = _write_ci_workflow(cwd=tmp_path, matrix_targets=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when other recipes follow `check:`; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_ci_matrix_blank_and_comment_lines_skipped(*, tmp_path: Path) -> None:
    """Blank lines and `#` comments inside a CI `matrix.target` list are skipped.

    Exercises the blank/comment-skip branch inside `_parse_ci_matrix_targets`.
    """
    slugs = ["check-lint", "check-format"]
    _ = _write_tool_backed_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    body = (
        "name: CI\n"
        "on: [push]\n"
        "jobs:\n"
        "  check-python:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          # a comment inside the target list\n"
        "          - check-lint\n"
        "\n"
        "          - check-format\n"
        "    steps:\n"
        "      - run: just ${{ matrix.target }}\n"
    )
    _ = (workflows / "ci.yml").write_text(body, encoding="utf-8")
    result = _run_check(cwd=tmp_path, extra_argv=["--tool-backed-from", "tool-backed.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with comment/blank lines inside CI matrix target list; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    combined = result.stdout.lower()
    assert "tool-backed" in combined or "usage" in combined
