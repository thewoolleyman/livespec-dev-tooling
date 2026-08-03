"""Consumer-tier: the GitHub App rate-budget token gate.

Covers the `SPECIFICATION/scenarios.md` GitHub App rate-budget scenarios. A
consumer references the public `github-rate-budget-token` composite Action,
which probes the installation budget with a minimum-scope token, waits within a
bounded budget when quota is deficient, and only then mints the final token with
the caller-requested scope.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_DIR = _REPO_ROOT / ".github" / "actions" / "github-rate-budget-token"
_ACTION_FILE = _ACTION_DIR / "action.yml"
_HELPER = _ACTION_DIR / "rate-budget-gate.js"


def _node_env() -> dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ.get("PATH", ""),
    }


def _run_node(*, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", script],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=_node_env(),
    )


def _json_stdout(*, result: subprocess.CompletedProcess[str]) -> object:
    assert result.returncode == 0, (
        f"node helper script must exit 0; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return json.loads(result.stdout)


def test_public_action_declares_scope_preserving_two_token_contract() -> None:
    """The public composite Action exposes the ratified consumer contract."""
    assert _ACTION_FILE.is_file(), (
        "the public composite Action must live at "
        "`.github/actions/github-rate-budget-token/action.yml`"
    )

    text = _ACTION_FILE.read_text(encoding="utf-8")

    for required_input in (
        "client-id:",
        "private-key:",
        "owner:",
        "repositories:",
        "min-core-remaining:",
        "min-graphql-remaining:",
        "cushion-seconds:",
        "max-wait-seconds:",
        "jitter-seed:",
    ):
        assert required_input in text
    assert "token:" in text
    assert "actions/create-github-app-token@v3" in text
    assert text.count("uses: actions/create-github-app-token@v3") == 2
    assert "skip-token-revoke" not in text
    assert "owner: ${{ inputs.owner }}" in text
    assert "repositories: ${{ inputs.repositories }}" in text
    assert "rate-budget-gate.js" in text


def test_helper_reports_healthy_probe_without_waiting_or_minting() -> None:
    """A healthy probe succeeds without waiting; the final mint stays in YAML."""
    script = f"""
      (async () => {{
      const gate = require({json.dumps(str(_HELPER))});
      const sleeps = [];
      const probes = [];
      const env = {{
        INPUT_MIN_CORE_REMAINING: '500',
        INPUT_MIN_GRAPHQL_REMAINING: '200',
        INPUT_CUSHION_SECONDS: '30',
        INPUT_MAX_WAIT_SECONDS: '3900',
        INPUT_JITTER_SEED: 'healthy-seed',
        PROBE_TOKEN: 'probe-token',
        GITHUB_API_URL: 'https://example.test/api'
      }};
      const response = {{
        resources: {{
          core: {{ remaining: 900, reset: 1010 }},
          graphql: {{ remaining: 250, reset: 1020 }}
        }}
      }};
      gate.runGate({{
        env,
        nowSeconds: () => 1000,
        sleepSeconds: async (seconds) => sleeps.push(seconds),
        fetchImpl: async (url, options) => {{
          probes.push({{ url, authorization: options.headers.authorization }});
          return {{ ok: true, status: 200, json: async () => response }};
        }},
        log: () => {{}}
      }}).then((value) => {{
        console.log(JSON.stringify({{ value, sleeps, probes }}));
      }}).catch((error) => {{
        console.error(error.message);
        process.exit(1);
      }});
      }})();
    """
    payload = _json_stdout(result=_run_node(script=script))

    assert payload == {
        "value": {"status": "healthy", "sleptSeconds": 0},
        "sleeps": [],
        "probes": [
            {
                "url": "https://example.test/api/rate_limit",
                "authorization": "Bearer probe-token",
            }
        ],
    }


def test_helper_waits_to_later_deficient_reset_plus_cushion_and_jitter() -> None:
    """A deficient budget waits to the later deficient reset plus cushion+jitter."""
    script = f"""
      const gate = require({json.dumps(str(_HELPER))});
      const sleeps = [];
      const payloads = [
        {{
          resources: {{
            core: {{ remaining: 100, reset: 1100 }},
            graphql: {{ remaining: 0, reset: 1120 }}
          }}
        }},
        {{
          resources: {{
            core: {{ remaining: 600, reset: 1200 }},
            graphql: {{ remaining: 2, reset: 1200 }}
          }}
        }}
      ];
      const env = {{
        INPUT_MIN_CORE_REMAINING: '500',
        INPUT_MIN_GRAPHQL_REMAINING: '1',
        INPUT_CUSHION_SECONDS: '30',
        INPUT_MAX_WAIT_SECONDS: '3900',
        INPUT_JITTER_SEED: 'wait-seed',
        PROBE_TOKEN: 'probe-token'
      }};
      gate.runGate({{
        env,
        nowSeconds: () => 1000,
        sleepSeconds: async (seconds) => sleeps.push(seconds),
        fetchImpl: async () => {{
          const payload = payloads.shift();
          return {{ ok: true, status: 200, json: async () => payload }};
        }},
        log: () => {{}}
      }}).then((value) => {{
        console.log(JSON.stringify({{
          value,
          sleeps,
          jitter: gate.deterministicJitterSeconds('wait-seed')
        }}));
      }}).catch((error) => {{
        console.error(error.message);
        process.exit(1);
      }});
    """
    payload = _json_stdout(result=_run_node(script=script))

    expected_sleep = 120 + 30 + payload["jitter"]
    assert payload == {
        "value": {"status": "healthy", "sleptSeconds": expected_sleep},
        "sleeps": [expected_sleep],
        "jitter": payload["jitter"],
    }
    assert 0 <= payload["jitter"] <= 30


def test_helper_failure_taxonomy_is_bounded_and_distinct() -> None:
    """Invalid input, unusable probes, malformed payloads, and exhaustion differ."""
    script = f"""
      (async () => {{
      const gate = require({json.dumps(str(_HELPER))});
      async function capture(run) {{
        try {{
          await run();
          return 'ok';
        }} catch (error) {{
          return error.message;
        }}
      }}
      const baseEnv = {{
        INPUT_MIN_CORE_REMAINING: '500',
        INPUT_MIN_GRAPHQL_REMAINING: '1',
        INPUT_CUSHION_SECONDS: '30',
        INPUT_MAX_WAIT_SECONDS: '10',
        INPUT_JITTER_SEED: 'taxonomy',
        PROBE_TOKEN: 'probe-token'
      }};
      const invalid = await capture(() => gate.runGate({{
        env: {{ ...baseEnv, INPUT_MIN_CORE_REMAINING: '0' }},
        sleepSeconds: async () => {{}},
        fetchImpl: async () => {{ throw new Error('must not poll'); }},
        log: () => {{}}
      }}));
      let attempts = 0;
      const unusable = await capture(() => gate.runGate({{
        env: baseEnv,
        sleepSeconds: async () => {{}},
        fetchImpl: async () => {{
          attempts += 1;
          return {{ ok: false, status: 503, text: async () => 'unavailable' }};
        }},
        log: () => {{}}
      }}));
      const malformed = await capture(() => gate.runGate({{
        env: baseEnv,
        sleepSeconds: async () => {{}},
        fetchImpl: async () => {{
          return {{ ok: true, status: 200, json: async () => ({{ resources: {{ core: {{ remaining: 1 }} }} }}) }};
        }},
        log: () => {{}}
      }}));
      const exhausted = await capture(() => gate.runGate({{
        env: baseEnv,
        nowSeconds: () => 1000,
        sleepSeconds: async () => {{}},
        fetchImpl: async () => {{
          return {{
            ok: true,
            status: 200,
            json: async () => ({{
              resources: {{
                core: {{ remaining: 1, reset: 2000 }},
                graphql: {{ remaining: 1, reset: 1000 }}
              }}
            }})
          }};
        }},
        log: () => {{}}
      }}));
      console.log(JSON.stringify({{ invalid, unusable, attempts, malformed, exhausted }}));
      }})().catch((error) => {{
        console.error(error.message);
        process.exit(1);
      }});
    """
    payload = _json_stdout(result=_run_node(script=script))

    assert payload == {
        "invalid": "rate-budget-invalid-input",
        "unusable": "probe-unusable",
        "attempts": 3,
        "malformed": "rate-budget-malformed",
        "exhausted": "rate-budget-not-restored",
    }


def test_helper_jitter_is_deterministic_sha256_modulo_31() -> None:
    """The jitter function is deterministic and bounded to [0, 30]."""
    script = f"""
      const crypto = require('crypto');
      const gate = require({json.dumps(str(_HELPER))});
      const seed = 'deterministic';
      const expected = parseInt(
        crypto.createHash('sha256').update(seed).digest('hex').slice(0, 8),
        16
      ) % 31;
      console.log(JSON.stringify({{
        first: gate.deterministicJitterSeconds(seed),
        second: gate.deterministicJitterSeconds(seed),
        expected
      }}));
    """
    payload = _json_stdout(result=_run_node(script=script))

    assert payload["first"] == payload["second"]
    assert payload["first"] == payload["expected"]
    assert 0 <= payload["first"] <= 30
