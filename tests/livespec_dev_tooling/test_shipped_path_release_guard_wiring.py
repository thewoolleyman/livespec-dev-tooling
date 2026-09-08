"""The shipped-path release guard is ARMED — asserted by test, not by inspection.

Slice C of the R6 guard (work-item `livespec-dev-tooling-sxdz`, ACCEPTANCE A).
Slice B left a runnable, tested check that no repository was gated on. What this
file pins is the WIRING: that this repository's own `lefthook.yml` and `justfile`
actually invoke it, in the right hook, in the right order, through the right
indirection.

A wiring assertion is worth only as much as its NEGATIVE CONTROL, because the
cheap version of this test — read the file, assert a substring is present —
passes against wiring that is subtly wrong and would pass against no wiring at
all if the substring appeared in a comment. So the rules live in
`lefthook_wiring_findings`, a pure function over the file's TEXT, and each rule
is exercised twice: once against the real committed `lefthook.yml` (expecting
silence) and once against a MUTATED copy that breaks exactly that rule
(expecting a finding). The mutations are the ones actually reachable by a future
edit: dropping the entry, shelling out to python instead of delegating to
`just`, dropping the message-file argument, and reordering it ahead of
`01-red-green-replay`.

`lefthook.yml` is parsed as TEXT rather than YAML deliberately — this repository
vendors no YAML parser, and its own CI-matrix checks parse workflow YAML with
regexes for the same reason (`checks/_ci_matrix_parse.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]

# The entry this slice arms, and the entry it must follow. Ordering matters for
# the same reason it matters in the aggregate: red-green-replay is the gate that
# can REJECT a commit outright, so it runs first and the release guard never
# spends its diagnostics on a commit already refused.
_ENTRY = "02-shipped-path-release-guard"
_PRECEDING_ENTRY = "01-red-green-replay"
_JUST_TARGET = "check-shipped-path-release-guard"

# A lefthook command entry: `    <name>:` nested under `commands:`. The capture
# is the entry name; the indent is what distinguishes it from a hook header
# (`commit-msg:`) at column 0.
_COMMAND_ENTRY = re.compile(r"^\s{4,}(?P<name>[0-9a-z][0-9a-z-]*):\s*$", re.MULTILINE)
_HOOK_HEADER = re.compile(r"^(?P<name>[a-z][a-z-]*):\s*$", re.MULTILINE)
# Shelling out to the underlying tool instead of delegating to `just` — the
# spec's lefthook-must-delegate-to-just rule, stated in lefthook.yml's own
# header. `uv run python -m ...` in a `run:` is the exact bypass it forbids.
_DIRECT_TOOL = re.compile(r"\b(uv|python|python3|pytest|ruff)\b")


def _commit_msg_block(*, text: str) -> str | None:
    """The body of the `commit-msg:` hook, or None when the hook is absent."""
    headers = list(_HOOK_HEADER.finditer(text))
    for index, header in enumerate(headers):
        if header.group("name") != "commit-msg":
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        return text[header.end() : end]
    return None


def _entry_stanzas(*, block: str) -> dict[str, str]:
    """Each command entry's name mapped to its OWN stanza, in declared order.

    A stanza is the text between an entry's header and the next entry's, so a
    neighbour's `run:` can never be read as this one's. Returned as one dict
    rather than looked up per entry because the caller needs both the ORDER (to
    check the entry follows red-green-replay) and the BODIES, and deriving both
    from a single pass keeps them from disagreeing. `dict` preserves insertion
    order, so `list(stanzas)` IS the declared order.
    """
    entries = list(_COMMAND_ENTRY.finditer(block))
    stanzas: dict[str, str] = {}
    for index, match in enumerate(entries):
        end = entries[index + 1].start() if index + 1 < len(entries) else len(block)
        stanzas[match.group("name")] = block[match.end() : end]
    return stanzas


def lefthook_wiring_findings(*, text: str) -> list[str]:
    """Every way `text` fails to arm the guard in the `commit-msg` hook.

    An empty list means correctly wired. Returned as reasons rather than a bare
    bool so a failing assertion names WHICH rule broke.
    """
    block = _commit_msg_block(text=text)
    if block is None:
        return ["no `commit-msg:` hook"]
    stanzas = _entry_stanzas(block=block)
    names = list(stanzas)
    if _ENTRY not in names:
        return [f"`commit-msg` carries no `{_ENTRY}` entry"]
    findings: list[str] = []
    if _PRECEDING_ENTRY not in names:
        findings.append(f"`commit-msg` carries no `{_PRECEDING_ENTRY}` entry to order against")
    elif names.index(_ENTRY) < names.index(_PRECEDING_ENTRY):
        findings.append(f"`{_ENTRY}` is ordered BEFORE `{_PRECEDING_ENTRY}`")
    # Looked up on the entry's own stanza, so this cannot fall through to a
    # not-found case: `_ENTRY in names` was just established from the SAME pass.
    run_line = re.search(r"^\s*run:\s*(?P<body>.*)$", stanzas[_ENTRY], re.MULTILINE)
    if run_line is None:
        findings.append(f"`{_ENTRY}` declares no `run:`")
        return findings
    run = run_line.group("body").strip()
    if _DIRECT_TOOL.search(run):
        findings.append(f"`{_ENTRY}` shells out to the tool directly rather than to `just`: {run}")
    elif not run.startswith(f"just {_JUST_TARGET}"):
        findings.append(f"`{_ENTRY}` does not delegate to `just {_JUST_TARGET}`: {run}")
    if "{1}" not in run:
        findings.append(f"`{_ENTRY}` does not pass the message-file argument `{{1}}`: {run}")
    return findings


def _lefthook_text() -> str:
    return (_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8")


def test_the_repository_arms_the_guard_in_its_commit_msg_hook() -> None:
    """The real committed `lefthook.yml` satisfies every wiring rule."""
    assert lefthook_wiring_findings(text=_lefthook_text()) == []


def test_removing_the_entry_is_caught() -> None:
    """NEGATIVE CONTROL: the guard un-armed must not read as armed."""
    text = _lefthook_text()
    stripped = re.sub(rf"^\s+{re.escape(_ENTRY)}:\n(?:\s+run:.*\n)?", "", text, flags=re.MULTILINE)

    assert stripped != text, "the mutation matched nothing, so it controls nothing"
    assert lefthook_wiring_findings(text=stripped) != []


def test_shelling_out_to_python_directly_is_caught() -> None:
    """NEGATIVE CONTROL: the spec's lefthook-must-delegate-to-just rule."""
    text = _lefthook_text().replace(
        f"just {_JUST_TARGET} {{1}}",
        "uv run python -m livespec_dev_tooling.shipped_path_release_guard_check {1}",
    )

    findings = lefthook_wiring_findings(text=text)
    assert any("shells out to the tool directly" in f for f in findings), findings


def test_dropping_the_message_file_argument_is_caught() -> None:
    """NEGATIVE CONTROL: without `{1}` the hook would silently run the RANGE instead."""
    text = _lefthook_text().replace(f"just {_JUST_TARGET} {{1}}", f"just {_JUST_TARGET}")

    findings = lefthook_wiring_findings(text=text)
    assert any("does not pass the message-file argument" in f for f in findings), findings


def test_ordering_the_entry_before_red_green_replay_is_caught() -> None:
    """NEGATIVE CONTROL: the declared order is part of the wiring, not a formatting choice.

    Built as a synthetic document rather than a mutation of the real file. The
    obvious mutation — renaming the entry so it sorts earlier — also makes the
    name `02-shipped-path-release-guard` disappear, so it trips the PRESENCE
    rule and would pass while the ordering rule was entirely absent. Here both
    entries are present and only their order is wrong, which is the one thing
    this control is for.
    """
    text = (
        "commit-msg:\n"
        "  commands:\n"
        f"    {_ENTRY}:\n"
        f"      run: just {_JUST_TARGET} {{1}}\n"
        f"    {_PRECEDING_ENTRY}:\n"
        "      run: just check-red-green-replay {1}\n"
    )

    findings = lefthook_wiring_findings(text=text)
    assert any("ordered BEFORE" in f for f in findings), findings


def test_the_justfile_declares_the_delegated_target() -> None:
    """The `run:` above delegates to a `just` target, so that target must exist.

    Asserted with its `*args` forwarding intact: the recipe takes the message
    file positionally in commit-msg mode and NOTHING in range mode, so a recipe
    that dropped `"$@"` would silently validate the range on every commit.
    """
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    recipe = re.search(
        rf"^{re.escape(_JUST_TARGET)} \*args:\n(?P<body>(?:\s+.*\n)+)", justfile, re.MULTILINE
    )

    assert recipe is not None, f"justfile declares no `{_JUST_TARGET} *args` recipe"
    body = recipe.group("body")
    assert "livespec_dev_tooling.shipped_path_release_guard_check" in body, body
    assert '"$@"' in body, body


def test_the_aggregate_wires_the_target() -> None:
    """`just check` runs the guard in range mode, so the branch gate is not opt-in."""
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    targets = re.search(
        r"^check:\n.*?targets=\(\n(?P<body>.*?)^\s*\)$", justfile, re.DOTALL | re.MULTILINE
    )

    assert targets is not None, "justfile declares no `check:` aggregate with a targets array"
    assert _JUST_TARGET in targets.group("body").split(), targets.group("body")


def test_the_target_inventory_wires_the_target() -> None:
    """`check-targets.txt` is the aggregate's other reader; drift between them is the defect."""
    inventory = (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8").split()

    assert _JUST_TARGET in inventory, inventory


# --- The predicate's remaining verdicts -------------------------------------
#
# Each is a wiring failure a future edit can actually produce, and each is
# asserted over a synthetic document so the rule is pinned independently of what
# the committed `lefthook.yml` happens to say today.


def test_a_document_with_no_commit_msg_hook_is_caught() -> None:
    """A lefthook.yml that lost the hook entirely must not read as armed."""
    text = "pre-commit:\n  commands:\n    00-install-worktree-pack:\n      run: just install-worktree-pack\n"

    assert lefthook_wiring_findings(text=text) == ["no `commit-msg:` hook"]


def test_an_entry_declaring_no_run_is_caught() -> None:
    """A named entry that runs nothing is wiring in appearance only."""
    text = (
        "commit-msg:\n"
        "  commands:\n"
        f"    {_PRECEDING_ENTRY}:\n"
        "      run: just check-red-green-replay {1}\n"
        f"    {_ENTRY}:\n"
        "      glob: '*.py'\n"
    )

    findings = lefthook_wiring_findings(text=text)
    assert any("declares no `run:`" in f for f in findings), findings


def test_delegating_to_the_wrong_just_target_is_caught() -> None:
    """`just` alone is not the rule — it must be THIS repo's guard target."""
    text = (
        "commit-msg:\n"
        "  commands:\n"
        f"    {_PRECEDING_ENTRY}:\n"
        "      run: just check-red-green-replay {1}\n"
        f"    {_ENTRY}:\n"
        "      run: just check-red-green-replay {1}\n"
    )

    findings = lefthook_wiring_findings(text=text)
    assert any(f"does not delegate to `just {_JUST_TARGET}`" in f for f in findings), findings


def test_an_entry_with_no_red_green_replay_to_order_against_is_caught() -> None:
    """Ordering is unverifiable when the anchor is gone, which is itself a finding.

    Reported rather than passed: silence here would mean a lefthook.yml that
    dropped `01-red-green-replay` also silently dropped this file's ordering
    guarantee.
    """
    text = "commit-msg:\n  commands:\n" f"    {_ENTRY}:\n" f"      run: just {_JUST_TARGET} {{1}}\n"

    findings = lefthook_wiring_findings(text=text)
    assert any(f"no `{_PRECEDING_ENTRY}` entry to order against" in f for f in findings), findings
