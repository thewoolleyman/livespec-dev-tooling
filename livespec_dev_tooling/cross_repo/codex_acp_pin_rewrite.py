"""codex_acp_pin_rewrite — bare-value rewrite of the codex-acp Dockerfile ARG pin.

Per `SPECIFICATION/contracts.md` section "Pin autodiscovery rules", the codex-acp pin
is the `ARG CODEX_ACP_VERSION=<version>` line in
`docker/fabro-sandbox/agent/Dockerfile`, carrying the bare npm semver (no `v`
prefix) of the `@agentclientprotocol/codex-acp` adapter baked into the fabro-sandbox
image. Unlike the fabro image tag (a `<layer>-vX.Y.Z` prefixed value), this pin
is a plain bare value, so the rewrite replaces the whole value on the anchored
`ARG` line.

This is the codex-acp sibling of `fabro_image_pin_rewrite`: the composite
Action's `codex_acp_docker_arg` case dispatches this module's `main()` instead
of an inline heredoc, so the rewrite carries typed, unit-tested behavioral
coverage. The bump is factory-gated per section "codex-acp factory gate".

Output discipline mirrors the sibling `fabro_image_pin_rewrite` entry point: the
pure `rewrite_arg_in_text` core does no I/O, and `main()` owns the env read +
in-place file write plus the fail-fast `::error::` annotation (declared in
`pyproject.toml` `supervisor_entry_files`, the surface `no_write_direct`
exempts).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

__all__: list[str] = ["rewrite_arg_in_text"]


def rewrite_arg_in_text(
    *, text: str, arg_name: str, current_value: str, new_value: str
) -> tuple[str, int]:
    """Return (rewritten_text, match_count) for the bare-value ARG pin in `text`.

    Matches the single `ARG <arg_name>=<current_value>` line (anchored to the
    whole line, multiline mode) and rewrites its value to `new_value`.
    `match_count` is 0 (pin absent, text returned unchanged) or 1 (pin
    rewritten) — the caller enforces the expected 1.
    """
    pattern = re.compile(
        r"^ARG " + re.escape(arg_name) + r"=" + re.escape(current_value) + r"$",
        re.MULTILINE,
    )
    new_text, count = pattern.subn(f"ARG {arg_name}={new_value}", text, count=1)
    return new_text, count


def main() -> int:
    """IO entry point — rewrite the codex-acp ARG pin named by the `PIN_*` env in place.

    Reads `PIN_FILE` / `PIN_KEY` / `PIN_CURRENT` / `PIN_TAG` (the `file` / `key`
    / `current` / new `TAG` the composite Action's rewrite step binds for the
    `codex_acp_docker_arg` case), rewrites the `ARG <key>=<current>` line to the
    new value, and writes the file back. A match count other than 1 (the pin the
    autodiscovery record named is gone) writes an `::error::` annotation and
    returns non-zero.
    """
    path = Path(os.environ["PIN_FILE"])
    arg_name = os.environ["PIN_KEY"]
    current_value = os.environ["PIN_CURRENT"]
    new_value = os.environ["PIN_TAG"]
    new_text, count = rewrite_arg_in_text(
        text=path.read_text(encoding="utf-8"),
        arg_name=arg_name,
        current_value=current_value,
        new_value=new_value,
    )
    if count != 1:
        _ = sys.stderr.write(f"::error::failed to rewrite ARG {arg_name} in {path}\n")
        return 1
    _ = path.write_text(new_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
