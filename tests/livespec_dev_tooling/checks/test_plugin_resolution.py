"""Outside-in test for `livespec_dev_tooling/checks/plugin_resolution.py`.

The Verifier slot of the Conformance Pattern's Cross-harness plugin-resolution
concern (concern #2), per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Conformance Pattern" and `SPECIFICATION/contracts.md` §"Shared check
inventory" → §"`plugin_resolution` check".

These tests inject a deterministic fake `CliRunner` (the cli_e2e seam) and a
stubbed `shutil.which`, so NO subprocess is ever spawned (the check is exempt
from the `subprocess_spawn_allowlist`). The load-bearing case is the **ob-4ts
proof**: a fake `CliRunner` whose raw-`bd` fallback "succeeds" but whose
`/livespec:*` slash command does NOT resolve must drive the check to FAIL
(exit 4) — because the Verifier only ever invokes the command surface and never
substitutes a raw-CLI success. The skip-vs-fail distinction folds in work-item
livespec-mjnv: an unavailable harness binary SKIPs (it "can't run here"), it
does not fail.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import plugin_resolution
from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing.cli_e2e import CliResult, CliRunner

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


def _which_none(_cmd: str) -> str | None:
    """`shutil.which` stand-in: the harness binary is unavailable in this environment."""
    return None


def _which_path(cmd: str) -> str | None:
    """`shutil.which` stand-in: every harness binary resolves to a fake path."""
    return "/usr/bin/" + cmd


def _runner_factory(runner: CliRunner) -> Callable[..., Result[CliRunner, Exception]]:
    """Build a typed `select_runner` stand-in returning a fixed injected runner.

    Returns a `Success`, matching `select_runner`'s converted shape — the stand-in
    has to carry the same container the real function does, or `plugin_resolution`
    would unwrap something this never produced.
    """

    def factory(*, injected_runner: CliRunner | None = None) -> Result[CliRunner, Exception]:
        _ = injected_runner
        return Success(runner)

    return factory


@dataclass(frozen=True, kw_only=True)
class _FakeCliRunner:
    """Deterministic `CliRunner` that records prompts and never spawns.

    Conforms structurally to `livespec_dev_tooling.testing.cli_e2e.CliRunner`.
    `exit_for_prompt` maps a prompt to an exit code; the default models the
    ob-4ts class — a raw `bd …` fallback "succeeds" (exit 0) while a
    `/livespec:*` slash command does NOT resolve (exit 1).
    """

    raw_fallback_exit: int = 0
    slash_exit: int = 1
    recorded: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        _ = (home, cwd, resume_session_id)
        self.recorded.append(prompt)
        exit_code = self.raw_fallback_exit if prompt.startswith("bd") else self.slash_exit
        return CliResult(exit_code=exit_code, stdout="", stderr="", session_id=None)


@dataclass(frozen=True, kw_only=True)
class _ResolvingCliRunner:
    """`CliRunner` that resolves every command surface to exit 0 (a PASS)."""

    recorded: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        _ = (home, cwd, resume_session_id)
        self.recorded.append(prompt)
        return CliResult(exit_code=0, stdout="", stderr="", session_id=None)


def _write_livespec_jsonc(*, root: Path, body: str) -> None:
    _ = (root / ".livespec.jsonc").write_text(body, encoding="utf-8")


_VALID_SUPPORTED_AND_EXEMPT = """{
  "harnesses": {
    "codex":  { "status": "supported", "canonical_command": "livespec:next" },
    "claude": { "status": "exempt", "reason": "claude plugin surface not provisioned here" }
  }
}
"""


# ---------------------------------------------------------------------------
# Always-on declaration-integrity gate — load_harnesses.
# ---------------------------------------------------------------------------


def test_load_harnesses_skips_when_file_absent(*, tmp_path: Path) -> None:
    """No `.livespec.jsonc` → SKIP (no declared harness surface)."""
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "skip"
    assert ".livespec.jsonc" in load.detail


def test_load_harnesses_skips_when_unparseable(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that is not parseable JSONC → SKIP (deferred to config tooling)."""
    _write_livespec_jsonc(root=tmp_path, body="@@@ not parseable @@@")
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "skip"
    assert "unreadable" in load.detail


def test_load_harnesses_skips_when_top_level_not_object(*, tmp_path: Path) -> None:
    """A top-level non-object `.livespec.jsonc` → SKIP."""
    _write_livespec_jsonc(root=tmp_path, body="[1, 2, 3]")
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "skip"
    assert "not an object" in load.detail


def test_load_harnesses_fails_when_no_harnesses_key(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` present WITHOUT a `harnesses` key → ABSENT (required since M6)."""
    _write_livespec_jsonc(root=tmp_path, body='{ "template": "livespec" }')
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "absent"
    assert "harnesses" in load.detail


def test_load_harnesses_malformed_when_harnesses_not_object(*, tmp_path: Path) -> None:
    """`harnesses` that is not an object → MALFORMED (fail-closed)."""
    _write_livespec_jsonc(root=tmp_path, body='{ "harnesses": "claude" }')
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "must be an object" in load.detail


def test_load_harnesses_malformed_unknown_harness(*, tmp_path: Path) -> None:
    """An unknown harness key → MALFORMED (garbled declaration)."""
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "gpt": { "status": "supported", "canonical_command": "x" } } }',
    )
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "unknown harness" in load.detail


def test_load_harnesses_malformed_entry_not_object(*, tmp_path: Path) -> None:
    """A harness entry that is not an object → MALFORMED."""
    _write_livespec_jsonc(root=tmp_path, body='{ "harnesses": { "claude": "x" } }')
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "entry must be an object" in load.detail


def test_load_harnesses_malformed_bad_status(*, tmp_path: Path) -> None:
    """A `status` outside {supported, exempt} → MALFORMED."""
    _write_livespec_jsonc(
        root=tmp_path, body='{ "harnesses": { "claude": { "status": "maybe" } } }'
    )
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "status" in load.detail


def test_load_harnesses_malformed_supported_missing_command(*, tmp_path: Path) -> None:
    """A `supported` harness with no `canonical_command` → MALFORMED."""
    _write_livespec_jsonc(
        root=tmp_path, body='{ "harnesses": { "codex": { "status": "supported" } } }'
    )
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "canonical_command" in load.detail


def test_load_harnesses_malformed_exempt_missing_reason(*, tmp_path: Path) -> None:
    """An `exempt` harness with no `reason` → MALFORMED."""
    _write_livespec_jsonc(
        root=tmp_path, body='{ "harnesses": { "claude": { "status": "exempt" } } }'
    )
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "malformed"
    assert "reason" in load.detail


def test_load_harnesses_ok_supported_and_exempt(*, tmp_path: Path) -> None:
    """A well-formed declaration with a supported + an exempt harness → OK."""
    _write_livespec_jsonc(root=tmp_path, body=_VALID_SUPPORTED_AND_EXEMPT)
    load = plugin_resolution.load_harnesses(root=tmp_path)
    assert load.state == "ok"
    by_name = {decl.harness: decl for decl in load.declarations}
    assert by_name["codex"].status == "supported"
    assert by_name["codex"].canonical_command == "livespec:next"
    assert by_name["claude"].status == "exempt"
    assert by_name["claude"].reason


# ---------------------------------------------------------------------------
# Live layer runner — CliResolutionRunner (reuses the cli_e2e CliRunner seam).
# ---------------------------------------------------------------------------


def test_cli_resolution_runner_skips_when_binary_unavailable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable harness binary → available=False (SKIP), runner never invoked (mjnv)."""
    monkeypatch.setattr(shutil, "which", _which_none)
    fake = _ResolvingCliRunner()
    runner = plugin_resolution.CliResolutionRunner(cli_runner=fake)
    outcome = runner.resolve(harness="claude", canonical_command="livespec:next")
    assert outcome.available is False
    assert outcome.resolved is False
    assert fake.recorded == []


def test_cli_resolution_runner_claude_issues_slash_command(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An available claude binary resolves via the `/`-prefixed slash command surface."""
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _ResolvingCliRunner()
    runner = plugin_resolution.CliResolutionRunner(cli_runner=fake)
    outcome = runner.resolve(harness="claude", canonical_command="livespec:next")
    assert outcome.available is True
    assert outcome.resolved is True
    assert fake.recorded == ["/livespec:next"]


def test_cli_resolution_runner_codex_name_selects(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """An available codex binary resolves via the name-selected command (no leading slash)."""
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _ResolvingCliRunner()
    runner = plugin_resolution.CliResolutionRunner(cli_runner=fake)
    outcome = runner.resolve(harness="codex", canonical_command="livespec:next")
    assert outcome.resolved is True
    assert fake.recorded == ["livespec:next"]


def test_cli_resolution_runner_unresolved_on_nonzero_exit(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An available binary whose slash command returns non-zero → resolved=False."""
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _FakeCliRunner()
    runner = plugin_resolution.CliResolutionRunner(cli_runner=fake)
    outcome = runner.resolve(harness="claude", canonical_command="livespec:next")
    assert outcome.available is True
    assert outcome.resolved is False


# ---------------------------------------------------------------------------
# main() — both layers wired (declaration gate + env-gated live smoke).
# ---------------------------------------------------------------------------


def test_main_skips_when_no_livespec_jsonc(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `.livespec.jsonc` at all → exit 0 (non-governed dir; the gate is a no-op)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    assert plugin_resolution.main() == 0


def test_main_fails_when_harnesses_key_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `.livespec.jsonc` present but WITHOUT a `harnesses` key → exit 4 (required since M6)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    _write_livespec_jsonc(root=tmp_path, body='{ "template": "livespec" }')
    assert plugin_resolution.main() == 4


def test_main_fails_on_malformed_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed `harnesses` declaration → exit 4 (fail-closed declaration-integrity gate)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    _write_livespec_jsonc(
        root=tmp_path, body='{ "harnesses": { "claude": { "status": "maybe" } } }'
    )
    assert plugin_resolution.main() == 4


def test_main_passes_declaration_gate_in_mock_mode(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed declaration in `mock` mode → exit 0; the live layer does NOT run."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "mock")
    _write_livespec_jsonc(root=tmp_path, body=_VALID_SUPPORTED_AND_EXEMPT)
    assert plugin_resolution.main() == 0


def test_main_real_mode_skips_unavailable_binary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`real` mode + unavailable claude binary → SKIP, exit 0 (mjnv; via the real RealCliRunner wiring)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    monkeypatch.setattr(shutil, "which", _which_none)
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "claude": { "status": "supported", "canonical_command": "livespec:next" } } }',
    )
    assert plugin_resolution.main() == 0


def test_main_real_mode_codex_delegated_to_repo_local_smoke(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`real` mode + a `supported` codex harness whose binary IS available → SKIP (delegated), exit 0.

    codex's genuine live resolution smoke is the repo-local `check-codex-skill-picker`,
    NOT this dev-tooling cross-harness live layer (whose `CliResolutionRunner` shells the
    `claude` binary). So a `supported` codex harness must be routed to a delegated runner
    and SKIP — the claude-backed runner must NEVER be invoked for codex (which would
    mis-route `livespec:next` through `claude -p`). The empty `fake.recorded` is the
    anti-mis-route assertion.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _ResolvingCliRunner()
    monkeypatch.setattr(plugin_resolution, "select_runner", _runner_factory(fake))
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "codex": { "status": "supported", "canonical_command": "livespec:next" } } }',
    )
    assert plugin_resolution.main() == 0
    assert fake.recorded == []


def test_main_real_mode_passes_when_command_resolves(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`real` mode + available binary + canonical command resolves → exit 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _ResolvingCliRunner()
    monkeypatch.setattr(plugin_resolution, "select_runner", _runner_factory(fake))
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "claude": { "status": "supported", "canonical_command": "livespec:next" } } }',
    )
    assert plugin_resolution.main() == 0
    assert fake.recorded == ["/livespec:next"]


def test_main_real_mode_exempt_harness_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`real` mode + a declared-exempt harness → exit 0 (the Exemption slot; no smoke run)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    fake = _ResolvingCliRunner()
    monkeypatch.setattr(plugin_resolution, "select_runner", _runner_factory(fake))
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "codex": { "status": "exempt", "reason": "codex surface not shipped here" } } }',
    )
    assert plugin_resolution.main() == 0
    assert fake.recorded == []


def test_ob4ts_proof_main_fails_when_slash_unresolved(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ob-4ts proof: a fake whose raw `bd` fallback works but whose `/livespec:*` slash
    command does NOT resolve drives the check to FAIL (exit 4).

    The Verifier only ever issues the slash command (recorded `/livespec:next`), never a
    raw `bd` substitute — so the tolerated raw-CLI fallback that let ob-4ts ship "done" is
    rejected as proof of resolution.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    monkeypatch.setattr(shutil, "which", _which_path)
    fake = _FakeCliRunner(raw_fallback_exit=0, slash_exit=1)
    monkeypatch.setattr(plugin_resolution, "select_runner", _runner_factory(fake))
    _write_livespec_jsonc(
        root=tmp_path,
        body='{ "harnesses": { "claude": { "status": "supported", "canonical_command": "livespec:next" } } }',
    )
    assert plugin_resolution.main() == 4
    assert fake.recorded == ["/livespec:next"]
    assert all(not prompt.startswith("bd") for prompt in fake.recorded)
