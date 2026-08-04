"""Released-tag-matched tool-pin projection for fleet bump PRs."""

from __future__ import annotations

from returns.result import Failure, Success

from livespec_dev_tooling.cross_repo.tool_pin_projection import (
    ToolPinProjectionRefused,
    project_shellcheck_pin,
)

__all__: list[str] = []


def test_projects_the_released_shellcheck_pin_into_the_consumer_tools_table() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\npython = "3.10"\nshellcheck = "0.11.0"\n',
        consumer_mise_text='[tools]\npython = "3.10"\n\n[settings]\nyes = true\n',
    )

    assert projected == Success(
        '[tools]\npython = "3.10"\nshellcheck = "0.11.0"\n\n[settings]\nyes = true\n'
    )


def test_updates_an_existing_pin_without_losing_its_comment() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\nshellcheck = "0.11.0"\n',
        consumer_mise_text='[tools]\nshellcheck = "0.10.0" # canonical shell lint\n',
    )

    assert projected == Success('[tools]\nshellcheck = "0.11.0" # canonical shell lint\n')


def test_refuses_a_release_without_an_exact_shellcheck_semver() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\nshellcheck = "latest"\n',
        consumer_mise_text="[tools]\n",
    )

    assert projected == Failure(ToolPinProjectionRefused(reason="released-shellcheck-pin-missing"))


def test_refuses_a_consumer_without_a_tools_table() -> None:
    projected = project_shellcheck_pin(
        released_mise_text='[tools]\nshellcheck = "0.11.0"\n',
        consumer_mise_text="[settings]\nyes = true\n",
    )

    assert projected == Failure(ToolPinProjectionRefused(reason="consumer-tools-table-missing"))
