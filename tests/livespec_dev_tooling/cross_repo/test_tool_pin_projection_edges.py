"""Boundary and I/O coverage for released tool-pin projection."""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.cross_repo.tool_pin_projection import (
    ToolPinProjectionRefused,
    main,
    project_shellcheck_pin,
)

__all__: list[str] = []


def test_refuses_duplicate_released_pins() -> None:
    projected = project_shellcheck_pin(
        released_mise_text=('[tools]\nshellcheck = "0.11.0"\nshellcheck = "0.12.0"\n'),
        consumer_mise_text="[tools]\n",
    )

    assert projected == Failure(ToolPinProjectionRefused(reason="released-shellcheck-pin-missing"))


def test_refuses_a_release_without_a_tools_table() -> None:
    projected = project_shellcheck_pin(
        released_mise_text="[settings]\nyes = true\n",
        consumer_mise_text="[tools]\n",
    )

    assert projected == Failure(ToolPinProjectionRefused(reason="released-shellcheck-pin-missing"))


def test_refuses_duplicate_consumer_pins() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\nshellcheck = "0.11.0"\n',
        consumer_mise_text=('[tools]\nshellcheck = "0.9.0"\nshellcheck = "0.10.0"\n'),
    )

    assert projected == Failure(
        ToolPinProjectionRefused(reason="consumer-shellcheck-pin-ambiguous")
    )


def test_insertion_preserves_crlf_and_repairs_a_missing_final_newline() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\r\nshellcheck = "0.11.0"\r\n',
        consumer_mise_text="[tools]",
    )

    assert projected == Success('[tools]\nshellcheck = "0.11.0"\n')


def test_reads_a_released_pin_without_a_final_newline() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\nshellcheck = "0.11.0"',
        consumer_mise_text="[tools]\n",
    )

    assert projected == Success('[tools]\nshellcheck = "0.11.0"\n')


def test_main_projects_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    released = tmp_path / "released-mise.toml"
    consumer = tmp_path / "consumer-mise.toml"
    _ = released.write_text('[tools]\nshellcheck = "0.11.0"\n', encoding="utf-8")
    _ = consumer.write_text('[tools]\npython = "3.10"\n', encoding="utf-8")
    monkeypatch.setenv("RELEASED_MISE_FILE", str(released))
    monkeypatch.setenv("CONSUMER_MISE_FILE", str(consumer))

    assert main() == 0
    assert consumer.read_text(encoding="utf-8") == (
        '[tools]\npython = "3.10"\nshellcheck = "0.11.0"\n'
    )


def test_main_refuses_without_touching_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    released = tmp_path / "released-mise.toml"
    consumer = tmp_path / "consumer-mise.toml"
    _ = released.write_text('[tools]\nshellcheck = "latest"\n', encoding="utf-8")
    original = '[tools]\npython = "3.10"\n'
    _ = consumer.write_text(original, encoding="utf-8")
    monkeypatch.setenv("RELEASED_MISE_FILE", str(released))
    monkeypatch.setenv("CONSUMER_MISE_FILE", str(consumer))

    assert main() == 1
    assert consumer.read_text(encoding="utf-8") == original
