"""Paired test for `livespec_dev_tooling/charters/_seed_rules.py`."""

from __future__ import annotations

from livespec_dev_tooling.charters._seed_rules import (
    empty_prev_watcher_init,
    empty_seeded_comparison_lines,
)

__all__: list[str] = []

_ACCUMULATOR = (
    "matched_ref=''\n"
    '[ "$installed_md5" = "$recorded_md5" ] && matched_ref="$generator_ref"\n'
    'if [ -z "$matched_ref" ]; then echo none; fi\n'
    'if [ "$matched_ref" = "$generator_ref" ]; then echo exact; fi'
)

_WATCHER = (
    "last_seen=''\n"
    "pane=$(tmux capture-pane -p -t '=demo:')\n"
    'if [ "$pane" = "$last_seen" ]; then stable=1; fi\n'
    'last_seen="$pane"'
)


def test_a_capture_is_what_makes_a_comparison_a_stability_comparison() -> None:
    """The block-level rule keys on a capture feeding the comparison.

    Both blocks seed a variable empty and later compare it for equality. The
    ONLY structural difference is that the watcher's comparison reads a
    `capture-pane` result, which is precisely the property the rule names — "the
    variable the stability comparison treats as the PREVIOUS capture".
    """
    assert empty_seeded_comparison_lines(block=_ACCUMULATOR) == []
    assert empty_seeded_comparison_lines(block=_WATCHER) == ["last_seen=''"]


def test_the_literal_prev_rule_still_fires_with_no_capture_anywhere() -> None:
    """The capture requirement must NOT narrow the literal-name rule.

    The two rules are deliberately kept side by side and neither may narrow the
    other, so a bare `prev=""` stays a finding even though nothing captures.
    """
    assert empty_prev_watcher_init(text='```bash\nprev=""; stable=0\n```') == ['prev=""; stable=0']


def test_one_defect_described_by_both_rules_is_reported_once() -> None:
    """Deduped BY LINE: reporting it twice doubled fleet exposure counts."""
    watcher = f"```bash\nprev=''\n{_WATCHER.split(chr(10), 1)[1]}\n```"
    assert empty_prev_watcher_init(text=watcher).count("prev=''") == 1
