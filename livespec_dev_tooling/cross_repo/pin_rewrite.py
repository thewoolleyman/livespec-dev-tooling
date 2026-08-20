"""pin_rewrite — shared rewrite logic for autodiscovered cross-repo pins.

The `bump-pin-rewrite` composite Action receives records emitted by
`pin_autodiscovery` and rewrites the matching pin to a newly published tag. This
module owns the four legacy regex rewrites that used to live as inline Python
heredocs in `.github/actions/bump-pin-rewrite/action.yml`:
`.livespec.jsonc` compat pins, `pyproject.toml` uv-source tags,
`.vendor.jsonc` upstream refs, reusable-workflow `uses:` refs, and Claude
settings marketplace source refs.

The pure `rewrite_pin_in_text` core does no I/O. `main()` owns the env read and
in-place file write for the composite Action's shell glue, using the same
`PIN_*` contract as the sibling specialized rewrite modules.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

__all__: list[str] = ["PinFormat", "rewrite_pin_in_text"]

PinFormat = Literal[
    "livespec_jsonc_compat_pinned",
    "pyproject_toml_uv_sources",
    "vendor_jsonc",
    "github_workflow_uses_ref",
    "claude_settings_extra_known_marketplace_source_ref",
]
_PatternBuilder = Callable[..., re.Pattern[str]]


def rewrite_pin_in_text(
    *, text: str, pin_format: PinFormat, pin_key: str, current_value: str, new_value: str
) -> tuple[str, int]:
    """Return (rewritten_text, match_count) for one autodiscovered pin record.

    `match_count` is 0 when the record target is absent and 1 when the targeted
    pin was rewritten. The caller enforces the expected 1 so stale
    autodiscovery records fail fast.
    """
    pattern = _PATTERN_BUILDERS[pin_format](pin_key=pin_key, current_value=current_value)
    new_text, count = pattern.subn(
        lambda match: match.group(1) + new_value + match.group(2),
        text,
        count=1,
    )
    return new_text, count


def _compile_livespec_jsonc(*, pin_key: str, current_value: str) -> re.Pattern[str]:
    return re.compile(
        r'("'
        + re.escape(pin_key)
        + r'"\s*:\s*\{[^}]*?"pinned"\s*:\s*")'
        + re.escape(current_value)
        + r'(")',
        re.DOTALL,
    )


def _compile_pyproject_uv_source(*, pin_key: str, current_value: str) -> re.Pattern[str]:
    return re.compile(
        r"(^"
        + re.escape(pin_key)
        + r'\s*=\s*\{[^}]*?tag\s*=\s*")'
        + re.escape(current_value)
        + r'(")',
        re.MULTILINE,
    )


def _compile_vendor_jsonc(*, pin_key: str, current_value: str) -> re.Pattern[str]:
    return re.compile(
        r'("name"\s*:\s*"'
        + re.escape(pin_key)
        + r'"[^}]*?"upstream_ref"\s*:\s*")'
        + re.escape(current_value)
        + r'(")',
        re.DOTALL,
    )


def _compile_github_workflow_uses(*, pin_key: str, current_value: str) -> re.Pattern[str]:
    return re.compile(
        r"(^\s+uses:\s+" + re.escape(pin_key) + r"@)" + re.escape(current_value) + r"(\s*)$",
        re.MULTILINE,
    )


def _compile_claude_settings_marketplace_ref(
    *, pin_key: str, current_value: str
) -> re.Pattern[str]:
    return re.compile(
        r'("'
        + re.escape(pin_key)
        + r'"\s*:\s*\{\s*"source"\s*:\s*\{[^}]*?"ref"\s*:\s*")'
        + re.escape(current_value)
        + r'(")',
        re.DOTALL,
    )


_PATTERN_BUILDERS: dict[PinFormat, _PatternBuilder] = {
    "livespec_jsonc_compat_pinned": _compile_livespec_jsonc,
    "pyproject_toml_uv_sources": _compile_pyproject_uv_source,
    "vendor_jsonc": _compile_vendor_jsonc,
    "github_workflow_uses_ref": _compile_github_workflow_uses,
    "claude_settings_extra_known_marketplace_source_ref": _compile_claude_settings_marketplace_ref,
}


def main() -> int:
    """IO entry point — rewrite the pin named by the composite Action `PIN_*` env."""
    pin_format = os.environ["PIN_FORMAT"]
    path = Path(os.environ["PIN_FILE"])
    pin_key = os.environ["PIN_KEY"]
    current_value = os.environ["PIN_CURRENT"]
    new_value = os.environ["PIN_TAG"]
    new_text, count = rewrite_pin_in_text(
        text=path.read_text(encoding="utf-8"),
        pin_format=cast(PinFormat, pin_format),
        pin_key=pin_key,
        current_value=current_value,
        new_value=new_value,
    )
    if count != 1:
        _ = sys.stderr.write(f"::error::failed to rewrite {pin_format} for {pin_key} in {path}\n")
        return 1
    _ = path.write_text(new_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
