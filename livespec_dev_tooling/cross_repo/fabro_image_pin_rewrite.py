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
rewrites ONLY the trailing `vX.Y.Z` version and preserves the `<layer>-` prefix
that precedes it.

A tag with NO prefix to preserve is REFUSED rather than rewritten.
`.github/workflows/fabro-sandbox-image.yml` publishes five layers (`base-`,
`python-`, `python-agent-`, `python-rust-`, `python-rust-agent-`) and every tag
it pushes carries its layer prefix in both the `-sha-<short>` and `-v<X.Y.Z>`
forms — a BARE `vX.Y.Z` is never published. So rewriting an unprefixed pin to a
bare release tag names an image that will never exist, and because the rewrite
"succeeds" it surfaces as a clean-looking diff on a green auto-merge bump PR
pointing at nothing. The refusal is carried in the TYPE (`str | None`,
`tuple[str, int] | None`) so no caller can silently inherit the old fallback;
`main()` turns it into a distinct `::error::` telling the operator to migrate
the pin to a prefixed tag by hand.

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


# The version anchor: the trailing `vX.Y.Z` semver in the tag. The `<layer>-`
# prefix that precedes it (`base-` / `python-` / `python-agent-` /
# `python-rust-` / `python-rust-agent-`) is preserved verbatim; only this
# portion is replaced by the new release tag. The anchor must be present AND
# preceded by a non-empty prefix — see `rewrite_layered_docker_tag`.
_VERSION_RE = re.compile(r"v\d+\.\d+\.\d+")


def rewrite_layered_docker_tag(*, current_tag: str, release_tag: str) -> str | None:
    """Return the new docker-image tag, or `None` when the tag cannot be rewritten.

    `current_tag` is the tag as it appears in the pin (e.g. `python-rust-v0.43.0`
    since the layer split); `release_tag` is the new bare release tag
    (`v<X.Y.Z>`). Only the trailing `vX.Y.Z` version of `current_tag` is
    replaced; the `<layer>-` prefix that precedes it is preserved.

    Returns `None` — refusing the rewrite — in the two shapes that leave NO
    prefix to preserve: no `vX.Y.Z` anchor at all (e.g. a `sha-<short>` or
    `python-sha-<short>` tag), or an anchor at index 0 (an already-bare
    `v0.38.1`). Both would otherwise yield a bare `release_tag`, and the image
    build publishes only layer-prefixed tags, so a bare result names an image
    that will never exist. Refusing is what keeps that from shipping as a
    clean-looking diff on a green auto-merge bump PR pointing at nothing; the
    pin has to be migrated to a prefixed tag by hand instead.
    """
    match = _VERSION_RE.search(current_tag)
    if match is None or match.start() == 0:
        return None
    return current_tag[: match.start()] + release_tag


def rewrite_pin_in_text(
    *, text: str, image_key: str, current_tag: str, release_tag: str
) -> tuple[str, int] | None:
    """Return (rewritten_text, match_count), or `None` when `current_tag` is unrewritable.

    Matches EITHER surface of the one `fabro_sandbox_docker_image` format per
    `SPECIFICATION/contracts.md` §"Pin autodiscovery rules" — the Fabro
    `workflow.toml` line `docker = "<image_key>:<current_tag>"`, or the GitHub
    Actions job `container:` block's `image: <image_key>:<current_tag>` line
    (including its one-line `container: <image>` shorthand) — and rewrites the
    tag via `rewrite_layered_docker_tag`. `match_count` is 0 (pin absent, text
    returned unchanged) or 1 (pin rewritten) — the caller enforces the expected 1.

    When `rewrite_layered_docker_tag` refuses the tag there is no valid
    replacement to substitute, so this returns `None` BEFORE the pattern is
    built and `text` is never touched. That `None` is distinct from the
    `(text, 0)` "pin absent" answer: the pin may well be present — it simply
    carries no layer prefix, so the fan-out cannot maintain it.

    Exactly ONE occurrence is rewritten per invocation, which is what makes the
    autodiscovery walk's one-record-per-matching-line rule converge: a file
    carrying the pin on N lines yields N records, and each record's invocation
    consumes the next still-unrewritten occurrence.
    """
    new_tag = rewrite_layered_docker_tag(current_tag=current_tag, release_tag=release_tag)
    if new_tag is None:
        return None
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
    prefix-preserving, and writes the file back.

    TWO distinct failures return non-zero with DIFFERENT `::error::`
    annotations, because they need different operator actions:

    - An unrewritable tag shape (`rewrite_pin_in_text` returned `None`) — the
      pin carries no layer prefix, so no bump can be synthesized and a human
      must migrate it to a prefixed tag before the fan-out can maintain it.
    - A match count other than 1 — the pin the autodiscovery record named is
      gone, so the record itself went stale. This is the heredoc's original
      fail-fast, now behind a tested surface.

    Either way the file is left untouched.
    """
    path = Path(os.environ["PIN_FILE"])
    image_key = os.environ["PIN_KEY"]
    current_tag = os.environ["PIN_CURRENT"]
    release_tag = os.environ["PIN_TAG"]
    rewritten = rewrite_pin_in_text(
        text=path.read_text(encoding="utf-8"),
        image_key=image_key,
        current_tag=current_tag,
        release_tag=release_tag,
    )
    if rewritten is None:
        _ = sys.stderr.write(
            f'::error::refusing to rewrite docker image tag "{current_tag}" for {image_key} in '
            f"{path}: it carries no layer prefix, so the correct target layer cannot be inferred. "
            f"Migrate this pin by hand to a layer-prefixed tag first — a CI job container wants "
            f"the slim python-{release_tag} or python-rust-{release_tag}; a Fabro sandbox wants "
            f"python-agent-{release_tag} or python-rust-agent-{release_tag}, because the slim "
            f"layers carry no ACP adapters.\n"
        )
        return 1
    new_text, count = rewritten
    if count != 1:
        _ = sys.stderr.write(
            f"::error::failed to rewrite docker image tag for {image_key} in {path}\n"
        )
        return 1
    _ = path.write_text(new_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
