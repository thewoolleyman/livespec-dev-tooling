"""§"Comment discipline" — the `ERA` ban, asserted as ARMED over the trees it judges.

The section's first sentence ("comments explain the WHY, not the WHAT") is a
judgement a linter cannot make, and the section knows it: the sentence is
followed by the two mechanical halves that CAN be enforced — "The `ERA` ruff
rule bans commented-out code; LLM-author scaffolding artifacts MUST be
deleted before commit." Commented-out code and scaffolding leftovers are
precisely the WHAT-comments a machine can recognise, and `ERA` is the
mechanism the section names for them.

Selecting a rule is not the same as arming it, and this repository has
already paid for the difference. `pyproject.toml` records it at the
`per-file-ignores` block: the PreToolUse guard hook was once excluded from
ruff WHOLESALE via `extend-exclude`, "and that exclusion took the `BLE001`
backstop down with it". The exclusion was made for one rule and silently
disarmed every other rule over those files. Nothing failed; ruff kept
reporting a clean tree, over a smaller tree than anyone intended.

So the assertion is not "`ERA` appears in `select`" — that is necessary but
convicts nothing that matters. It is that `ERA` still REACHES every
first-party file: no `extend-exclude` glob swallows one, and no
`per-file-ignores` entry that lists `ERA` matches one. The probe set is the
actual `.py` files of the two declared trees (the package and `tests/`)
rather than a synthetic path, so a subtree exclusion cannot slip past a
probe that happens to sit above it.

The companion `comment_line_anchors` check enforces the section's other
recorded failure mode — a comment anchored to a LINE NUMBER, which rots
silently on the next edit above it — and is covered by its own paired unit
suite; its membership in `just check` is asserted with every other shipped
slug by `tests.spec.test_definition_of_done_gates`.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The rule the section names, and the sub-rule ruff reports it under. Either
# spelling in an ignore list disarms commented-out-code detection.
_ERA = "ERA"
_ERA_SUBRULE = "ERA001"

# The trees whose comments the section governs: the shipped package and the
# suite that mirrors it.
_GOVERNED_TREES = ("livespec_dev_tooling", "tests")

# Vendored and generated trees are legitimately excluded — they are not this
# repository's comments to police.
_UNGOVERNED_PARTS = ("_vendor", "__pycache__")

_TOML_HEADER = re.compile(r"^\[(?P<name>[^\]]+)\]$")
_ARRAY = re.compile(r"^(?P<key>[a-z_-]+) = \[(?P<body>[^\]]*)\]$", re.MULTILINE)
_QUOTED = re.compile(r'"([^"]+)"')
_PER_FILE_IGNORE = re.compile(r'^"?(?P<glob>[^"\s=]+)"? = \[(?P<rules>[^\]]*)\]$', re.MULTILINE)


def _toml_sections() -> dict[str, str]:
    """Each `[section]` of `pyproject.toml` mapped to its raw body text.

    Text rather than a parse: stdlib `tomllib` lands in 3.11 and this
    repository's floor is 3.10.
    """
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        header = _TOML_HEADER.match(line)
        current = header.group("name") if header else current
        bodies.setdefault(current, []).append(line)
    return {name: "\n".join(lines) for name, lines in bodies.items()}


def _array_values(*, section: str, key: str) -> list[str]:
    """The quoted elements of one single-line array key in one section."""
    matched = [
        match for match in _ARRAY.finditer(_toml_sections()[section]) if match.group("key") == key
    ]
    assert len(matched) == 1, f"`[{section}]` must declare exactly one `{key}` array"
    return _QUOTED.findall(matched[0].group("body"))


def _governed_files() -> list[str]:
    """Every first-party `.py` file whose comments the section governs."""
    return sorted(
        str(path.relative_to(_REPO_ROOT))
        for tree in _GOVERNED_TREES
        for path in (_REPO_ROOT / tree).rglob("*.py")
        if not any(part in _UNGOVERNED_PARTS for part in path.relative_to(_REPO_ROOT).parts)
    )


def _disarming_globs() -> list[str]:
    """Every `per-file-ignores` glob whose rule list disarms the `ERA` ban."""
    body = _toml_sections()["tool.ruff.lint.per-file-ignores"]
    return [
        matched.group("glob")
        for matched in _PER_FILE_IGNORE.finditer(body)
        if {_ERA, _ERA_SUBRULE} & set(_QUOTED.findall(matched.group("rules")))
    ]


def test_the_commented_out_code_ban_is_selected() -> None:
    """`ERA` — the rule the section names — is in the lint selection."""
    lint_select = _toml_sections()["tool.ruff.lint"]
    assert f'"{_ERA}"' in lint_select, (
        f"the section names `{_ERA}` as the mechanism that bans commented-out code and "
        f"LLM scaffolding leftovers; unselected, it reports nothing and the ban exists "
        f"only as prose"
    )


def test_no_exclusion_disarms_the_ban_over_a_governed_file() -> None:
    """`ERA` reaches every first-party `.py` — no wholesale exclusion, no rule carve-out."""
    governed = _governed_files()
    assert governed, "the governed trees must contain files for the ban to reach"

    excluded = _array_values(section="tool.ruff", key="extend-exclude")
    swallowed = sorted(
        f"{path} (by {glob})"
        for glob in excluded
        for path in governed
        if fnmatch.fnmatch(path, glob)
    )
    assert not swallowed, (
        f"a ruff `extend-exclude` glob removes a governed file from EVERY rule at once, "
        f"not just the one it was added for — this repository has already lost the "
        f"`BLE001` backstop that way, with nothing failing and ruff reporting a clean "
        f"tree over a smaller tree than intended; swallowed={swallowed}"
    )

    carved = sorted(
        f"{path} (by {glob})"
        for glob in _disarming_globs()
        for path in governed
        if fnmatch.fnmatch(path, glob)
    )
    assert not carved, (
        f"no `per-file-ignores` entry may disarm `{_ERA}` over a governed file: "
        f"commented-out code and LLM-author scaffolding are exactly the WHAT-comments "
        f"the section deletes before commit, and a per-path carve-out re-admits them "
        f"where nobody is reading for them; carved={carved}"
    )
