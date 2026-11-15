"""commit_message — what a commit-msg hook may append trailers to.

git runs the commit-msg hook BEFORE its empty-message abort. A hook that appends
trailers with `git interpret-trailers --in-place` therefore turns an aborted
empty message into a commit whose whole message is a trailer block, and the
first trailer becomes its subject (work-item livespec-dev-tooling-a4w7qr). Both
fleet writers, `factory_provenance_gate` (`Factory-Run-Id`) and the
Red-Green-Replay trailer writer (`TDD-*`), write through
`append_trailers` so that a message with no content stays empty and git's own
abort fires.

A message has content when at least one line is neither blank nor a `#` comment
line. git strips comment lines when it cleans a message that was edited, so a
message made only of them is empty to git too.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

__all__: list[str] = [
    "append_trailers",
    "has_content",
]


def has_content(*, text: str) -> bool:
    """Return True when `text` holds a line that is neither blank nor a `#` comment."""
    return any(line.strip() and not line.startswith("#") for line in text.splitlines())


def append_trailers(
    *,
    message_path: Path,
    text: str,
    trailers: Iterable[tuple[str, str]],
    options: Sequence[str] = (),
) -> None:
    """Append `trailers` to the message file with `git interpret-trailers --in-place`.

    `text` is the message as the caller read it, and `options` are passed to git
    before the trailers. A `text` with no content is left alone: the file is not
    rewritten at all, because even a trailer-less `interpret-trailers` appends a
    newline to it. Failure is not raised, so a git that cannot rewrite the message
    loses the trailers rather than the commit.
    """
    if not has_content(text=text):
        return
    pairs = [arg for key, value in trailers for arg in ("--trailer", f"{key}: {value}")]
    _ = subprocess.run(  # noqa: S603
        ["git", "interpret-trailers", "--in-place", *options, *pairs, str(message_path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
