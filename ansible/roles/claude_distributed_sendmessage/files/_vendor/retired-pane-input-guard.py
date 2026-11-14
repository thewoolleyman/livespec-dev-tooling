#!/usr/bin/env python3
"""Retired pane-input guard: an allow-all stub.

The guard that refused typing into Claude panes was retired on 2026-11-14
(maintainer ruling: "DO NOT PREVENT SESSIONS FROM TYPING INTO PANES"). A
Claude Code session started before the retirement still has the old managed
PreToolUse hook cached and runs this path; deleting the file would make every
Bash call in that session fail. This stub admits every command.
"""

import sys

sys.exit(0)
