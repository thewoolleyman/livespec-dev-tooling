"""Tests for the JIT runner admission controller's GitHub response classifier.

`admission_response.py` lives under `ci-runner/supervisor/` alongside the bash
supervisor it will serve, not under `livespec_dev_tooling/` (outside this
repo's declared `source_trees`), so it is loaded directly by path rather than
imported as a package module.

Covers the classification slice of
`SPECIFICATION/non-functional-requirements.md#adaptive-jit-runner-admission-budget`:
only an actual 403/429 with a genuine rate-limit signal (never a bare
credential-denied 403, never 401) may open the shared circuit; a valid
`Retry-After` and a valid `X-RateLimit-Reset` are both honored and the LATER
boundary wins when both are present; missing/malformed guidance falls back to
a conservative finite wait rather than an immediate retry.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

__all__: list[str] = []


def _load_admission_response() -> ModuleType:
    path = Path(__file__).parents[3] / "ci-runner" / "supervisor" / "admission_response.py"
    spec = importlib.util.spec_from_file_location("admission_response", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_successful_response_is_not_retryable_and_does_not_open_the_circuit() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=201, headers={}, body="", now=1_000.0
    )

    assert decision.kind == "ok"
    assert decision.retryable is False
    assert decision.opens_circuit is False
    assert decision.wait_seconds == 0.0


def test_a_429_with_a_valid_retry_after_header_opens_the_circuit_and_honors_it() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=429, headers={"Retry-After": "30"}, body="", now=1_000.0
    )

    assert decision.kind == "rate_limited"
    assert decision.retryable is True
    assert decision.opens_circuit is True
    assert decision.wait_seconds == 30.0
    assert decision.guidance_source == "retry_after"


def test_a_secondary_403_with_ratelimit_remaining_zero_and_a_reset_time_is_honored() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1040"},
        body="",
        now=1_000.0,
    )

    assert decision.kind == "rate_limited"
    assert decision.retryable is True
    assert decision.opens_circuit is True
    assert decision.wait_seconds == 40.0
    assert decision.guidance_source == "rate_limit_reset"


def test_a_secondary_403_identified_only_by_body_text_is_honored() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=403,
        headers={},
        body='{"message": "You have exceeded a secondary rate limit"}',
        now=1_000.0,
    )

    assert decision.kind == "rate_limited"
    assert decision.opens_circuit is True


def test_when_both_guidance_forms_are_present_the_later_boundary_wins() -> None:
    admission_response = _load_admission_response()

    # Retry-After says 10s (-> 1010); X-RateLimit-Reset says 1040 (-> 40s). The
    # reset boundary is later and must win.
    later_reset = admission_response.classify_response(
        status_code=429,
        headers={"Retry-After": "10", "X-RateLimit-Reset": "1040"},
        body="",
        now=1_000.0,
    )
    assert later_reset.wait_seconds == 40.0
    assert later_reset.guidance_source == "later_boundary"

    # Retry-After says 60s (-> 1060); X-RateLimit-Reset says 1040 (-> 40s). The
    # Retry-After boundary is later and must win.
    later_retry_after = admission_response.classify_response(
        status_code=429,
        headers={"Retry-After": "60", "X-RateLimit-Reset": "1040"},
        body="",
        now=1_000.0,
    )
    assert later_retry_after.wait_seconds == 60.0
    assert later_retry_after.guidance_source == "later_boundary"


def test_missing_guidance_falls_back_to_a_conservative_finite_wait_not_immediate_retry() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=429, headers={}, body="", now=1_000.0
    )

    assert decision.kind == "rate_limited"
    assert decision.opens_circuit is True
    assert decision.guidance_source == "fallback"
    assert decision.wait_seconds == admission_response.CONSERVATIVE_FALLBACK_SECONDS
    assert decision.wait_seconds > 0.0


def test_malformed_guidance_is_treated_as_absent_and_falls_back() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=429,
        headers={"Retry-After": "not-a-number", "X-RateLimit-Reset": "also-not-a-number"},
        body="",
        now=1_000.0,
    )

    assert decision.guidance_source == "fallback"
    assert decision.wait_seconds == admission_response.CONSERVATIVE_FALLBACK_SECONDS


def test_a_401_is_a_terminal_auth_failure_never_retryable_never_opens_circuit() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=401, headers={"Retry-After": "30"}, body="", now=1_000.0
    )

    assert decision.kind == "auth_failure"
    assert decision.retryable is False
    assert decision.opens_circuit is False
    assert decision.wait_seconds == 0.0


def test_a_bare_credential_denied_403_is_auth_failure_not_rate_limited() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=403, headers={}, body='{"message": "Bad credentials"}', now=1_000.0
    )

    assert decision.kind == "auth_failure"
    assert decision.retryable is False
    assert decision.opens_circuit is False


def test_a_malformed_ratelimit_remaining_header_falls_through_to_the_body_check() -> None:
    admission_response = _load_admission_response()

    honored_by_body = admission_response.classify_response(
        status_code=403,
        headers={"X-RateLimit-Remaining": "not-a-number"},
        body='{"message": "You have exceeded a secondary rate limit"}',
        now=1_000.0,
    )
    assert honored_by_body.kind == "rate_limited"

    without_body_signal = admission_response.classify_response(
        status_code=403,
        headers={"X-RateLimit-Remaining": "not-a-number"},
        body='{"message": "Bad credentials"}',
        now=1_000.0,
    )
    assert without_body_signal.kind == "auth_failure"


def test_a_server_error_is_retryable_but_never_opens_the_circuit() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=502, headers={}, body="", now=1_000.0
    )

    assert decision.kind == "server_error"
    assert decision.retryable is True
    assert decision.opens_circuit is False


def test_a_plain_client_error_is_a_terminal_non_retryable_other_error() -> None:
    admission_response = _load_admission_response()

    decision = admission_response.classify_response(
        status_code=422, headers={}, body="", now=1_000.0
    )

    assert decision.kind == "other_error"
    assert decision.retryable is False
    assert decision.opens_circuit is False
