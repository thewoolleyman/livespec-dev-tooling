"""The green-token CLI vocabulary, including its delegated pre-push extension."""

from __future__ import annotations

from livespec_dev_tooling import pre_push_reuse

__all__: list[str] = []

WRITE = "write"
WRITE_PRE_COMMIT = "write-pre-commit"
CHECK = "check"
WORLD_READING = "world-reading"
UNDECLARED = "undeclared"
PRE_COMMIT_ARGUMENT_COUNT = 2
PRE_PUSH_COMMANDS = pre_push_reuse.PRE_PUSH_COMMANDS
COMMANDS = (WRITE, WRITE_PRE_COMMIT, CHECK, WORLD_READING, UNDECLARED, *PRE_PUSH_COMMANDS)
