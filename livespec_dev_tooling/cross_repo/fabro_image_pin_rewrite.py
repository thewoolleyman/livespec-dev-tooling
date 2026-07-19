"""fabro_image_pin_rewrite — prefix-preserving rewrite of a fabro-sandbox docker pin.

Extracted from the embedded Python heredoc in
`.github/actions/bump-pin-rewrite/action.yml`'s "Rewrite matching pins to new
tag" step (the `fabro_sandbox_docker_image` case). Per
`SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the fabro-sandbox image
pin is `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"` in a
Fabro `workflow.toml`, and the SAME image reference under a GitHub Actions job's
`container:` block (`image: ghcr.io/…:<tag>`) where a cut-over consumer runs its
CI inside the baked sandbox image. Both surfaces are the one format and this
module rewrites both.

Since the layer split (livespec-3lev.4) that `<tag>` carries a `<layer>-` prefix
— `python-v<X.Y.Z>` / `python-rust-v<X.Y.Z>` — over the bare release version.
The pre-extraction heredoc rewrote the WHOLE tag to the bare release `$TAG`,
dropping the prefix and breaking the pin on every release fan-out. This module
rewrites ONLY the trailing `vX.Y.Z` version and preserves whatever prefix
precedes it.

Output discipline mirrors the sibling `justfile_canonical_reconcile` entry
point: the pure `rewrite_layered_docker_tag` / `rewrite_pin_in_text` core does
no I/O, and `main()` owns the env read + in-place file write plus the fail-fast
`::error::` annotation (declared in `pyproject.toml` `supervisor_entry_files`,
the surface `no_write_direct` exempts).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

__all__: list[str] = ["rewrite_layered_docker_tag", "rewrite_pin_in_text"]


# The version anchor: the trailing `vX.Y.Z` semver in the tag. Whatever precedes
# it (a `base-` / `python-` / `python-rust-` layer prefix, or nothing) is
# preserved verbatim; only this portion is replaced by the new release tag.
_VERSION_RE = re.compile(r"v\d+\.\d+\.\d+")


def rewrite_layered_docker_tag(*, current_tag: str, release_tag: str) -> str:
    """Return the new docker-image tag, preserving any layered-image prefix.

    `current_tag` is the tag as it appears in the pin (e.g. `python-rust-v0.43.0`
    since the layer split, or a bare `v0.43.0`); `release_tag` is the new bare
    release tag (`v<X.Y.Z>`). Only the trailing `vX.Y.Z` version of `current_tag`
    is replaced; the `<layer>-` prefix that precedes it is preserved. A
    `current_tag` with no `vX.Y.Z` anchor (e.g. a pre-layer `sha-<short>`)
    carries no prefix to preserve, so it rewrites to the bare `release_tag`.
    """
    match = _VERSION_RE.search(current_tag)
    prefix = current_tag[: match.start()] if match is not None else ""
    return prefix + release_tag


def rewrite_pin_in_text(
    *, text: str, image_key: str, current_tag: str, release_tag: str
) -> tuple[str, int]:
    """Return (rewritten_text, match_count) for the fabro docker pin in `text`.

    Matches EITHER surface of the one `fabro_sandbox_docker_image` format per
    `SPECIFICATION/contracts.md` §"Pin autodiscovery rules" — the Fabro
    `workflow.toml` line `docker = "<image_key>:<current_tag>"`, or the GitHub
    Actions job `container:` block's `image: <image_key>:<current_tag>` line
    (including its one-line `container: <image>` shorthand) — and rewrites the
    tag via `rewrite_layered_docker_tag`. `match_count` is 0 (pin absent, text
    returned unchanged) or 1 (pin rewritten) — the caller enforces the expected 1.

    Exactly ONE occurrence is rewritten per invocation, which is what makes the
    autodiscovery walk's one-record-per-matching-line rule converge: a file
    carrying the pin on N lines yields N records, and each record's invocation
    consumes the next still-unrewritten occurrence.
    """
    new_tag = rewrite_layered_docker_tag(current_tag=current_tag, release_tag=release_tag)
    escaped_key = re.escape(image_key)
    pattern = re.compile(
        r"("
        # Fabro workflow.toml: docker = "<image>:<tag>"
        r'^[ \t]*docker\s*=\s*"' + escaped_key + r":"
        r"|"
        # GitHub Actions: a job container: block's image: line, or the
        # one-line `container: <image>` shorthand.
        r"^[ \t]*(?:image|container):[ \t]+[\"']?" + escaped_key + r":"
        r")"
        + re.escape(current_tag)
        +
        # Assert (without consuming) that the tag ENDS here, so a longer tag
        # sharing this one's prefix is never truncated — and so whatever
        # closes the line (the TOML quote, a YAML quote, a comment) survives.
        r"(?=[\"'\s#]|$)",
        re.MULTILINE,
    )
    new_text, count = pattern.subn(lambda match: match.group(1) + new_tag, text, count=1)
    return new_text, count


def main() -> int:
    """IO entry point — rewrite the fabro docker pin named by the `PIN_*` env in place.

    Reads `PIN_FILE` / `PIN_KEY` / `PIN_CURRENT` / `PIN_TAG` (the `file` / `key` /
    `current` / new `TAG` the composite Action's rewrite step already binds for
    the `fabro_sandbox_docker_image` case), rewrites the pin's tag
    prefix-preserving, and writes the file back. A match count other than 1 (the
    pin the autodiscovery record named is gone) writes an `::error::` annotation
    and returns non-zero — the heredoc's fail-fast, now behind a tested surface.
    """
    path = Path(os.environ["PIN_FILE"])
    image_key = os.environ["PIN_KEY"]
    current_tag = os.environ["PIN_CURRENT"]
    release_tag = os.environ["PIN_TAG"]
    new_text, count = rewrite_pin_in_text(
        text=path.read_text(encoding="utf-8"),
        image_key=image_key,
        current_tag=current_tag,
        release_tag=release_tag,
    )
    if count != 1:
        _ = sys.stderr.write(
            f"::error::failed to rewrite docker image tag for {image_key} in {path}\n"
        )
        return 1
    _ = path.write_text(new_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
