"""_foreground_pytest — decide whether a FOREGROUND pytest is a full suite to refuse.

The ratified `SPECIFICATION/contracts.md` section "Agent-session
gate-command guard" refuses an agent session's foreground full-suite pytest
on a delegating host, naming the `just gate-start -- <command>` form, because
such a run can outlast the harness's tool-call ceiling and leave no verdict.
This module is that refusal's classifier; `pretooluse_background_guard`
logs and returns the verdict. It sits beside `_foreground_gate`, the git
refusal's classifier, and reads commands through the same
`_command_shape.invocations` parse, so a prefix, a separator or a `bash -c`
script cannot hide a pytest from one guard that the other would see
(livespec-dev-tooling-4pchid's review finding).
"""

from __future__ import annotations

import shlex
from pathlib import Path

from livespec_dev_tooling.agent_hooks._command_shape import Invocation, invocations
from livespec_dev_tooling.gate_command import pytest_command
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import delegated_gate_enabled

__all__: list[str] = [
    "foreground_full_suite_pytest",
]

# Options that take a separate value argument. The list narrows what is read
# as a test path; the existing-path test in `_names_test_path` is what decides
# it, so an option missing here is still not mistaken for a targeted run.
_PYTEST_VALUE_OPTIONS: frozenset[str] = frozenset(
    {
        "-c",
        "--config-file",
        "--confcutdir",
        "--rootdir",
        "-o",
        "--override-ini",
        "-p",
        "-W",
        "--pythonwarnings",
        "-k",
        "-m",
        "-r",
        "--tb",
        "--maxfail",
        "--deselect",
        "--ignore",
        "--ignore-glob",
        "--durations",
        "--durations-min",
        "--junitxml",
        "--junit-xml",
        "--junitprefix",
        "--junit-prefix",
        "--basetemp",
        "--import-mode",
        "--capture",
        "--color",
        "--code-highlight",
        "--assert",
        "--show-capture",
        "--verbosity",
        "--log-level",
        "--log-format",
        "--log-date-format",
        "--log-file",
        "--log-file-level",
        "--log-file-format",
        "--log-file-date-format",
        "--log-cli-level",
        "--log-cli-format",
        "--log-cli-date-format",
        "--doctest-glob",
        "--doctest-report",
        "--cov",
        "--cov-config",
        "--cov-report",
        "--cov-fail-under",
        "--cov-context",
        "--dist",
        "--tx",
        "--rsyncdir",
        "--maxprocesses",
        "--max-worker-restart",
        "--timeout",
        "--timeout-method",
        "--reruns",
        "--reruns-delay",
        "--only-rerun",
        "--rerun-except",
        "--randomly-seed",
        "--hypothesis-seed",
        "--hypothesis-profile",
    }
)


def foreground_full_suite_pytest(*, command: str, cwd: Path) -> Path | None:
    """The repository an eligible host's foreground full-suite pytest targets, or None.

    Reads `command` through `invocations`, the parse the foreground git guard
    uses, so an environment prefix, `nohup`, `mise exec --` or a `bash -c`
    script hides no pytest, and a pytest after `;` or `&&` is still found. The
    target repository is decided as for a git command: each `cd <path>` moves
    it, and any pytest reached before a `cd` targets the session's working
    directory. EVERY pytest is judged, each against the target in force when
    the shell reaches it, so a targeted pytest ahead of a full one hides
    nothing; the first eligible full suite decides the verdict. Text the shell
    cannot lex (an unterminated quote) runs nothing at all, so it is not
    refused.
    """
    try:
        _ = shlex.split(command)
    except ValueError:
        return None
    target = cwd
    for invocation in invocations(command=command):
        if invocation.binary == "cd":
            target = target / (invocation.subcommand or str(Path.home()))
            continue
        pytest_argv = pytest_command(command=_argv(invocation=invocation))
        if pytest_argv is not None:
            eligible = (
                _is_full_suite_pytest(pytest_argv=pytest_argv, cwd=target)
                and delegated_gate_enabled(repo_root=target)
                and gates_kubeconfig_readable()
            )
            if eligible:
                return target
    return None


def _argv(*, invocation: Invocation) -> tuple[str, ...]:
    """Rebuild an invocation's words in shell order, as `pytest_command` reads them."""
    head = (invocation.subcommand,) if invocation.subcommand is not None else ()
    return (invocation.binary, *invocation.options, *head, *invocation.args)


def _is_full_suite_pytest(*, pytest_argv: tuple[str, ...], cwd: Path) -> bool:
    """A pytest names no test path, unless xdist makes it full-suite anyway."""
    arguments = pytest_argv[1:]
    if any(_is_numprocesses_option(argument=argument) for argument in arguments):
        return True
    expect_option_value = False
    for argument in arguments:
        if expect_option_value:
            expect_option_value = False
        elif argument in _PYTEST_VALUE_OPTIONS:
            expect_option_value = True
        elif not argument.startswith("-") and _names_test_path(argument=argument, cwd=cwd):
            return False
    return True


def _names_test_path(*, argument: str, cwd: Path) -> bool:
    """A positional argument is a test path when it is a node id or exists on disk."""
    return "::" in argument or (cwd / argument).exists()


def _is_numprocesses_option(*, argument: str) -> bool:
    """xdist's worker count, spelled `-n 4`, `-n4`, `-n=4` or `--numprocesses[=4]`."""
    return argument.startswith(("-n", "--numprocesses"))
