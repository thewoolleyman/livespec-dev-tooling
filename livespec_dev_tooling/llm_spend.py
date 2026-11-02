"""llm_spend — the ONE price table every LLM-spend emitter prices from, and its correction guard.

This repository's `SPECIFICATION/non-functional-requirements.md`, in its section on LLM-spend
telemetry pricing, requires every emitter that writes the `llm-spend` dataset (the `livespec`
Honeycomb environment) to price from one shared table at list prices, never to send a
token-bearing response at `cost_usd` 0, to mark a fallback-priced event, and to apply a
correction at most once. The emitters themselves are host-local (`~/token-spend-report/scripts`
on the dev host); their `prices.py` re-exports this module, so the table and the rules live
where a test runs (work item livespec-dev-tooling-mnj7).

The contract held here:

* A listed model is priced at its list price below, with no fallback marker.
* A dated or suffixed Anthropic id (`claude-haiku-4-5-20251001`, `claude-opus-5-5[1m]`) is
  the same model as its undated table key, so it is a listed model.
* A model NOT listed is never priced at $0. It is priced as the listed model of its family
  (the family token in its name: sol / terra / luna / astra for OpenAI, fable / opus /
  sonnet / haiku for Anthropic) or, when no family token matches, as the provider's listed
  model with the highest output price, so an unknown model never understates spend. The
  event says so: `fallback_fields` sets `spend.price_fallback` and a `cost_note` naming the
  model it was priced as.
* A correction (a retract/restate pass) claims a done marker before it sends anything, and a
  second claim of the same marker is refused.

Sources: OpenAI https://developers.openai.com/api/docs/pricing (Standard tier, short context up
to 272K input tokens; read 2026-10-31); Anthropic
https://platform.claude.com/docs/en/about-claude/pricing (read 2026-11-01; Claude Haiku 5.5 at
its rate for prompts up to 100,000 tokens). Long-context and long-prompt rates are not applied.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "ANTHROPIC_FAMILY",
    "ANTHROPIC_PRICES",
    "OPENAI_FAMILY",
    "OPENAI_PRICES",
    "anthropic_key",
    "claim_correction",
    "claude_price",
    "codex_price",
    "cost_usd",
    "fallback_fields",
]

# Anthropic $/MTok: input, output, cache read, cache write 5m, cache write 1h.
ANTHROPIC_PRICES: Final[Mapping[str, tuple[float, float, float, float, float]]] = {
    "claude-fable-5-1": (10, 50, 0.25, 12.5, 20),
    "claude-opus-5-5": (4, 20, 0.20, 5, 8),
    "claude-opus-5": (5, 25, 0.50, 6.25, 10),
    "claude-sonnet-5-5": (2, 10, 0.10, 2.5, 4),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125, 0.20),
    "claude-opus-4-8": (5, 25, 0.50, 6.25, 10),
    "claude-sonnet-4-6": (3, 15, 0.30, 3.75, 6),
    "claude-haiku-4-5": (1, 5, 0.10, 1.25, 2),
}
# OpenAI $/MTok: input, cached input, output.
OPENAI_PRICES: Final[Mapping[str, tuple[float, float, float]]] = {
    "gpt-6-astra": (10, 1.00, 50),
    "gpt-6.1-sol": (2, 0.10, 10),
    "gpt-6-sol": (2, 0.20, 10),
    "gpt-6.1-terra": (1, 0.05, 5),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-sol": (4, 0.40, 20),
    "gpt-5.6-terra": (2, 0.20, 12),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
}
# The listed model an unlisted model of each family is priced as: the newest listed member.
OPENAI_FAMILY: Final[Mapping[str, str]] = {
    "astra": "gpt-6-astra",
    "sol": "gpt-6.1-sol",
    "terra": "gpt-6.1-terra",
    "luna": "gpt-6-luna",
}
ANTHROPIC_FAMILY: Final[Mapping[str, str]] = {
    "fable": "claude-fable-5-1",
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
_OPENAI_TOP: Final[str] = max(OPENAI_PRICES, key=lambda m: OPENAI_PRICES[m][2])
_ANTHROPIC_TOP: Final[str] = max(ANTHROPIC_PRICES, key=lambda m: ANTHROPIC_PRICES[m][1])
_SMALLEST_COST: Final[float] = 1e-6


def _family(*, model: str, families: Mapping[str, str], top: str) -> str:
    """The family member a model is priced as, by the first family token in its name, else `top`."""
    tokens = re.split(r"[^a-z]+", model.lower())
    return next((families[tok] for tok in tokens if tok in families), top)


def anthropic_key(*, model: str) -> str:
    """The table key for an Anthropic id, without a `[...]` suffix or a trailing -YYYYMMDD date."""
    return re.sub(r"-\d{8}$", "", model.split("[")[0])


def codex_price(*, model: str) -> tuple[tuple[float, float, float], str]:
    """(input, cached input, output) $/MTok, and the model it was priced as ('' if listed)."""
    if model in OPENAI_PRICES:
        return OPENAI_PRICES[model], ""
    priced_as = _family(model=model, families=OPENAI_FAMILY, top=_OPENAI_TOP)
    return OPENAI_PRICES[priced_as], priced_as


def claude_price(*, model: str) -> tuple[tuple[float, float, float, float, float], str]:
    """(input, output, cache read, cache write 5m, 1h) $/MTok, and the fallback ('' if listed).

    An OpenAI model met in a Claude Code transcript (a proxied session) is priced at its OpenAI
    price, with cached input as the cache-read rate and cache writes at the plain input rate.
    That is not an Anthropic list price, so it is a fallback even when the OpenAI model is listed.
    """
    key = anthropic_key(model=model)
    if key in ANTHROPIC_PRICES:
        return ANTHROPIC_PRICES[key], ""
    openai_model = (
        key if key in OPENAI_PRICES else _family(model=key, families=OPENAI_FAMILY, top="")
    )
    if openai_model:
        inp, cached, out = OPENAI_PRICES[openai_model]
        return (inp, out, cached, inp, inp), openai_model
    priced_as = _family(model=key, families=ANTHROPIC_FAMILY, top=_ANTHROPIC_TOP)
    return ANTHROPIC_PRICES[priced_as], priced_as


def fallback_fields(*, model: str, priced_as: str) -> dict[str, bool | str]:
    """The event fields that mark a fallback-priced response; empty for a listed model."""
    if not priced_as:
        return {}
    note = f"fallback price {priced_as}: no list price for {model or 'unknown model'}"
    return {"spend.price_fallback": True, "cost_note": note}


def cost_usd(*, cost: float) -> float:
    """`cost_usd` as sent: six decimals, but a non-zero cost never rounds to $0.

    A cost under half a micro-dollar (one cached input token) is sent at the smallest
    representable cost, with its sign kept so a retraction still negates it exactly.
    """
    rounded = round(cost, 6)
    if rounded == 0 and cost != 0:
        return _SMALLEST_COST if cost > 0 else -_SMALLEST_COST
    return rounded


def claim_correction(*, done_path: Path, record: str) -> bool:
    """Claim a correction's done marker before it sends; False, writing nothing, if it ran before.

    A correction retracts what was sent and restates it; a second run would retract events
    already sent at the corrected price, so the marker is claimed first and never released.
    """
    if done_path.exists():
        return False
    done_path.parent.mkdir(parents=True, exist_ok=True)
    _ = done_path.write_text(record, encoding="utf-8")
    return True
