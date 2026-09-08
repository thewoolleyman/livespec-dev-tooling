"""Consumer-tier: a CI workflow consumes the reusable check-matrix.

Covers the `SPECIFICATION/scenarios.md` scenario "a CI workflow consumes
the reusable check-matrix". A consumer's `ci.yml` declares
`jobs.<job>.uses: .../reusable-check-matrix.yml@vX.Y.Z` with a `checks`
input listing the slugs to run; the matrix fans out over those slugs and
each matrix entry executes the named check via the `run-check` composite
Action (`uv run python -m livespec_dev_tooling.checks.<check-name>`).

The consumer-observable contract this test pins is the *matrix shape*:

- the `canonical_checks` thin-transport surface emits a non-empty JSON
  array of check slugs (`{"slugs": [...]}`, exit 0) — the exact shape a
  consumer's `checks` input is populated from; and
- every emitted slug resolves to a real, importable
  `livespec_dev_tooling.checks.<name>` module — so every matrix entry the
  workflow fans out to executes a named check, never a missing module.

Driven through the shipped `livespec_dev_tooling.canonical_checks`
entrypoint (the consumer-facing surface), not internal helpers. The
entrypoint is invoked IN-PROCESS — `monkeypatch.chdir(...)` +
`monkeypatch.setattr(sys, "argv", ...)` + `capsys` + `rc = main()` —
rather than as a `sys.executable -m` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The argv monkeypatch is
what `-m ... --json` supplied before, since `main()` runs the flag
through `argparse`; the assertion targets are unchanged — the int exit
code plus the JSON the entrypoint writes, now read off `capsys` instead
of `CompletedProcess.stdout`.

Branch parity with the retired spawn: this test drove exactly the
argparse arm, the `canonical_check_slugs()` success track, and the stdout
emission, and it still drives those three. The `IOFailure` arm and the
`if __name__ == "__main__": raise SystemExit(main())` line were never
reached from here — the latter is excluded repo-wide by the PRE-EXISTING
`exclude_also` patterns in `[tool.coverage.report]` — so no coverage this
file held has moved and no new exclusion is introduced.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]

# `canonical_checks` emits kebab-case slugs with a `check-` prefix
# (e.g., `check-no-inheritance`); the matrix's `run-check` action maps a
# slug back to a module via `livespec_dev_tooling.checks.<name>`, where
# `<name>` is the snake_case module name. This is that inverse mapping.
_SLUG_PREFIX = "check-"

# The shipped consumer-facing entrypoint, imported by name rather than
# spawned as `python -m <name>` — a consumer reaches the same `main()`.
_ENTRYPOINT_MODULE = "livespec_dev_tooling.canonical_checks"


def _slug_to_module_name(*, slug: str) -> str:
    return slug.removeprefix(_SLUG_PREFIX).replace("-", "_")


def _canonical_slugs(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> list[str]:
    """Run the shipped `--json` thin-transport surface and return the slug list."""
    monkeypatch.chdir(_REPO_ROOT)
    monkeypatch.setattr(sys, "argv", ["canonical-checks", "--json"])
    module = importlib.import_module(_ENTRYPOINT_MODULE)

    returncode = module.main()

    captured = capsys.readouterr()
    assert returncode == 0, (
        f"canonical_checks --json must exit 0; got returncode={returncode} "
        f"stderr={captured.err!r}"
    )
    payload = json.loads(captured.out)
    slugs = payload["slugs"]
    assert isinstance(slugs, list)
    return slugs


def test_canonical_checks_emits_a_nonempty_matrix_array(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The matrix-shape surface emits a non-empty JSON array of check slugs."""
    slugs = _canonical_slugs(monkeypatch=monkeypatch, capsys=capsys)

    assert (
        slugs
    ), "the reusable-check-matrix `checks` input is populated from a non-empty slug array"
    assert all(
        isinstance(slug, str) and slug.startswith(_SLUG_PREFIX) for slug in slugs
    ), f"every matrix slug is a `check-`-prefixed string; got {slugs}"


def test_every_matrix_slug_resolves_to_a_runnable_check_module(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each emitted slug maps to a real importable `checks.<name>` module.

    Every matrix entry the workflow fans out to therefore executes a named
    check via `run-check`, never a missing module.
    """
    checks_dir = _REPO_ROOT / "livespec_dev_tooling" / "checks"

    for slug in _canonical_slugs(monkeypatch=monkeypatch, capsys=capsys):
        module_name = _slug_to_module_name(slug=slug)
        module_file = checks_dir / f"{module_name}.py"
        assert module_file.is_file(), (
            f"matrix slug {slug!r} must map to a runnable check module "
            f"`livespec_dev_tooling/checks/{module_name}.py`; file not found"
        )
