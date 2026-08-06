"""Detector (d) — a watcher seeded with a value a real capture can equal.

Split out of `_detectors.py`, which sat at EXACTLY the 250-LLOC hard ceiling, so
any addition to it failed `check-file-lloc` regardless of merit. The (d) rule is
the natural seam: it is the only detector carrying two co-operating rules plus
their own four patterns, and it is the one that needed to grow.

TWO RULES, DELIBERATELY SIDE BY SIDE, AND NEITHER MAY NARROW THE OTHER. The
literal rule keys on the spelling `prev=""`. The property rule keys on the
property — the variable a stability comparison treats as the previous capture
must be seeded with something no real capture can equal — so a watcher using any
other variable name cannot evade it. Findings are deduped BY LINE because both
rules describe ONE defect when they both fire, and reporting it twice inflated
fleet exposure counts by 2x on every affected charter.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.charters._shell import code_blocks, is_comment

__all__: list[str] = [
    "empty_prev_watcher_init",
    "empty_seeded_comparison_lines",
]

PREV_EMPTY = re.compile(r"""prev=(?:''|""|\s*$)""", re.MULTILINE)
STABILITY_CMP = re.compile(r'\[\s*"\$(\w+)"\s*=\s*"\$(\w+)"\s*\]')
EMPTY_SEED = re.compile(r"""^\s*(\w+)=(?:""|''|)\s*(?:;|$)""", re.MULTILINE)
# The variable a `capture-pane` assignment feeds. This is what separates a
# STABILITY comparison from an ordinary identity comparison, and keeping it
# deliberately broader than the bounded-capture patterns is the point: any
# capture makes the comparison a watcher's, bounded or not.
CAPTURE_FED = re.compile(r"""^\s*(\w+)=["']?\$\(.*capture-pane""", re.MULTILINE)


def empty_seeded_comparison_lines(*, block: str) -> list[str]:
    """Lines seeding empty a var that a STABILITY comparison then reads.

    A STABILITY comparison reads a CAPTURE — this rule's own subject is "the
    variable the stability comparison treats as the PREVIOUS capture". Keying on
    any `[ "$a" = "$b" ]` also matched ORDINARY IDENTITY comparisons, so an
    empty-seeded search accumulator later compared for equality scored as a
    defective watcher. Measured 2026-08-06 against `homelab`: a
    generator-provenance block seeds an accumulator empty, sets it on a digest
    match, tests it with `[ -z ... ]` to mean not-found, then compares it for
    identity to report which ref matched. No watcher, no capture, no stability.

    THE REMEDY THAT FALSE POSITIVE IMPLIED WAS WORSE THAN THE FINDING, which is
    why the fix landed here and not in the charter. The rule accepts a sentinel
    seed, so satisfying it means seeding the accumulator — and that BREAKS the
    block, because its not-found test is an EMPTINESS test. A sentinel makes it
    never fire, so a missing generator silently reports as found. A gate that
    induces a defect in a charter that had none is worse than no gate.

    So a comparison counts only when a capture feeds one of its sides. That keeps
    the property this rule is about while dropping the spelling it happened to
    key on, and it does NOT narrow the literal rule, which still fires on its own
    with no capture anywhere.
    """
    capture_fed = {match.group(1) for match in CAPTURE_FED.finditer(block)}
    compared: set[str] = set()
    for match in STABILITY_CMP.finditer(block):
        if not capture_fed.isdisjoint(match.groups()):
            compared.update(match.groups())
    found: list[str] = []
    for line in block.splitlines():
        seed = EMPTY_SEED.search(line)
        if seed is not None and seed.group(1) in compared:
            found.append(line.strip())
    return found


def empty_prev_watcher_init(*, text: str) -> list[str]:
    """Watcher seeded with `prev=""`, which an absent session's capture equals."""
    found: list[str] = []
    for block in code_blocks(text=text):
        for line in block.splitlines():
            if not is_comment(line=line) and PREV_EMPTY.search(line):
                found.append(line.strip())
        found.extend(empty_seeded_comparison_lines(block=block))
    return list(dict.fromkeys(found))
