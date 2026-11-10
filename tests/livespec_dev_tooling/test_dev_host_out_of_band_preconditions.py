"""Every out-of-band precondition of the VPS dev-host roles fails at the start or is recorded.

Work-item `livespec-dev-tooling-c763up`; spec clause: SPECIFICATION/non-functional-requirements.md
§"Host provisioning tree", "Out-of-band preconditions fail at the start". A role that
depends on state it cannot create MUST assert each such input before its first
task that can change the host, and MUST list each step only an operator can take
after the apply in an "Out-of-band" section of its `HOST_VARS.md`. These tests
read the committed roles for the claims that are about order and wording; the
asserts themselves run only in the drift and apply runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []

_ROLES = Path(__file__).resolve().parents[2] / "ansible" / "roles"


def _task_names(*, role: str) -> list[str]:
    tasks = cast(
        "list[dict[str, Any]]", yaml.safe_load((_ROLES / role / "tasks" / "main.yml").read_text())
    )
    return [str(task["name"]) for task in tasks]


def _first_change_follows(*, role: str, asserts: list[str], first_change: str) -> None:
    names = _task_names(role=role)
    assert first_change in names, f"{role}: task {first_change!r} is gone"
    for assertion in asserts:
        assert assertion in names, f"{role}: assert {assertion!r} is gone"
        assert names.index(assertion) < names.index(
            first_change
        ), f"{role}: {assertion!r} must run before {first_change!r}"


def test_restic_backup_asserts_the_six_credentials_before_installing() -> None:
    _first_change_follows(
        role="restic_backup",
        asserts=["Refuse to install when a restic credential does not resolve"],
        first_change="Install restic",
    )
    defaults = cast(
        "dict[str, Any]",
        yaml.safe_load((_ROLES / "restic_backup" / "defaults" / "main.yml").read_text()),
    )
    assert defaults["restic_backup_credential_names"] == [
        "VPS_RESTIC_REPOSITORY",
        "VPS_RESTIC_PASSWORD",
        "VPS_RESTIC_AWS_ACCESS_KEY_ID",
        "VPS_RESTIC_AWS_SECRET_ACCESS_KEY",
        "VPS_RESTIC_S3_BUCKET",
        "VPS_RESTIC_S3_REGION",
    ]


def test_honeycomb_mcp_changes_the_checkout_only_after_every_assert() -> None:
    _first_change_follows(
        role="honeycomb_mcp",
        asserts=[
            "Require the vps-info checkout to carry the stdio wrapper",
            "Require the 1Password service-account wrapper",
            "Require a Honeycomb Management key in the 1Password homelab Environment",
            "Require the honeycomb Claude Code plugin to be installed",
        ],
        first_change="Make the stdio wrapper executable in the checkout",
    )


def test_trigger_recipients_check_asserts_its_key_before_its_first_change() -> None:
    _first_change_follows(
        role="honeycomb_trigger_recipients_check",
        asserts=["Require the Honeycomb Configuration key"],
        first_change="Make the check script executable in the checkout",
    )
    assert "Warn when the Honeycomb Configuration key is missing" not in _task_names(
        role="honeycomb_trigger_recipients_check"
    )


def test_gates_kubeconfig_fetches_before_it_installs_anything() -> None:
    _first_change_follows(
        role="gates_kubeconfig",
        asserts=[
            "Require the control-plane node to have rendered the gates kubeconfig",
            "Refuse a fetched file that is not a kubeconfig",
        ],
        first_change="Install kubectl pinned to the cluster's k3s minor",
    )


def test_codex_config_asserts_the_cloudflare_token_before_any_change_and_the_write() -> None:
    names = _task_names(role="codex_config")
    token_assert = "Require the Cloudflare MCP token to resolve through the wrapper"
    write = "Add the Cloudflare MCP server to the Codex configuration"
    assert write in names
    _first_change_follows(
        role="codex_config",
        asserts=[token_assert, "Require the 1Password credential wrapper"],
        first_change="Stage the released Driver dev-tooling for the observer unit",
    )
    assert names.index(token_assert) < names.index(write)
    defaults = cast(
        "dict[str, Any]",
        yaml.safe_load((_ROLES / "codex_config" / "defaults" / "main.yml").read_text()),
    )
    assert defaults["codex_config_cloudflare_mcp_name"] == "cloudflare-api"
    assert defaults["codex_config_cloudflare_mcp_token_env"] == "CLOUDFLARE_MCP_TOKEN"


_OUT_OF_BAND_STEPS = {
    "onepassword_desktop": ["Sign in", "auto-lock"],
    "claude_desktop": ["Sign in", "keyring"],
    "restic_backup": ["restic doctor", "first backup"],
    "honeycomb_mcp": ["plugin update", "Re-apply"],
    "secret_reinjection": ["seed-github-app-creds.sh", "credstore"],
}


@pytest.mark.parametrize("role", sorted(_OUT_OF_BAND_STEPS))
def test_host_vars_lists_the_post_apply_steps_in_an_out_of_band_section(*, role: str) -> None:
    text = (_ROLES / role / "HOST_VARS.md").read_text()
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert any(heading.startswith("## Out-of-band") for heading in headings), headings
    section = text[text.index("## Out-of-band") :]
    assert "Post-apply steps an operator still performs" in section
    for step in _OUT_OF_BAND_STEPS[role]:
        assert step in section, f"{role}: the out-of-band section must name {step!r}"


def test_the_homelab_aws_prerequisite_is_recorded_for_the_dev_host() -> None:
    text = (_ROLES / "restic_backup" / "HOST_VARS.md").read_text()
    section = text[text.index("## Out-of-band") :]
    assert "/usr/local/bin/with-homelab-aws.sh" in section
    assert "/etc/credstore.encrypted/homelab-aws-bootstrap" in section
