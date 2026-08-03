"""Outside-in test for `livespec_dev_tooling/checks/aggregate_completeness.py`.

Per epic `li-univck` Phase 1.3 (work-item `li-aggchk`), the check
parses a consumer's `justfile` `check:` recipe, extracts the
`targets=(...)` array, and compares to the canonical-check slug
tuple emitted by `livespec_dev_tooling.canonical_checks`. The
canonical subset MUST appear in full and in alphabetical order;
extras (repo-private checks) are allowed but only AFTER the
canonical block.

Failure modes covered:

- Missing canonical slug → exit 4 with structured finding per
  missing slug.
- Out-of-order canonical slugs (set match, ordering differs) →
  exit 4 with diff between canonical and observed order.
- Extras BEFORE / interleaved with the canonical block → exit 4
  (because the canonical-subset ordering is broken).
- Justfile missing entirely → exit 4 with graceful-absence finding.
- `check:` recipe missing entirely → exit 4 with graceful-absence
  finding.

Acceptance behaviors:

- Full match (canonical = wired, alphabetical) → exit 0.
- Repo-private extras AFTER the canonical block → exit 0.

The check is self-bootstrapping: because the check module itself
lives under `livespec_dev_tooling/checks/`, its own slug
(`check-aggregate-completeness`) appears in the canonical set
discovered by `canonical_checks`. Tests therefore inject a
synthetic canonical-set list via the check's `--canonical-from`
flag — this keeps tests hermetic from changes to the live
checks/ package and decouples them from sibling-PR landings.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "aggregate_completeness.py"
_CHECK_SCRIPT = _REPO_ROOT / "scripts" / "just" / "check.sh"


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


def _write_justfile(*, cwd: Path, body: str) -> Path:
    path = cwd / "justfile"
    _ = path.write_text(body, encoding="utf-8")
    return path


def _write_canonical_json(*, cwd: Path, slugs: list[str]) -> Path:
    path = cwd / "canonical.json"
    _ = path.write_text(json.dumps({"slugs": slugs}), encoding="utf-8")
    return path


def _write_target_inventory(*, cwd: Path, targets: list[str]) -> Path:
    path = cwd / "check-targets.txt"
    _ = path.write_text("\n".join(targets) + "\n", encoding="utf-8")
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


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line findings from the check's stderr.

    Every test that exercises a failure path produces structlog-rendered
    lines (`{...}\\n`) on stderr — no other content shapes are emitted —
    so this helper restricts to bracket-leading lines and JSON-parses
    them straight into dict findings.
    """
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def _legacy_core_v1_17_1_extract_check_slugs(*, justfile_text: str) -> tuple[str, ...] | None:
    """Freeze livespec CORE's legacy justfile reader at its v1.17.1 tooling pin."""
    check_recipe = re.compile(r"^check\s*:\s*$")
    targets_opener = re.compile(r"^\s*targets\s*=\s*\(\s*$")
    targets_closer = re.compile(r"^\s*\)\s*(?:#.*)?$")
    target_slug = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_-]*)\s*(?:#.*)?$")
    in_check_recipe = False
    in_targets_array = False
    collected: list[str] = []
    for line in justfile_text.splitlines():
        if check_recipe.match(line):
            in_check_recipe = True
            continue
        if not in_check_recipe:
            continue
        if not in_targets_array:
            if targets_opener.match(line):
                in_targets_array = True
            continue
        if targets_closer.match(line):
            return tuple(collected)
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        slug_match = target_slug.match(line)
        if slug_match is not None:
            collected.append(slug_match.group(1))
    return tuple(collected) if in_targets_array else None


def _normalized_real_target_inventory() -> tuple[str, ...]:
    """Return the production inventory using the check script's normalization rule."""
    targets: list[str] = []
    for raw in (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8").splitlines():
        token = raw.split("#", 1)[0].strip()
        if token.startswith("check-"):
            targets.append(token)
    return tuple(targets)


def test_real_check_recipe_is_legacy_readable_exact_inventory_mirror() -> None:
    """CORE's v1.17.1 reader sees the exact authoritative 65-target inventory."""
    justfile_text = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")

    wired = _legacy_core_v1_17_1_extract_check_slugs(justfile_text=justfile_text)

    assert wired == _normalized_real_target_inventory()
    assert wired is not None and len(wired) == 65
    canonical = unsafe_perform_io(canonical_check_slugs().unwrap())
    assert not set(canonical).difference(wired)
    assert _legacy_core_v1_17_1_extract_check_slugs(justfile_text="default:\n    true\n") is None
    assert _legacy_core_v1_17_1_extract_check_slugs(
        justfile_text=(
            "check:\n    targets=(\n        # tolerated\n\n        ! invalid\n        check-alpha\n"
        )
    ) == ("check-alpha",)


def test_check_script_rejects_mirror_drift_before_dispatch(*, tmp_path: Path) -> None:
    """A stale literal mirror fails closed before sync or aggregate dispatch."""
    script = tmp_path / "scripts" / "just" / "check.sh"
    script.parent.mkdir(parents=True)
    _ = shutil.copy2(_CHECK_SCRIPT, script)
    _ = (tmp_path / "check-targets.txt").write_text("check-alpha\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_marker = tmp_path / "uv-called"
    fake_uv = bin_dir / "uv"
    _ = fake_uv.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nprintf called > "${UV_MARKER}"\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ["bash", str(script), "check-beta"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "UV_MARKER": str(uv_marker),
        },
    )

    assert result.returncode == 1
    assert "literal check target mirror drift" in result.stderr
    assert not uv_marker.exists(), "mirror drift must fail before uv sync or dispatch"


def test_full_match_passes(*, tmp_path: Path) -> None:
    """Canonical = wired, in alphabetical order → exit 0."""
    slugs = ["check-alpha", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=slugs))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 on full match; got {result.returncode}, stderr={result.stderr!r}"


def test_target_inventory_supplies_check_aggregate_passes(*, tmp_path: Path) -> None:
    """`check-targets.txt` is the aggregate inventory when present."""
    slugs = ["check-alpha", "check-beta"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(cwd=tmp_path, body="check:\n    scripts/just/check.sh\n")
    _ = _write_target_inventory(
        cwd=tmp_path,
        targets=["# canonical", "bootstrap", "check-alpha  # inline", "", "check-beta"],
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when check-targets.txt supplies the canonical block; "
        f"stderr={result.stderr!r}"
    )


def test_missing_canonical_slug_fails(*, tmp_path: Path) -> None:
    """A canonical slug absent from the consumer's targets → exit 4 + finding."""
    canonical = ["check-alpha", "check-beta", "check-gamma"]
    wired = ["check-alpha", "check-gamma"]  # `check-beta` missing.
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 4
    ), f"expected exit 4 on missing slug; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing_findings = [
        f
        for f in findings
        if f.get("status") == "fail" and f.get("failure_mode") == "missing_canonical_slug"
    ]
    assert (
        len(missing_findings) == 1
    ), f"expected exactly one missing-slug finding; got {missing_findings!r}"
    assert missing_findings[0].get("slug") == "check-beta"


def test_out_of_order_canonical_slugs_fails(*, tmp_path: Path) -> None:
    """Canonical set matches but ordering differs → exit 4 + diff finding."""
    canonical = ["check-alpha", "check-beta", "check-gamma"]
    wired = ["check-beta", "check-alpha", "check-gamma"]  # set match, wrong order.
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert (
        result.returncode == 4
    ), f"expected exit 4 on out-of-order slugs; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    order_findings = [
        f
        for f in findings
        if f.get("status") == "fail" and f.get("failure_mode") == "out_of_order_canonical_slugs"
    ]
    assert (
        len(order_findings) == 1
    ), f"expected exactly one out-of-order finding; got {order_findings!r}"
    assert order_findings[0].get("canonical_order") == canonical
    assert order_findings[0].get("observed_order") == wired


def test_repo_private_extras_after_canonical_block_passes(*, tmp_path: Path) -> None:
    """Repo-private extras AFTER the canonical block → exit 0 (extras allowed at end)."""
    canonical = ["check-alpha", "check-beta", "check-gamma"]
    wired = [*canonical, "check-foo-private", "check-zoo-private"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with extras after canonical block; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_extras_before_canonical_block_fails(*, tmp_path: Path) -> None:
    """Extras placed BEFORE the canonical set → exit 4 (canonical subset order broken)."""
    canonical = ["check-alpha", "check-beta", "check-gamma"]
    wired = ["check-foo-private", *canonical]  # extra slug at front.
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 4, (
        f"expected exit 4 with extras before canonical block; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    order_findings = [
        f
        for f in findings
        if f.get("status") == "fail" and f.get("failure_mode") == "out_of_order_canonical_slugs"
    ]
    assert len(order_findings) == 1, (
        f"expected one out-of-order finding when extras precede canonical block; "
        f"got {order_findings!r}"
    )


def test_extras_interleaved_with_canonical_block_fails(*, tmp_path: Path) -> None:
    """Extras interleaved with canonical set → exit 4 (canonical-subset order broken)."""
    canonical = ["check-alpha", "check-beta", "check-gamma"]
    wired = ["check-alpha", "check-foo-private", "check-beta", "check-gamma"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 4, (
        f"expected exit 4 with extras interleaved; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_missing_justfile_fails_gracefully(*, tmp_path: Path) -> None:
    """No justfile at cwd → exit 4 with structured graceful-absence finding."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 4, (
        f"expected exit 4 when justfile missing; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "justfile_not_found"]
    assert len(absence) == 1, f"expected one justfile_not_found finding; got {absence!r}"


def test_justfile_without_check_recipe_fails(*, tmp_path: Path) -> None:
    """Justfile present but no `check:` recipe → exit 4 with structured finding."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
    _ = _write_justfile(
        cwd=tmp_path,
        body="default:\n    @just --list\n\nfmt:\n    ruff format .\n",
    )
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 4, (
        f"expected exit 4 when check recipe missing; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "check_recipe_not_found"]
    assert len(absence) == 1, f"expected one check_recipe_not_found finding; got {absence!r}"


def test_targets_array_missing_fails(*, tmp_path: Path) -> None:
    """`check:` recipe exists but has no `targets=(...)` array → exit 4 + finding."""
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=slugs)
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
    assert result.returncode == 4, (
        f"expected exit 4 when targets array missing; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1, f"expected one targets_array_not_found finding; got {absence!r}"


def test_comments_and_blank_lines_filtered_out(*, tmp_path: Path) -> None:
    """Blank lines + `#` comments inside `targets=(...)` are skipped during slug extraction."""
    canonical = ["check-alpha", "check-beta"]
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        # leading comment\n"
        "        check-alpha\n"
        "\n"
        "        # interstitial comment\n"
        "        check-beta\n"
        "    )\n"
        '    for t in "${targets[@]}"; do\n'
        '        just "$t" || exit 1\n'
        "    done\n"
    )
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=body)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 with comments and blanks filtered; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_non_check_prefixed_targets_filtered(*, tmp_path: Path) -> None:
    """Targets not starting with `check-` are ignored (e.g. `bootstrap`, `fmt`)."""
    canonical = ["check-alpha", "check-beta"]
    wired = ["bootstrap", "check-alpha", "check-beta", "fmt"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=wired))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    # `bootstrap` and `fmt` are filtered before the canonical-subset
    # check; the remaining `check-*` targets are `[check-alpha,
    # check-beta]` in canonical order, so the check passes.
    assert result.returncode == 0, (
        f"expected exit 0 when non-`check-` targets present; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_default_canonical_source_is_live_package(*, tmp_path: Path) -> None:
    """Without `--canonical-from`, the check loads the live canonical set."""
    # We don't pin the live canonical set's exact membership (it
    # changes as new checks land), but we can verify default-mode
    # operation by deliberately writing a justfile that omits a
    # known-canonical slug and asserting the check fails. The
    # `check-aggregate-completeness` slug itself is guaranteed to
    # appear in the live set because this module exists.
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=[]))
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 4, (
        f"expected exit 4 when live canonical set is non-empty but justfile wires nothing; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    missing_slugs = {
        f.get("slug") for f in findings if f.get("failure_mode") == "missing_canonical_slug"
    }
    assert "check-aggregate-completeness" in missing_slugs, (
        f"expected check-aggregate-completeness in missing-slug findings under default canonical; "
        f"got {missing_slugs!r}"
    )


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout (per contracts.md section "CLI surface")."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    combined = result.stdout.lower()
    assert "aggregate-completeness" in combined or "usage" in combined


def test_malformed_canonical_json_treated_as_empty(*, tmp_path: Path) -> None:
    """`--canonical-from` pointing to JSON without a list-shaped `slugs` field → empty canonical set.

    With an empty canonical set, any non-empty `check:` aggregate is
    trivially valid and the check exits 0. The branch exercises the
    `slug_field` not-a-list fallback in `_load_canonical`.
    """
    bad_path = tmp_path / "canonical.json"
    _ = bad_path.write_text(json.dumps({"slugs": "not-a-list"}), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_targets(targets=["check-anything"]))
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when canonical.json shape is invalid (empty canonical set); "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_recipe_body_stops_at_next_recipe_header(*, tmp_path: Path) -> None:
    """A `check:` recipe followed by another recipe → body extraction stops at the next header.

    Exercises the `break` branch inside `_extract_check_recipe_body`
    where a non-indented `name:` line terminates the body scan.
    """
    canonical = ["check-alpha"]
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
        "other-recipe:\n"
        "    echo something\n"
        "\n"
        "fmt:\n"
        "    ruff format .\n"
    )
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=body)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when other recipes follow `check:`; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_unclosed_targets_array_fails(*, tmp_path: Path) -> None:
    """`targets=(...)` array missing closing `)` → exit 4 + targets_array_not_found finding.

    Exercises the loop-fell-off-without-closing branch in
    `_extract_targets_array_lines`.
    """
    canonical = ["check-alpha"]
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        check-alpha\n"
        "    # never closed (no `)` line before EOF / next recipe)\n"
    )
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=body)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 4, (
        f"expected exit 4 when targets array is never closed; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "targets_array_not_found"]
    assert len(absence) == 1


def test_inline_trailing_comment_after_slug_stripped(*, tmp_path: Path) -> None:
    """A `<slug>  # trailing comment` line → trailing comment is stripped, slug retained.

    Exercises the `line.split("#", 1)[0].strip()` path in
    `_filter_to_check_slugs` where the line has a real slug followed
    by an inline `#` comment.
    """
    canonical = ["check-alpha", "check-beta"]
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        "        check-alpha  # in-line comment after a real slug\n"
        "        check-beta\n"
        "    )\n"
        '    for t in "${targets[@]}"; do just "$t"; done\n'
    )
    _ = _write_canonical_json(cwd=tmp_path, slugs=canonical)
    _ = _write_justfile(cwd=tmp_path, body=body)
    result = _run_check(cwd=tmp_path, extra_argv=["--canonical-from", "canonical.json"])
    assert result.returncode == 0, (
        f"expected exit 0 when inline trailing comment is stripped from a slug line; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
