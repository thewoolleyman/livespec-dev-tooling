"""Gate-context disposition: a credential-less check must FAIL inside a gate pod.

R4.S6 (livespec-dev-tooling-ul61), the plan's load-bearing hazard. Two checks
shell out to `gh api` and exit 0 with a structured warning when `gh` is
unauthenticated. That is right on a developer laptop and WRONG in the gate that
authorises a push: a gate pod without a forge token would report the tree green
having silently skipped checks the pushing host runs authenticated.

The disposition is keyed on an EXPLICIT signal rather than on guessing the
environment, because guessing is what makes such a rule fire where it was not
meant to. Outside that context the warn-and-pass behaviour is unchanged.
"""

from __future__ import annotations

from livespec_dev_tooling.checks._gate_context import (
    GATE_CONTEXT_ENV,
    credential_skip_is_failure,
    in_gate_context,
)


def test_absent_signal_is_not_gate_context() -> None:
    assert in_gate_context(env={}) is False


def test_empty_signal_is_not_gate_context() -> None:
    """An empty value is the repo's idiom for "lever unset", not for "on"."""
    assert in_gate_context(env={GATE_CONTEXT_ENV: ""}) is False


def test_set_signal_is_gate_context() -> None:
    assert in_gate_context(env={GATE_CONTEXT_ENV: "1"}) is True


def test_credential_skip_passes_outside_the_gate() -> None:
    """The developer-laptop case: warn and pass, exactly as before."""
    assert credential_skip_is_failure(env={}) is False


def test_credential_skip_fails_inside_the_gate() -> None:
    """The whole point of the slice: no silent skip where a push is authorised."""
    assert credential_skip_is_failure(env={GATE_CONTEXT_ENV: "1"}) is True


def test_signal_is_read_from_the_passed_env_not_the_process() -> None:
    """Callers inject the environment, so a test can never depend on the host's."""
    assert in_gate_context(env={"SOMETHING_ELSE": "1"}) is False
