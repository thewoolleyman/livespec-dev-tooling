"""Behavioral gate for ShellCheck pin projection during bump-pin fanout."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.cross_repo import shellcheck_pin_gate

__all__: list[str] = []


def test_sentinel_less_pinned_consumer_fails_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    """Positive control: a pinned, sentinel-less consumer must not skip silently."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mise.toml").write_text('[tools]\nshellcheck = "0.11.0"\n', encoding="utf-8")
    (tmp_path / "justfile").write_text(
        """check:
    targets=(
        check-python
    )

check-python:
    uv run python -m pytest
""",
        encoding="utf-8",
    )
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """jobs:
  checks:
    strategy:
      matrix:
        target:
          - check-python
""",
        encoding="utf-8",
    )

    result = shellcheck_pin_gate.main()

    captured = capsys.readouterr()
    assert result == 1
    assert (
        "::error::ShellCheck pin is present but check-shell-quality is not fully wired"
        in captured.out
    )
    assert "justfile aggregate target check-shell-quality" in captured.out
    assert "check-shell-quality recipe" in captured.out
    assert "CI check-shell-quality job or matrix target" in captured.out
    assert "check-aggregate-completeness" not in captured.out


def test_fully_wired_pinned_consumer_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    """A ShellCheck-pinned consumer passes only when every gate surface is present."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mise.toml").write_text('[tools]\nshellcheck = "0.11.0"\n', encoding="utf-8")
    (tmp_path / "justfile").write_text(
        """check:
    targets=(
        check-shell-quality
    )

check-shell-quality:
    uv run python -m livespec_dev_tooling.checks.shell_quality
""",
        encoding="utf-8",
    )
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """jobs:
  checks:
    strategy:
      matrix:
        target:
          - check-shell-quality
""",
        encoding="utf-8",
    )

    result = shellcheck_pin_gate.main()

    assert result == 0
    assert capsys.readouterr().out == "::notice::ShellCheck pin is gated by check-shell-quality\n"


def test_delegated_aggregate_script_layout_counts_as_wired(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A repo whose `check` recipe delegates its target list to a script is WIRED.

    The fleet uses two legitimate aggregate layouts. Most repos list targets
    inline in the justfile; `livespec-runtime` declares `check *skip_targets:`
    which delegates to `.github/scripts/check.sh`, and its `targets=()` array
    is where `check-shell-quality` lives. Reading only the justfile reported
    that repo as unwired, which is a FALSE failure — and because this gate runs
    inside the bump-pin fanout, the false failure blocked every pin bump into
    it (livespec-dev-tooling-62jh).
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mise.toml").write_text('[tools]\nshellcheck = "0.11.0"\n', encoding="utf-8")
    (tmp_path / "justfile").write_text(
        """check *skip_targets:
    .github/scripts/check.sh "$@"

check-shell-quality:
    uv run python -m livespec_dev_tooling.checks.shell_quality
""",
        encoding="utf-8",
    )
    script = tmp_path / ".github" / "scripts" / "check.sh"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env bash
targets=(
    check-shell-quality
)
""",
        encoding="utf-8",
    )
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """jobs:
  checks:
    strategy:
      matrix:
        target:
          - check-shell-quality
""",
        encoding="utf-8",
    )

    result = shellcheck_pin_gate.main()

    captured = capsys.readouterr()
    assert result == 0, (
        f"a delegated-script aggregate is fully wired and must pass; got {result} "
        f"with output {captured.out!r}"
    )
    assert captured.out == "::notice::ShellCheck pin is gated by check-shell-quality\n"


def test_consumer_without_shellcheck_pin_is_out_of_scope(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The invariant is only for consumers that received the ShellCheck pin."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mise.toml").write_text('[tools]\npython = "3.10"\n', encoding="utf-8")

    result = shellcheck_pin_gate.main()

    assert result == 0
    assert (
        capsys.readouterr().out
        == "::notice::no ShellCheck pin present after tool-pin projection; skipping check-shell-quality invariant\n"
    )
