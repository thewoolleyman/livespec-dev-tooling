"""Tests for `livespec_dev_tooling/agent_hooks/_command_shape.py`.

The command-token-position classification moved out of
`pretooluse_background_guard.py` when work-item
livespec-dev-tooling-zlhnib gave that classification a SECOND consumer:
the foreground hook-running-git refusal the ratified
`SPECIFICATION/contracts.md` section "Agent-session gate-command guard"
requires, beside the background-gate refusal the guard already carried.
A private tokenizer cannot cross a module boundary — pyright strict's
`reportPrivateUsage` and this repo's own `private_calls` check both
reject it — so the parse is a module with a public entry point rather
than a second, drifting copy.

This module pins that cut. The classification's BEHAVIOR is exercised
through the importer, in `test_pretooluse_background_guard.py`, per the
package-private helper convention (`tests_mirror_pairing` (a): a
`_`-prefixed module is exercised through the public function that
imports it). What is pinned HERE is what only this file can see: that
the module exists, that the guard reads the parse from it rather than
carrying its own, and the two properties the second consumer made
load-bearing — the shell-runner FLATTENING every caller inherits, and
the split that keeps `git`'s global `-C` apart from `git commit`'s
`-C`.

The module import is performed INSIDE the test body rather than at
module top. A top-level import would make the extraction's Red leg a
COLLECTION error, which proves only that the module is unimportable —
not that the code has yet to move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []

_PACKAGE = "livespec_dev_tooling.agent_hooks"
_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "agent_hooks"

# The names the extraction moves OUT of the hook module. Their absence
# there is half of what makes this a move rather than a copy.
_MOVED_NAMES = ("_tokenize", "_segments", "_command_word", "_TRANSPARENT_PREFIXES")


def test_command_shape_classification_lives_in_its_own_module() -> None:
    """The parse is its own module, and the hook module no longer carries it."""
    module_path = _PACKAGE_DIR / "_command_shape.py"
    assert module_path.is_file()

    module = importlib.import_module(f"{_PACKAGE}._command_shape")
    assert callable(module.invocations)
    assert module.Invocation is not None

    guard = importlib.import_module(f"{_PACKAGE}.pretooluse_background_guard")
    for name in _MOVED_NAMES:
        assert not hasattr(guard, name), f"{name} is still carried by the hook module"
    # And the hook reads the parse from here rather than from a second copy.
    assert guard.invocations is module.invocations


def test_a_shell_runner_script_is_flattened_for_every_consumer() -> None:
    """`bash -c '<text>'` yields the invocations of `<text>`, not of `bash`.

    The flattening lives in the parse precisely so a consumer cannot
    forget it: a classifier that saw the runner invocation instead would
    read `bash -c 'git commit'` as an invocation of `bash` and let the
    laundered command past. Asserting it here pins the property at the
    only place that can guarantee it for BOTH guards.
    """
    module = importlib.import_module(f"{_PACKAGE}._command_shape")

    found = module.invocations(command="bash -c 'mise exec -- git commit -m x'")

    assert [one.binary for one in found] == ["git"]
    assert found[0].subcommand == "commit"


def test_global_options_and_subcommand_arguments_stay_apart() -> None:
    """`-C` before the subcommand is a directory; after it, it is not.

    `-C` is git's global "run in this directory" option AND `git commit`'s
    own `--reuse-message` short form. A consumer reading `-C` out of one
    undifferentiated argument list therefore reads `git commit -C HEAD~1`
    as naming a repository `HEAD~1`. The split is what makes that
    unrepresentable rather than merely unlikely.
    """
    module = importlib.import_module(f"{_PACKAGE}._command_shape")

    targeted = module.invocations(command="git -C /srv/repo commit -m x")[0]
    assert targeted.options == ("-C", "/srv/repo")
    assert targeted.subcommand == "commit"
    assert targeted.args == ("-m", "x")

    reused = module.invocations(command="git commit -C HEAD~1")[0]
    assert reused.options == ()
    assert reused.subcommand == "commit"
    assert reused.args == ("-C", "HEAD~1")
