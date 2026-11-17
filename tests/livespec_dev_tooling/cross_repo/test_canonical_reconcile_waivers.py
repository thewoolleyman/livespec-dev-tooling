"""Regression coverage for waived canonical checks during bump-pin reconcile."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo import (
    ci_yaml_canonical_reconcile,
    justfile_canonical_reconcile,
)

__all__: list[str] = []


_JUSTFILE = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

_CI_YAML = """name: CI

jobs:
  checks:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target:
          - check-aggregate-completeness
          - check-lint
    steps:
      - run: just ${{ matrix.target }}
"""

_PYPROJECT = """[tool.livespec_dev_tooling]
canonical_check_waivers = [
    { slug = "check-alpha", reason = "this consumer does not support alpha" },
]
"""


def test_reconcile_omits_waived_slug_from_aggregate_and_ci(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A waiver stays honoured while an unwaived canonical check is adopted.

    The bump reconciles both surfaces in sequence.  `check-alpha` is canonical
    but explicitly waived by the consumer, so it must gain neither a `just
    check` target/recipe nor a CI matrix entry.  `check-beta` is the control:
    it is equally absent but unwaived, and therefore must be added to both
    surfaces in their normal positions.
    """
    justfile = tmp_path / "justfile"
    justfile.write_text(_JUSTFILE, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    ci_yaml = tmp_path / ".github" / "workflows" / "ci.yml"
    ci_yaml.parent.mkdir(parents=True)
    ci_yaml.write_text(_CI_YAML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CANONICAL_JSON",
        '{"slugs": ["check-aggregate-completeness", "check-alpha", "check-beta"]}',
    )

    assert justfile_canonical_reconcile.main() == 0
    assert ci_yaml_canonical_reconcile.main() == 0

    reconciled_justfile = justfile.read_text(encoding="utf-8")
    reconciled_ci_yaml = ci_yaml.read_text(encoding="utf-8")
    assert "check-alpha" not in reconciled_justfile
    assert "check-alpha" not in reconciled_ci_yaml
    assert "        check-beta\n" in reconciled_justfile
    assert (
        "\ncheck-beta:\n    uv run python -m livespec_dev_tooling.checks.beta\n"
        in reconciled_justfile
    )
    assert (
        "          - check-aggregate-completeness\n"
        "          - check-beta\n"
        "          - check-lint\n"
    ) in reconciled_ci_yaml
