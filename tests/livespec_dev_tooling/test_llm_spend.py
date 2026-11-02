"""The LLM-spend price table prices listed models at list, never sends $0, and corrects once.

WHY IT EXISTS (work item livespec-dev-tooling-mnj7).
`SPECIFICATION/non-functional-requirements.md`, in its section on LLM-spend telemetry pricing,
and the matching scenario in `scenarios.md` were ratified spec-first, because the only
implementation lived in host-local emitter scripts outside any tested repository. Two real
defects had already shipped there: 784 gpt-6.1-sol and 455 gpt-6-luna local Codex responses sent
at `cost_usd` 0 because those models were missing from the table (2026-10-21..30), and every
Sonnet 5.5 cache read priced at $0.20/MTok instead of $0.10 (corrected 2026-11-02,
livespec-dev-tooling-89c8). The table and its rules now live in
`livespec_dev_tooling.llm_spend`, which the host emitters' `prices.py` re-exports.

WHY THESE ARE INTEGRATION-TIER. Each case drives the module the emitters price with end to
end, from a model id as an emitter reads it off a response to the event fields it sends, and
the correction case claims a real done marker on disk twice. Nothing is mocked.
"""

from pathlib import Path

import pytest

from livespec_dev_tooling.llm_spend import (
    ANTHROPIC_PRICES,
    OPENAI_PRICES,
    claim_correction,
    claude_price,
    codex_price,
    cost_usd,
    fallback_fields,
)

pytestmark = pytest.mark.integration

_TOKENS = (1_000, 200_000, 3_000)  # input, cached input, output


def _codex_event(*, model: str) -> dict[str, object]:
    """The cost fields an emitter sends for one Codex response of `_TOKENS` on `model`."""
    (inp, cached, out), priced_as = codex_price(model=model)
    fresh, hit, gen = _TOKENS
    cost = cost_usd(cost=(fresh * inp + hit * cached + gen * out) / 1e6)
    return {"cost_usd": cost, **fallback_fields(model=model, priced_as=priced_as)}


def test_listed_model_is_priced_at_list_with_no_fallback_marker() -> None:
    event = _codex_event(model="gpt-6.1-sol")
    facts = [
        event == {"cost_usd": round((1_000 * 2 + 200_000 * 0.10 + 3_000 * 10) / 1e6, 6)},
        claude_price(model="claude-sonnet-5-5") == (ANTHROPIC_PRICES["claude-sonnet-5-5"], ""),
        ANTHROPIC_PRICES["claude-sonnet-5-5"][2] == 0.10,
    ]
    assert all(facts)


def test_dated_or_suffixed_anthropic_id_is_priced_as_its_listed_model() -> None:
    facts = [
        claude_price(model="claude-haiku-4-5-20251001")
        == (ANTHROPIC_PRICES["claude-haiku-4-5"], ""),
        claude_price(model="claude-opus-5-5[1m]") == (ANTHROPIC_PRICES["claude-opus-5-5"], ""),
    ]
    assert all(facts)


def test_unlisted_model_is_sent_at_a_marked_fallback_price() -> None:
    """Scenario: a token-bearing response on a model the LLM-spend price table does not list."""
    unlisted = _codex_event(model="gpt-7-sol")
    listed = _codex_event(model="gpt-6.1-sol")
    facts = [
        "gpt-7-sol" not in OPENAI_PRICES,
        unlisted["cost_usd"] != 0,
        unlisted["cost_usd"] == listed["cost_usd"],
        unlisted["spend.price_fallback"] is True,
        "gpt-6.1-sol" in str(unlisted["cost_note"]),
        "spend.price_fallback" not in listed,
    ]
    assert all(facts)


def test_unknown_family_falls_back_to_the_provider_top_model_and_is_marked() -> None:
    openai_prices, openai_as = codex_price(model="mystery-model")
    claude_prices, claude_as = claude_price(model="claude-mystery-9")
    proxied_prices, proxied_as = claude_price(model="gpt-6-luna")
    facts = [
        openai_as == "gpt-6-astra",
        openai_prices == OPENAI_PRICES["gpt-6-astra"],
        claude_as == "claude-fable-5-1",
        claude_prices == ANTHROPIC_PRICES["claude-fable-5-1"],
        proxied_as == "gpt-6-luna",
        proxied_prices == (0.10, 0.50, 0.01, 0.10, 0.10),
        fallback_fields(model="", priced_as="gpt-6-astra")["cost_note"]
        == "fallback price gpt-6-astra: no list price for unknown model",
    ]
    assert all(facts)


def test_a_token_bearing_cost_never_rounds_to_zero() -> None:
    facts = [
        cost_usd(cost=1e-8) == 1e-6,
        cost_usd(cost=-1e-8) == -1e-6,
        cost_usd(cost=0) == 0,
        cost_usd(cost=0.1234567) == 0.123457,
    ]
    assert all(facts)


def test_a_second_correction_run_is_refused(tmp_path: Path) -> None:
    done = tmp_path / "state" / "restate-done.json"
    first = claim_correction(done_path=done, record='{"rows": 2}')
    second = claim_correction(done_path=done, record='{"rows": 9}')
    facts = [first is True, second is False, done.read_text(encoding="utf-8") == '{"rows": 2}']
    assert all(facts)
