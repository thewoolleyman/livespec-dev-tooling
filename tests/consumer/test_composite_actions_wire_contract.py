"""Consumer-tier: the Composite Actions wire contract of `SPECIFICATION/contracts.md`.

A consumer reaches these Actions by `uses:` path and passes them inputs by
name, so the wire — the input names, which are required, and what an omitted
optional one defaults to — is the whole of what it can depend on. The section
says the path is the semver-stable identifier and "the underlying step list MAY
change between versions", which is exactly why this asserts the declared wire
and not the steps.

Five Actions are held to their documented wire, one clause each beyond the
shared "declares its inputs, outputs, and required permissions" rule:

- **`setup`** — one optional input defaulting to `.python-version`, and no
  outputs.
- **`run-check`** — `check-name` REQUIRED, `working-directory` defaulting to
  `.`, `extra-args` defaulting to the empty string; and its step list still
  naming the `python -m livespec_dev_tooling.checks.<slug>` invocation form,
  because an Action that ran something else would satisfy every input assertion
  above while breaking every consumer's matrix entry.
- **`github-rate-budget-token`** — the two required credential inputs, the two
  scope inputs that "default `""` and preserve
  `actions/create-github-app-token@v3`'s current-repository scope when
  omitted", and the five numeric/seed inputs with the exact defaults the section
  states (`500`, `1`, `30`, `3900`, `""`). Each default is a number a caller
  omits and therefore never sees; drifting one silently changes the budget every
  fleet workflow waits on. Its single declared output `token` is asserted too.
- **`publish-flake-retries`** — one optional `suffix` input defaulting to the
  empty string, and no outputs.
- **`forge-read`** — no inputs and no outputs.

`action.yml` is read as TEXT and its `inputs:` / `outputs:` blocks parsed by
line shape rather than by a YAML parser: this library declares zero runtime
dependencies (the dependency rules of `constraints.md`) and ships no YAML
parser, and the block grammar under assertion is exactly the two-space-indented
mapping GitHub itself requires.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTIONS_DIR = _REPO_ROOT / ".github" / "actions"

# A top-level `inputs:` / `outputs:` block runs until the next column-0 key.
_TOP_LEVEL_BLOCK = "^{key}:\n(?P<body>(?:[ \t].*\n|\n)*)"
# An entry name is the sole two-space-indented key; `required:` / `default:`
# sit one level deeper.
_ENTRY_NAME = re.compile(r"^  (?P<name>[A-Za-z_][A-Za-z0-9_-]*):$", re.MULTILINE)
_ENTRY_LINE = re.compile(r"^  (?P<name>[A-Za-z_][A-Za-z0-9_-]*):$")
_FIELD_LINE = re.compile(r"^    (?P<field>[a-z-]+): ?(?P<value>.*)$")

# The invocation form `run-check`'s step list must still name.
_CHECK_INVOCATION = "python -m livespec_dev_tooling.checks."
_FORGE_READ_POLICY_MODULE = "livespec_dev_tooling.budgeted_gh"

# Each Action's documented wire: the inputs REQUIRED, the optional inputs and
# their documented defaults, and the declared outputs.
_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "setup": (),
    "run-check": ("check-name",),
    "github-rate-budget-token": ("client-id", "private-key"),
    "publish-flake-retries": (),
    "forge-read": (),
}
_DEFAULTED_INPUTS: dict[str, dict[str, str]] = {
    "setup": {"python-version-file": ".python-version"},
    "run-check": {"working-directory": ".", "extra-args": ""},
    "github-rate-budget-token": {
        "owner": "",
        "repositories": "",
        "min-core-remaining": "500",
        "min-graphql-remaining": "1",
        "cushion-seconds": "30",
        "max-wait-seconds": "3900",
        "jitter-seed": "",
    },
    "publish-flake-retries": {"suffix": ""},
    "forge-read": {},
}
_DECLARED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "setup": (),
    "run-check": (),
    "github-rate-budget-token": ("token",),
    "publish-flake-retries": (),
    "forge-read": (),
}


def _action_source(*, name: str) -> str:
    """The `action.yml` text at the path a consumer's `uses:` names."""
    path = _ACTIONS_DIR / name / "action.yml"
    assert path.is_file(), f"the composite Action `{name}` must ship at {path}"
    return path.read_text(encoding="utf-8")


def _block(*, source: str, key: str) -> str:
    """The body of `source`'s top-level `key:` mapping, or the empty string."""
    matched = re.search(_TOP_LEVEL_BLOCK.format(key=key), source, re.MULTILINE)
    return "" if matched is None else matched.group("body")


def _fields(*, block: str, field: str) -> dict[str, str]:
    """Each entry in `block` mapped to its `field` value, quotes stripped.

    Scanned line by line rather than by one regex: an entry declares several
    fields in sequence, and a single non-overlapping pattern reads only the
    first of them.
    """
    values: dict[str, str] = {}
    entry = ""
    for line in block.splitlines():
        named = _ENTRY_LINE.match(line)
        if named is not None:
            entry = named.group("name")
        declared = _FIELD_LINE.match(line)
        if declared is not None and declared.group("field") == field:
            values[entry] = declared.group("value").strip().strip('"')
    return values


def _entry_names(*, block: str) -> set[str]:
    """The entry names directly declared in an Action wire block."""
    return set(_ENTRY_NAME.findall(block))


def test_every_shipped_composite_action_declares_its_documented_wire() -> None:
    """Each Action's required inputs, optional defaults, and outputs match the contract."""
    sources = {name: _action_source(name=name) for name in sorted(_REQUIRED_INPUTS)}

    not_composite = sorted(
        name for name, source in sources.items() if "using: composite" not in source
    )
    assert not not_composite, (
        f"each shipped Action must still be a COMPOSITE Action — the kind a consumer's "
        f"`uses: <path>` step runs in-line; not_composite={not_composite}"
    )

    inputs = {name: _block(source=source, key="inputs") for name, source in sources.items()}
    expected_inputs = {
        name: set(_REQUIRED_INPUTS[name]) | set(_DEFAULTED_INPUTS[name]) for name in sources
    }
    declared_inputs = {name: _entry_names(block=inputs[name]) for name in sources}
    assert declared_inputs == expected_inputs, (
        "a consumer passes these Actions inputs BY NAME, so the declared input set "
        f"must exactly match the documented wire; observed={declared_inputs}, "
        f"expected={expected_inputs}"
    )

    expected_required = {
        name: {
            input_name: "true" if input_name in _REQUIRED_INPUTS[name] else "false"
            for input_name in expected_inputs[name]
        }
        for name in sources
    }
    declared_required = {name: _fields(block=inputs[name], field="required") for name in sources}
    assert declared_required == expected_required, (
        "the required flags are part of the wire: a required input cannot be relaxed "
        f"and an optional input cannot become required; observed={declared_required}, "
        f"expected={expected_required}"
    )

    declared_defaults = {name: _fields(block=inputs[name], field="default") for name in sources}
    assert declared_defaults == _DEFAULTED_INPUTS, (
        "a default is the value every caller that omits the input receives and never "
        f"sees, so Action defaults must exactly match the documented wire; "
        f"observed={declared_defaults}, expected={_DEFAULTED_INPUTS}"
    )

    declared_outputs = {
        name: _entry_names(block=_block(source=sources[name], key="outputs")) for name in sources
    }
    expected_outputs = {name: set(outputs) for name, outputs in _DECLARED_OUTPUTS.items()}
    assert declared_outputs == expected_outputs, (
        "a declared output is what a caller's downstream step reads by name, so the "
        f"output set must exactly match the documented wire; observed={declared_outputs}, "
        f"expected={expected_outputs}"
    )

    assert _CHECK_INVOCATION in sources["run-check"], (
        f"`run-check` must still name the `{_CHECK_INVOCATION}<check-name>` invocation "
        f"form — an Action running something else satisfies every input assertion above "
        f"while breaking every consumer's check matrix"
    )


def test_forge_read_command_docstring_names_the_budgeted_read_policy_module() -> None:
    """The workflow-side command names the same policy module as its Action."""
    action_source = _action_source(name="forge-read")
    command_path = _ACTIONS_DIR / "forge-read" / "livespec-forge-read"
    command_source = command_path.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(command_source))

    assert _FORGE_READ_POLICY_MODULE in action_source
    assert docstring is not None
    assert _FORGE_READ_POLICY_MODULE in docstring
    assert "livespec_dev_tooling._forge_policy" not in docstring
