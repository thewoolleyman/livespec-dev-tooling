"""`node_sysctl`'s post-apply check reads its keyring budget as a FLOOR, not an equality.

THE ASSERTION THIS FILE CARRIES (work-item livespec-dev-tooling-5lqito,
Definition of Done assertion 2). The role installs a `/etc/sysctl.d/` drop-in and
then READS THE RUNNING KERNEL VALUE BACK, because writing the file is not
evidence the value took effect — a later-sorting drop-in, or a key this kernel
does not expose, would otherwise leave the role looking installed while changing
nothing. That verification was an EQUALITY, and on a host that is also a Fabro
sandbox host the equality is wrong in one direction: `keyring_quota` co-owns
`kernel.keys.maxbytes` / `kernel.keys.maxkeys` there, and on 2026-10-16 every
`just ansible-apply ansible/ci-pool.yml -l hp-xubuntu` failed at task 24 with
`kernel.keys.maxbytes is 1048576 after apply, expected 200000` — a live value
ABOVE the budget, refused.

WHAT THE ROLE'S NUMBER ACTUALLY IS: a MINIMUM. Its own shipped header derives it
from the pool's peak concurrent containers (~10x the node's pod cap in keys, so
that a container start never meets `EDQUOT`), which is a statement about how
small the ceiling may not be. A live ceiling above it satisfies that derivation;
a live ceiling below it does not. So the post-apply check accepts at-or-above and
refuses below — and the refusing arm is load-bearing, because it is the half that
still catches the shadowing drop-in the equality was right about.

THE FLOOR IS NOT A LICENCE FOR THE SHIPPED FILE TO DRIFT. The role's FIRST task
still refuses, controller-side, a drop-in whose declared values disagree with
these defaults, and `test_keyring_budget_single_effective_value.py` asserts the
same thing in this suite. Only the LIVE reading is compared loosely; what the
role installs stays exact. That file also carries the companion assertion — that
both co-owning drop-ins declare the same numbers, so the effective value does not
depend on which one sorts last or which play ran most recently.

HOW IT IS RESOLVED. Neither Ansible nor Jinja is importable in this suite (both
resolve through `uvx` against their own interpreter), so this file reads the
committed task's comparison and resolves it through a deliberately tiny
vocabulary: one live reading, one operator, one budget. `==` is IN that
vocabulary on purpose — it is the comparison that produced the 2026-10-16
failure, so a regression back to it is resolved and REFUSED here rather than
reported as an expression this file cannot parse.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NODE_SYSCTL = _REPO_ROOT / "ansible" / "roles" / "node_sysctl"

# The keyring budget the role asserts, read from the same `node_sysctl_dropins`
# records the role loops over. Only the `kernel.keys.*` keys: the inotify budget
# in the same list is not co-owned by any other role, so it is not what this
# file is about, even though the comparison below governs it identically.
_KEYRING_BUDGET_RE = re.compile(
    r"^      - key: (?P<key>kernel\.keys\.\w+)\n        value: (?P<value>\d+)$", re.MULTILINE
)
# The post-apply verification's `that:` — one comparison, on one line.
_RUNNING_ASSERT_RE = re.compile(
    r"^- name: Refuse a running [^\n]*\n(?:(?:  [^\n]*)?\n)*?^      - (?P<expression>[^\n]+)$",
    re.MULTILINE,
)
_COMPARISON_RE = re.compile(r"^item\.stdout \| int (?P<symbol>\S+) item\.item\.1\.value \| int$")
_COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    ">=": operator.ge,
    "==": operator.eq,
}


def _asserted_keyring_budget() -> dict[str, int]:
    """The `kernel.keys.*` budget node_sysctl's own defaults require."""
    budget = {
        match["key"]: int(match["value"])
        for match in _KEYRING_BUDGET_RE.finditer(
            (_NODE_SYSCTL / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
    }
    assert budget, (
        f"{_NODE_SYSCTL.name}/defaults/main.yml must declare the role's `kernel.keys.*` budget "
        f"as `- key:`/`value:` pairs inside `node_sysctl_dropins`: that list is what the "
        f"post-apply check compares the live reading against, and a budget this reader cannot "
        f"find is a comparison it cannot resolve"
    )
    return budget


def _post_apply_comparison_symbol() -> str:
    """The operator node_sysctl's post-apply check compares a live reading with."""
    task = _RUNNING_ASSERT_RE.search(
        (_NODE_SYSCTL / "tasks" / "main.yml").read_text(encoding="utf-8")
    )
    assert task is not None, (
        f"{_NODE_SYSCTL.name}/tasks/main.yml must carry a `Refuse a running …` assert whose "
        f"`that:` holds one comparison: it is the post-apply verification, and a role that "
        f"installs a drop-in without proving the live value took effect is the silent failure "
        f"its own header was written to prevent"
    )
    parsed = _COMPARISON_RE.fullmatch(task["expression"].strip())
    assert parsed is not None, (
        f"the post-apply comparison is {task['expression']!r}, which this file cannot resolve "
        f"faithfully. It must be `item.stdout | int <op> item.item.1.value | int`: neither "
        f"Ansible nor Jinja is importable in this suite, so a richer expression would resolve "
        f"WRONG here and right on the host"
    )
    return parsed["symbol"]


def _post_apply_accepts(*, live: int, budget: int) -> bool:
    """Whether the committed post-apply check accepts a live reading of `live`."""
    return _COMPARISONS[_post_apply_comparison_symbol()](live, budget)


def test_the_post_apply_comparison_stays_inside_the_vocabulary_this_file_resolves() -> None:
    """One live reading, one operator, one budget — nothing this file would resolve differently.

    Without this the resolver is free to drift from Jinja, and a drifted resolver
    reports a check that accepts what it refuses — worse than reporting nothing.
    """
    symbol = _post_apply_comparison_symbol()
    assert symbol in _COMPARISONS, (
        f"the post-apply comparison uses {symbol!r}, outside the vocabulary this file resolves "
        f"({sorted(_COMPARISONS)}). Add it here deliberately, with the resolution it has in "
        f"Jinja, rather than leaving the check unresolved in the suite"
    )


def test_the_post_apply_check_accepts_a_live_keyring_value_at_or_above_its_budget() -> None:
    """A co-owner that raises the ceiling must not fail the apply.

    This is the arm that was an equality on 2026-10-16 and failed every ci-pool
    apply on hp-xubuntu. The budget is the minimum the pool's containers need, so
    a live ceiling above it satisfies the role's own derivation.
    """
    for key, floor in sorted(_asserted_keyring_budget().items()):
        assert _post_apply_accepts(live=floor, budget=floor), (
            f"the post-apply check must accept a live {key} exactly at the {floor} budget — "
            f"that is the value the role's own drop-in installs, so refusing it would refuse "
            f"every apply on a node with no co-owner at all"
        )
        assert _post_apply_accepts(live=floor + 1, budget=floor), (
            f"and a live {key} one above it: the budget is a MINIMUM (the role derives it from "
            f"the pool's peak concurrent containers), so a higher live ceiling satisfies that "
            f"derivation rather than contradicting it"
        )
        assert _post_apply_accepts(live=floor * 8, budget=floor), (
            f"and a live {key} far above it — a co-owning drop-in's larger budget is not a "
            f"degree of wrongness, it is the same requirement met with room to spare"
        )


def test_the_post_apply_check_refuses_a_live_keyring_value_below_its_budget() -> None:
    """And the arm that still has to refuse — the shadowing drop-in the equality caught.

    A comparison that accepted anything would discard what the equality was right
    about: a later-sorting drop-in, or a `sysctl -p` of a single file, can leave
    the live ceiling BELOW what the pool needs while the role reports a clean
    apply. That failure is silent on the host — a container start meets `EDQUOT`
    and the job dies with "Disk quota exceeded" — so the refusal has to happen
    here or not at all.
    """
    for key, floor in sorted(_asserted_keyring_budget().items()):
        assert not _post_apply_accepts(live=floor - 1, budget=floor), (
            f"the post-apply check must refuse a live {key} of {floor - 1}, one below its "
            f"{floor} budget: a drop-in shadowed by a later-sorting file that LOWERS the "
            f"ceiling is exactly the silent failure this verification exists to catch"
        )
        assert not _post_apply_accepts(live=0, budget=floor), (
            f"and a live {key} of 0 — the shape a key this kernel does not expose, or an apply "
            f"that never happened, reads as"
        )
