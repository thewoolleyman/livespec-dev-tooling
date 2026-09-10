"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Composite Actions wire contract".

A consumer reaches these Actions by `uses:` path and passes them inputs by
name, so the wire — the input names, which are required, and what an omitted
optional one defaults to — is the whole of what it can depend on. The section
says the path is the semver-stable identifier and "the underlying step list MAY
change between versions", which is exactly why this asserts the declared wire
and not the steps.

Three Actions are held to their documented wire, one clause each beyond the
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

`action.yml` is read as TEXT and its `inputs:` / `outputs:` blocks parsed by
line shape rather than by a YAML parser: this library declares zero runtime
dependencies (`constraints.md` §"Dependencies") and ships no YAML parser, and
the block grammar under assertion is exactly the two-space-indented mapping
GitHub itself requires.
"""

from __future__ import annotations

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
_ENTRY_NAME = re.compile(r"^  (?P<name>[a-z0-9][a-z0-9-]*):$", re.MULTILINE)
_ENTRY_LINE = re.compile(r"^  (?P<name>[a-z0-9][a-z0-9-]*):$")
_FIELD_LINE = re.compile(r"^    (?P<field>[a-z-]+): ?(?P<value>.*)$")

# The invocation form `run-check`'s step list must still name.
_CHECK_INVOCATION = "python -m livespec_dev_tooling.checks."

# Each Action's documented wire: the inputs REQUIRED, the optional inputs and
# their documented defaults, and the declared outputs.
_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "setup": (),
    "run-check": ("check-name",),
    "github-rate-budget-token": ("client-id", "private-key"),
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
}
_DECLARED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "setup": (),
    "run-check": (),
    "github-rate-budget-token": ("token",),
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
    missing_inputs = {
        name: sorted(
            declared
            for declared in (*_REQUIRED_INPUTS[name], *_DEFAULTED_INPUTS[name])
            if declared not in set(_ENTRY_NAME.findall(inputs[name]))
        )
        for name in sources
    }
    absent = {name: names for name, names in missing_inputs.items() if names}
    assert not absent, (
        f"a consumer passes these Actions inputs BY NAME, so a documented input the "
        f"Action no longer declares is a break its `uses:` step cannot see; absent={absent}"
    )

    not_required = {
        name: sorted(
            declared
            for declared in _REQUIRED_INPUTS[name]
            if _fields(block=inputs[name], field="required").get(declared) != "true"
        )
        for name in sources
    }
    relaxed = {name: names for name, names in not_required.items() if names}
    assert not relaxed, (
        f"an input the contract marks REQUIRED must stay required — relaxing it lets a "
        f"caller omit it and reach the step list with an empty value; relaxed={relaxed}"
    )

    drifted = {
        f"{name}.{declared}": (observed, expected)
        for name in sources
        for declared, expected in _DEFAULTED_INPUTS[name].items()
        for observed in [_fields(block=inputs[name], field="default").get(declared)]
        if observed != expected
    }
    assert not drifted, (
        f"a default is the value every caller that omits the input receives and never "
        f"sees, so drift here silently changes behaviour fleet-wide; drifted={drifted}"
    )

    missing_outputs = {
        name: sorted(
            declared
            for declared in _DECLARED_OUTPUTS[name]
            if declared not in set(_ENTRY_NAME.findall(_block(source=sources[name], key="outputs")))
        )
        for name in sources
    }
    unwired_outputs = {name: names for name, names in missing_outputs.items() if names}
    assert not unwired_outputs, (
        f"a declared output is what a caller's downstream step reads by name; "
        f"unwired={unwired_outputs}"
    )

    assert _CHECK_INVOCATION in sources["run-check"], (
        f"`run-check` must still name the `{_CHECK_INVOCATION}<check-name>` invocation "
        f"form — an Action running something else satisfies every input assertion above "
        f"while breaking every consumer's check matrix"
    )
