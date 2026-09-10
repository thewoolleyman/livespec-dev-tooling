"""§"Enforcement-suite invocation" — the ban, read over the region the shipped scan cannot see.

The section states the rule and names the gate that enforces it: "direct tool
invocations (`ruff check ...`, `pytest ...`, `python3 ...`) inside `run:` blocks
are forbidden", enforced by `no_direct_tool_invocation`. So the interesting
question for this file is not whether the rule exists — it is which `run:` text
the shipped gate actually reads.

`no_direct_tool_invocation` matches `^\\s*-?\\s*run:\\s*(.+)$` and judges THAT
CAPTURE. For a one-line `run: uv run pytest` the capture is the command, and the
gate decides correctly. For the BLOCK-SCALAR form —

    - name: just check
      run: |
        uv run pytest tests/

— the capture is the literal `|`, which strips to empty and is banned-prefix-free,
and every line of the block body is never looked at. That is where this
repository's CI actually puts its commands: the gating jobs are `run: |` blocks.
The gate is not wrong about what it reads; it simply does not reach the body, so
a banned invocation added there is accepted in silence.

This file therefore applies the section's own rule over the FULL text of every
`run:` — inline and block-scalar alike — across `lefthook.yml` and the CI
workflow files. It is deliberately a second reader rather than a restatement:
where the shipped gate and this test disagree about a file, this test is reading
strictly more of it.

`python3 -m livespec_dev_tooling.<module>` is NOT a direct tool invocation and is
not banned here. That form is this library's OWN published CLI surface — the
stable `python -m livespec_dev_tooling.checks.<slug>` entry point `contracts.md`
names — and the section's parenthetical enumerates the underlying DEV TOOLS
(`ruff`, `pytest`, a loose `python3 <script>`) that the justfile exists to
single-source. A bare `python3 scripts/whatever.py` is still convicted.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_JUSTFILE = _REPO_ROOT / "justfile"

# The dev tools the section forbids reaching for directly. `uv sync` is the
# documented setup form every job needs before it can invoke `just`, so the
# banned `uv` form is spelled `uv run` exactly as the shipped gate spells it.
_BANNED_PREFIXES = (
    "uv run",
    "pytest",
    "ruff",
    "pyright",
    "lint-imports",
    "mutmut",
    "coverage",
    "python3 ",
    "python ",
)

# This library's own published module CLI — an invocation of the enforcement
# suite's public surface, not of a dev tool.
_OWN_MODULE_CLI = re.compile(r"^python3? -m livespec_dev_tooling\.")

_RUN_KEY = re.compile(r"^(?P<indent>\s*)-?\s*run:\s*(?P<rest>.*)$")
_BLOCK_SCALAR = re.compile(r"^[|>][-+]?$")

# `just <target>` where the target is a literal rather than a `${{ }}` template.
_JUST_TARGET = re.compile(r"(?:^|[|&;(]\s*)just\s+(?P<target>[a-z][a-z0-9-]*)\b")
_RECIPE_DEFINITION = re.compile(r"^(?P<name>[a-z][a-z0-9-]*)(?:\s+[^:]*)?:", re.MULTILINE)


def _yaml_sources() -> list[Path]:
    """`lefthook.yml` plus every CI workflow file, either YAML extension."""
    workflows = sorted(
        path for path in _WORKFLOWS_DIR.iterdir() if path.suffix in (".yml", ".yaml")
    )
    assert workflows, f"the CI workflow universe must not be empty; dir={_WORKFLOWS_DIR}"
    return [_LEFTHOOK, *workflows]


def _command_lines(*, source: Path) -> list[tuple[int, str]]:
    """Every shell line a `run:` in `source` executes, block-scalar bodies included."""
    lines = source.read_text(encoding="utf-8").splitlines()
    collected: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        matched = _RUN_KEY.match(lines[index])
        if matched is None:
            index += 1
            continue
        rest = matched.group("rest").strip()
        if not _BLOCK_SCALAR.match(rest):
            collected.append((index + 1, rest.strip("'\"")))
            index += 1
            continue
        outer = len(matched.group("indent"))
        index += 1
        while index < len(lines):
            body = lines[index]
            if body.strip() and len(body) - len(body.lstrip()) <= outer:
                break
            collected.append((index + 1, body.strip()))
            index += 1
    return [(number, text) for number, text in collected if text and not text.startswith("#")]


def test_no_run_block_body_invokes_a_dev_tool_directly() -> None:
    """The ban, applied to the block-scalar bodies the shipped scan never reads."""
    violations = [
        f"{source.relative_to(_REPO_ROOT)}:{number}: {text}"
        for source in _yaml_sources()
        for number, text in _command_lines(source=source)
        if any(text.startswith(prefix) for prefix in _BANNED_PREFIXES)
        and not _OWN_MODULE_CLI.match(text)
    ]
    assert not violations, (
        f"the enforcement-suite invocation surface is `just <target>`, so no `run:` may "
        f"reach a dev tool directly. These lines live inside `run: |` block bodies, which "
        f"the shipped `no_direct_tool_invocation` scan does not reach — its `run:` capture "
        f"is the block indicator `|`, which strips to empty and passes — so each of them "
        f"is accepted in silence by the gate the section names; violations={violations}"
    )


def test_every_literal_just_target_the_hooks_and_ci_name_is_a_recipe_that_exists() -> None:
    """A delegation to a target that does not exist delegates nowhere."""
    defined = set(_RECIPE_DEFINITION.findall(_JUSTFILE.read_text(encoding="utf-8")))
    assert (
        "check" in defined
    ), f"the justfile must define the `check` aggregate; found={len(defined)}"

    dangling = sorted(
        {
            f"{source.relative_to(_REPO_ROOT)}:{number}: just {target}"
            for source in _yaml_sources()
            for number, text in _command_lines(source=source)
            for target in _JUST_TARGET.findall(text)
            if target not in defined
        }
    )
    assert not dangling, (
        f"`just <target>` is the invocation surface, which means each named target has to "
        f"BE a recipe: a rename that misses one of these leaves the hook or the lane "
        f"invoking nothing, and the rarely-run lanes (pin freshness, release park) do not "
        f"report it until the day they run; dangling={dangling}"
    )
