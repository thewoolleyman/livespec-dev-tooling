"""Behavioral tests for `codex_acp_pin_rewrite` — bare-value Dockerfile ARG rewrite.

Per `SPECIFICATION/contracts.md` section "Pin autodiscovery rules", the codex-acp pin is
the `ARG CODEX_ACP_VERSION=<version>` line in
`docker/fabro-sandbox/agent/Dockerfile`, carrying the bare npm semver (no `v`
prefix) of the `@zed-industries/codex-acp` adapter. Unlike the fabro image tag
(a `<layer>-vX.Y.Z` prefixed value), this pin is a plain bare value, so the
rewrite replaces the whole value on the anchored `ARG` line. These tests give
the module the behavioral coverage the composite Action's `codex_acp_docker_arg`
case dispatches instead of an inline heredoc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo.codex_acp_pin_rewrite import main, rewrite_arg_in_text

__all__: list[str] = []


_ARG = "CODEX_ACP_VERSION"


# ---------------------------------------------------------------------------
# rewrite_arg_in_text — pure bare-value ARG rewrite
# ---------------------------------------------------------------------------


def test_rewrite_arg_in_text_rewrites_single_arg() -> None:
    """The `ARG CODEX_ACP_VERSION=<value>` line is rewritten once to the new value."""
    text = f"FROM base\nARG {_ARG}=0.16.0\nRUN echo hi\n"
    new_text, count = rewrite_arg_in_text(
        text=text,
        arg_name=_ARG,
        current_value="0.16.0",
        new_value="0.17.0",
    )
    assert count == 1
    assert new_text == f"FROM base\nARG {_ARG}=0.17.0\nRUN echo hi\n"


def test_rewrite_arg_in_text_reports_zero_when_absent() -> None:
    """When the ARG line is not present, the count is zero and text is unchanged."""
    text = "FROM base\nRUN echo no arg here\n"
    new_text, count = rewrite_arg_in_text(
        text=text,
        arg_name=_ARG,
        current_value="0.16.0",
        new_value="0.17.0",
    )
    assert count == 0
    assert new_text == text


def test_rewrite_arg_in_text_reports_zero_when_value_differs() -> None:
    """A present ARG line whose value differs from `current_value` is not rewritten."""
    text = f"ARG {_ARG}=0.15.0\n"
    new_text, count = rewrite_arg_in_text(
        text=text,
        arg_name=_ARG,
        current_value="0.16.0",
        new_value="0.17.0",
    )
    assert count == 0
    assert new_text == text


# ---------------------------------------------------------------------------
# main — env-driven in-place file rewrite
# ---------------------------------------------------------------------------


def test_main_rewrites_file_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` reads the pin coordinates from env and rewrites the file in place."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "Dockerfile"
    _ = pin_file.write_text(f"FROM base\nARG {_ARG}=0.16.0\n", encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _ARG)
    monkeypatch.setenv("PIN_CURRENT", "0.16.0")
    monkeypatch.setenv("PIN_TAG", "0.17.0")
    assert main() == 0
    assert pin_file.read_text(encoding="utf-8") == f"FROM base\nARG {_ARG}=0.17.0\n"


def test_main_returns_nonzero_when_pin_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` reports a non-zero exit and leaves the file untouched when the pin is absent."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "Dockerfile"
    _ = pin_file.write_text("FROM base\nRUN echo no arg here\n", encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _ARG)
    monkeypatch.setenv("PIN_CURRENT", "0.16.0")
    monkeypatch.setenv("PIN_TAG", "0.17.0")
    assert main() == 1
    assert pin_file.read_text(encoding="utf-8") == "FROM base\nRUN echo no arg here\n"
