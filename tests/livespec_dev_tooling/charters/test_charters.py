"""Tests for the importable charter-defect detector surface."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol, cast

import pytest
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs
from livespec_dev_tooling.charters.charters import CharterReadFailure

EXPECTED_CANONICAL_SLUGS: tuple[str, ...] = (
    "check-agents-ai-references-resolve",
    "check-aggregate-completeness",
    "check-all-declared",
    "check-assert-never-exhaustiveness",
    "check-branch-protection-alignment",
    "check-canonical-recipe-fidelity",
    "check-check-coverage-incremental",
    "check-check-mutation",
    "check-check-tools",
    "check-ci-matrix-completeness",
    "check-claude-md-coverage",
    "check-comment-line-anchors",
    "check-commit-pairs-source-and-test",
    "check-file-lloc",
    "check-fleet-marketplace-relative-sources",
    "check-global-writes",
    "check-handoff-dispatch-routing",
    "check-heading-coverage",
    "check-hook-trees-not-io-exempt",
    "check-keyword-only-args",
    "check-local-memory-drift-audit",
    "check-main-guard",
    "check-master-ci-green",
    "check-match-keyword-only",
    "check-newtype-domain-primitives",
    "check-no-direct-destructive-cli",
    "check-no-direct-tool-invocation",
    "check-no-except-outside-io",
    "check-no-fmt-directives",
    "check-no-inheritance",
    "check-no-lloc-soft-warnings",
    "check-no-raise-outside-io",
    "check-no-shadow-ledger-body-identical",
    "check-no-shadow-ledger-body-typechecks",
    "check-no-todo-registry",
    "check-no-write-direct",
    "check-partition-completeness",
    "check-pbt-coverage-pure-modules",
    "check-per-file-coverage",
    "check-plan-anchor-declared",
    "check-plan-epic-parity",
    "check-plan-no-tombstone",
    "check-plugin-resolution",
    "check-primary-checkout-commit-refuse-hook-installed",
    "check-private-calls",
    "check-public-api-result-typed",
    "check-red-green-replay",
    "check-required-role-keys-declared",
    "check-rop-pipeline-shape",
    "check-self-hosted-routing",
    "check-self-hosted-uv-lane",
    "check-shell-quality",
    "check-skill-invocation-paths",
    "check-source-trees-scoped-to-consumer",
    "check-supervisor-discipline",
    "check-tests-mirror-pairing",
    "check-tests-no-subprocess-spawn",
    "check-tool-backed-check-completeness",
    "check-vendor-manifest",
    "check-wrapper-shape",
)


class Detector(Protocol):
    def __call__(self, *, text: str) -> list[str]: ...


class CharterModule(Protocol):
    CHARTER_GLOBS: tuple[str, ...]
    DETECTORS: tuple[tuple[str, Detector], ...]

    def defects_in(self, *, text: str) -> list[str]: ...

    def charters_in(self, *, root: Path) -> IOResult[list[Path], CharterReadFailure]: ...


def _charters_module() -> CharterModule:
    module_path = Path("livespec_dev_tooling") / "charters" / "__init__.py"
    assert module_path.is_file()
    return cast("CharterModule", importlib.import_module("livespec_dev_tooling.charters"))


def _defects_in(*, text: str) -> list[str]:
    return _charters_module().defects_in(text=text)


def _fenced(*, body: str) -> str:
    return "```sh\n" + body + "\n```"


def test_charters_package_does_not_extend_canonical_check_slugs() -> None:
    assert (Path("livespec_dev_tooling") / "checks" / "charters.py").exists() is False
    assert unsafe_perform_io(canonical_check_slugs().unwrap()) == EXPECTED_CANONICAL_SLUGS


def test_public_surface_exports_detectors_globs_and_entry_points() -> None:
    module = _charters_module()
    assert module.CHARTER_GLOBS == (
        ".ai/supervisor-protocol.md",
        "plan/**/supervisor-handoff.md",
    )
    assert [name for name, _detector in module.DETECTORS] == [
        "a-bare-tmux-target",
        "b-unguarded-path-resolution",
        "c-history-fed-capture",
        "d-empty-prev-watcher-init",
        "e-supervisor-trusted-by-name",
        "f-regex-session-existence-test",
        "g-bash-pipestatus-under-zsh",
        "h-wrapper-less-ledger-read",
        "i-fixed-cap-marker-read",
        "j-unguarded-marker-binding",
        "k-local-time-labelled-utc",
        "l-busy-test-matches-idle-pane",
        "m-adoptable-runtime-contract",
        "n-unattended-charter-missing-perform-the-unblock",
    ]
    assert callable(module.defects_in)
    assert callable(module.charters_in)


def test_charters_in_uses_the_parameterized_root_and_declared_globs(tmp_path: Path) -> None:
    module = _charters_module()
    protocol = tmp_path / ".ai" / "supervisor-protocol.md"
    active = tmp_path / "plan" / "active" / "supervisor-handoff.md"
    active_epic = tmp_path / "plan" / "active" / "epic.md"
    archived = tmp_path / "plan" / "archive" / "done" / "supervisor-handoff.md"
    archived_epic = tmp_path / "plan" / "archive" / "done" / "epic.md"
    nested = tmp_path / "plan" / "archive" / "done" / "nested" / "supervisor-handoff.md"
    nested_epic = tmp_path / "plan" / "archive" / "done" / "nested" / "epic.md"
    for path in (protocol, active, active_epic, archived, archived_epic, nested, nested_epic):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("charter\n", encoding="utf-8")

    assert [
        path.relative_to(tmp_path).as_posix()
        for path in unsafe_perform_io(module.charters_in(root=tmp_path).unwrap())
    ] == [
        ".ai/supervisor-protocol.md",
        "plan/active/supervisor-handoff.md",
        "plan/archive/done/supervisor-handoff.md",
        "plan/archive/done/nested/supervisor-handoff.md",
    ]


def test_detectors_read_fenced_code_only_and_ignore_commented_defects() -> None:
    prose = """
Describe `tmux send-keys -t my-session`, `readlink -f "$pane_cwd"`, prev="",
`tmux capture-pane -p -S -40 | grep -qE select`, and `${PIPESTATUS[0]}` in prose.
The bare ledger hazard is `bd show "$ledger_anchor" --json`.
"""
    comments = _fenced(
        body=(
            "# tmux send-keys -t my-session -- 'do not do this'\n"
            '# readlink -f "$pane_cwd"\n'
            '# prev=""\n'
            "# pane=$(tmux capture-pane -p -t my-session -S -40)\n"
            '# bd show "$ledger_anchor" --json\n'
            "# date -u -r \"$f\" '+%FT%TZ'"
        )
    )
    assert _defects_in(text=prose) == []
    assert _defects_in(text=comments) == []


def test_detector_a_flags_only_bare_tmux_targets() -> None:
    bad = _fenced(body="tmux send-keys -t my-session -- 'echo hi'")
    good = _fenced(
        body=(
            "WORKER_TARGET='=my-session:'   # trailing colon REQUIRED\n"
            "tmux has-session -t '=my-session:'\n"
            "tmux send-keys -t \"$WORKER_TARGET\" -- 'echo hi'\n"
            'tmux capture-pane -p -t "${WORKER_TARGET}"'
        )
    )
    assert _defects_in(text=bad) == [
        "a-bare-tmux-target: tmux send-keys -t my-session -- 'echo hi'"
    ]
    assert _defects_in(text=good) == []


def test_detector_b_flags_path_resolution_without_a_nonempty_guard() -> None:
    unguarded = _fenced(
        body=(
            "pane_cwd=$(tmux display-message -p -t '=my-session:' '#{pane_current_path}')\n"
            'case "$(realpath -- "$pane_cwd")" in /data/projects/demo) ;; esac'
        )
    )
    guarded = _fenced(
        body=(
            "pane_cwd=$(tmux display-message -p -t '=my-session:' '#{pane_current_path}')\n"
            '[ -n "$pane_cwd" ] || { echo "HALT"; exit 1; }\n'
            'case "$(readlink -f -- "$pane_cwd")" in /data/projects/demo) ;; esac'
        )
    )
    assert [defect for defect in _defects_in(text=unguarded) if defect.startswith("b-")] == [
        "b-unguarded-path-resolution: "
        'case "$(realpath -- "$pane_cwd")" in /data/projects/demo) ;; esac'
    ]
    assert [defect for defect in _defects_in(text=guarded) if defect.startswith("b-")] == []


def test_detector_c_flags_history_fed_capture_but_not_bounded_inspection() -> None:
    bound = _fenced(body="pane=$(tmux capture-pane -p -t '=my-session:' -S -40)")
    inspection = _fenced(
        body=(
            "tmux capture-pane -p -t '=my-session:' -S -40\n"
            "pane=$(tmux capture-pane -p -t '=my-session:')"
        )
    )
    assert [defect for defect in _defects_in(text=bound) if defect.startswith("c-")] == [
        "c-history-fed-capture: pane=$(tmux capture-pane -p -t '=my-session:' -S -40)"
    ]
    assert [defect for defect in _defects_in(text=inspection) if defect.startswith("c-")] == []


def test_detector_d_does_not_flag_a_capture_free_search_accumulator() -> None:
    """An empty-seeded ACCUMULATOR compared for identity is not a watcher.

    THE THREE-WAY CONTROL this repo's charter-gate rule demands, run against a
    real charter rather than an invented one: `homelab`'s generator-provenance
    block seeds `matched_ref=''`, sets it on a digest match, tests it with
    `[ -z ... ]` to mean NOT-FOUND, and finally compares it for identity to
    report which ref matched. No watcher, no capture, no stability semantics.

    The property rule keyed on ANY `[ "$a" = "$b" ]`, so it read that identity
    comparison as a stability comparison and flagged correct code — the FOURTH
    false positive from this gate, all four flagging code already correct.

    THE IMPLIED REMEDY IS WORSE THAN THE FINDING, which is why this is a test
    and not a comment: the detector accepts a sentinel seed, so a session under
    adoption pressure "fixes" the charter by seeding one — and that BREAKS it,
    because the block's not-found test is an EMPTINESS test. A sentinel makes it
    never fire, so a missing generator would silently report as found.

    The discriminator is that a stability comparison reads a CAPTURE. The rule's
    own subject is "the variable the stability comparison treats as the PREVIOUS
    capture", so a comparison no capture feeds was never in scope.
    """
    accumulator = _fenced(
        body=(
            "matched_ref=''\n"
            '[ "$installed_md5" = "$recorded_md5" ] && matched_ref="$generator_ref"\n'
            'if [ -z "$matched_ref" ]; then echo none; fi\n'
            'if [ "$matched_ref" = "$generator_ref" ]; then echo exact; fi'
        )
    )
    watcher = _fenced(
        body=(
            "last_seen=''\n"
            "for i in $(seq 1 180); do\n"
            "  pane=$(tmux capture-pane -p -t '=demo:')\n"
            '  if [ "$pane" = "$last_seen" ]; then stable=$((stable+1)); fi\n'
            '  last_seen="$pane"\n'
            "done"
        )
    )

    assert [defect for defect in _defects_in(text=accumulator) if defect.startswith("d-")] == []
    assert [defect for defect in _defects_in(text=watcher) if defect.startswith("d-")] == [
        "d-empty-prev-watcher-init: last_seen=''"
    ]


def test_detector_d_keeps_literal_and_property_empty_seed_rules() -> None:
    watcher = (
        "{seed}\n"
        "for i in $(seq 1 180); do\n"
        "  pane=$(tmux capture-pane -p -t '=demo:')\n"
        '  if [ "$pane" = "{var}" ]; then stable=$((stable+1)); else stable=0; {var}="$pane"; fi\n'
        "done"
    )
    previous = _fenced(body=watcher.format(seed='previous=""; stable=0', var="$previous"))
    sentinel = _fenced(
        body=watcher.format(seed='previous="__NO_CAPTURE_YET__"; stable=0', var="$previous")
    )
    assert [defect for defect in _defects_in(text=previous) if defect.startswith("d-")] == [
        'd-empty-prev-watcher-init: previous=""; stable=0'
    ]
    assert [
        defect
        for defect in _defects_in(text=_fenced(body='prev=""; stable=0'))
        if defect.startswith("d-")
    ] == ['d-empty-prev-watcher-init: prev=""; stable=0']
    assert [defect for defect in _defects_in(text=sentinel) if defect.startswith("d-")] == []


def test_detectors_e_and_f_discriminate_supervisor_existence_from_liveness() -> None:
    existence = _fenced(
        body="tmux list-sessions -F '#{session_name}' | grep -Fqx 'demo-supervisor'"
    )
    regex = _fenced(body="tmux list-sessions -F '#{session_name}' | grep -qx 'demo-supervisor'")
    proof = _fenced(
        body=(
            "WORKER_TARGET='=demo:'\n"
            "SUPERVISOR_TARGET='=demo-supervisor:'\n"
            'tmux has-session -t "$SUPERVISOR_TARGET"\n'
            "supervisor_pane_pid=$(tmux display-message -p -t \"$SUPERVISOR_TARGET\" '#{pane_pid}')\n"
            '[ -n "$supervisor_pane_pid" ] || { echo "HALT"; exit 1; }\n'
            '[ "$supervisor_pane_pid" != "$pane_pid" ] || { echo "HALT"; exit 1; }\n'
            'ps -o pid=,comm=,args= --ppid "$supervisor_pane_pid" --pid "$supervisor_pane_pid" -H'
        )
    )
    assert [defect for defect in _defects_in(text=existence) if defect.startswith("e-")] == [
        "e-supervisor-trusted-by-name: supervisor existence checked but liveness never proven"
    ]
    assert [defect for defect in _defects_in(text=regex) if defect.startswith("f-")] == [
        "f-regex-session-existence-test: "
        "tmux list-sessions -F '#{session_name}' | grep -qx 'demo-supervisor'"
    ]
    assert _defects_in(text=proof) == []


def test_detector_g_flags_bash_pipestatus_under_zsh() -> None:
    bad = _fenced(body='just check | tail -5; echo "EXIT=${PIPESTATUS[0]}"')
    good = _fenced(body='just check | tail -5; echo "EXIT=$pipestatus[1]"')
    assert [defect for defect in _defects_in(text=bad) if defect.startswith("g-")] == [
        'g-bash-pipestatus-under-zsh: just check | tail -5; echo "EXIT=${PIPESTATUS[0]}"'
    ]
    assert [defect for defect in _defects_in(text=good) if defect.startswith("g-")] == []


def test_detector_h_accepts_wrapper_properties_and_line_continuations() -> None:
    bare = _fenced(body='bd show "$ledger_anchor" --json')
    dangling_bare = _fenced(body='bd show "$ledger_anchor" --json \\')
    direct = _fenced(body="/usr/local/bin/with-homelab-env.sh -- bd show homelab-123 --json")
    variable = _fenced(
        body=(
            'wrapper="with-livespec-env.sh"\n'
            'if command -v "$wrapper" >/dev/null 2>&1; then\n'
            '  "$wrapper" -- bd show "$1" --json\n'
            "fi"
        )
    )
    continued = _fenced(
        body="with-livespec-env.sh -- \\\n  bd show livespec-dev-tooling-8sc1 --json"
    )
    fallback = _fenced(
        body=(
            "if command -v with-livespec-env.sh >/dev/null 2>&1; then\n"
            '  with-livespec-env.sh -- bd show "$1" --json\n'
            "else\n"
            '  bd show "$1" --json\n'
            "fi"
        )
    )
    assert [defect for defect in _defects_in(text=bare) if defect.startswith("h-")] == [
        'h-wrapper-less-ledger-read: bd show "$ledger_anchor" --json'
    ]
    assert [defect for defect in _defects_in(text=dangling_bare) if defect.startswith("h-")] == [
        'h-wrapper-less-ledger-read: bd show "$ledger_anchor" --json \\'
    ]
    assert [defect for defect in _defects_in(text=direct) if defect.startswith("h-")] == []
    assert [defect for defect in _defects_in(text=variable) if defect.startswith("h-")] == []
    assert [defect for defect in _defects_in(text=continued) if defect.startswith("h-")] == []
    assert [defect for defect in _defects_in(text=fallback) if defect.startswith("h-")] == []


def test_detectors_i_and_j_discriminate_marker_reads() -> None:
    cap = _fenced(body='test ! -f "$supervisor_marker" || sed -n "1,220p" "$supervisor_marker"')
    announced = _fenced(
        body=(
            '[ -n "${supervisor_marker:-}" ] || { echo "HALT: unset"; exit 1; }\n'
            'sed -n "1,160p" "$supervisor_marker"\n'
            "printf 'TRUNCATED: lines 161 onward NOT SHOWN\\n'"
        )
    )
    unguarded = _fenced(body='test ! -f "$supervisor_marker" || cat "$supervisor_marker"')
    guarded = _fenced(
        body=(
            '[ -n "${supervisor_marker:-}" ] || { echo "HALT: unset"; exit 1; }\n'
            'test ! -f "$supervisor_marker" || cat "$supervisor_marker"'
        )
    )
    assert [defect for defect in _defects_in(text=cap) if defect.startswith("i-")] != []
    assert [defect for defect in _defects_in(text=announced) if defect.startswith("i-")] == []
    assert [defect for defect in _defects_in(text=unguarded) if defect.startswith("j-")] != []
    assert [defect for defect in _defects_in(text=guarded) if defect.startswith("j-")] == []


def test_detector_k_flags_file_mtime_labelled_utc_only() -> None:
    bad = _fenced(
        body=(
            "a=$(date -r \"$f\" -u '+%FT%TZ')\n"
            "b=$(date -ur \"$f\" '+%FT%TZ')\n"
            "c=$(date --utc --reference=\"$f\" '+%FT%TZ')\n"
            "d=$(date -r \"$f\" '+%Y-%m-%dT%H:%M:%SZ')"
        )
    )
    good = _fenced(
        body=(
            'mtime_epoch=$(stat -c %Y "$supervisor_marker")\n'
            "worker_state_at=$(date -u -d @\"$mtime_epoch\" '+%Y-%m-%dT%H:%M:%SZ')\n"
            "printf 'marker last written: %s\\n' \"$(date -r \"$supervisor_marker\" '+%H:%M %Z')\""
        )
    )
    assert len([defect for defect in _defects_in(text=bad) if defect.startswith("k-")]) == 4
    assert [defect for defect in _defects_in(text=good) if defect.startswith("k-")] == []


def test_detector_l_separates_historical_and_corrected_busy_tests() -> None:
    historical = _fenced(
        body=(
            "pane=$(tmux capture-pane -p -t '=w:' -S -40)\n"
            "busy=0\n"
            "printf '%s\\n' \"$pane\" | tail -6 \\\n"
            "  | grep -qE '[0-9]+[hms] |tokens|esc to interrupt|Running|Doing|monitor' && busy=1"
        )
    )
    corrected = _fenced(
        body=(
            "busy=0\n"
            "printf '%s\\n' \"$tail16\" | grep -vE '^[[:space:]]*>' \\\n"
            "  | grep -qE 'esc to interrupt|Running command' && busy=1\n"
            "kids=$(ps -o args= --ppid \"$pane_pid\" 2>/dev/null | grep -cv 'playwright-mcp')\n"
            '[ "${kids:-0}" -gt 0 ] && busy=1'
        )
    )
    assert [defect for defect in _defects_in(text=historical) if defect.startswith("l-")] != []
    assert [defect for defect in _defects_in(text=corrected) if defect.startswith("l-")] == []


def test_detector_l_models_shell_regex_edges() -> None:
    bre_hit = _fenced(body="busy=0\nprintf '%s' \"$p\" | grep -q 'nosuchmarker\\|tokens' && busy=1")
    bre_miss = _fenced(
        body="busy=0\nprintf '%s' \"$p\" | grep -q 'nosuchmarker|alsomissing' && busy=1"
    )
    broken = _fenced(body="busy=0\nprintf '%s' \"$p\" | grep -qE '[unclosed' && busy=1")
    inverted_only = _fenced(body="busy=0\nprintf '%s' \"$p\" | grep -vE 'Worked for' && busy=1")
    control_operator = _fenced(body="busy=0\nprintf '%s' \"$p\" | grep -qE 'tokens' || busy=1")
    assert [defect for defect in _defects_in(text=bre_hit) if defect.startswith("l-")] != []
    assert [defect for defect in _defects_in(text=bre_miss) if defect.startswith("l-")] == []
    assert [defect for defect in _defects_in(text=broken) if defect.startswith("l-")] == []
    assert [defect for defect in _defects_in(text=inverted_only) if defect.startswith("l-")] == []
    assert [
        defect for defect in _defects_in(text=control_operator) if defect.startswith("l-")
    ] != []


def test_detector_l_preserves_the_unicode_idle_pane_exemplar() -> None:
    glyphs = rb"\u276f|\u2500|\u273b|\u23bf|\u00b7".decode("unicode_escape")
    glyph_test = _fenced(body=f"busy=0\nprintf '%s' \"$p\" | grep -qE '{glyphs}' && busy=1")

    assert [defect for defect in _defects_in(text=glyph_test) if defect.startswith("l-")] != []


def test_detector_m_flags_incomplete_adoptable_runtime_contracts() -> None:
    incomplete = """
## Adoptable runtime launch and restart

Claude fresh launch: `claude --dangerously-skip-permissions`.
Claude live repair: `/rename <topic>`.
"""
    complete = """
## Adoptable runtime launch and restart

Claude fresh launch:
`claude --dangerously-skip-permissions
-n <topic>`.
Claude live repair: `/rename <topic>` only after confirming
`signals.is_structured_gate` is false.
Codex restart:
`codex resume --dangerously-bypass-approvals-and-sandbox <session-id>
"<kick>"`, recovered from `~/.codex/session_index.jsonl` by `thread_name`.
Codex fresh launch immediately uses `/rename <topic>`.
Never send `/rename` into a numbered cursor or a permission question.
A tmux session name is not an adoption key. Keep the daemon's own launch paths
unchanged; do not use fuzzy matching, tmux-name matching, live killing, or
blocking.
"""
    no_section = "Claude live repair: `/rename <topic>`."

    assert [defect for defect in _defects_in(text=incomplete) if defect.startswith("m-")] != []
    assert [defect for defect in _defects_in(text=complete) if defect.startswith("m-")] == []
    assert [defect for defect in _defects_in(text=no_section) if defect.startswith("m-")] == []


def test_detector_m_requires_structured_gate_safety() -> None:
    unsafe = """
## Adoptable runtime launch and restart

Claude fresh launch: `claude --dangerously-skip-permissions -n <topic>`.
Claude live repair: `/rename <topic>`.
Codex restart: `codex resume
--dangerously-bypass-approvals-and-sandbox <session-id> "<kick>"` by the
`thread_name` in `~/.codex/session_index.jsonl`.
Codex fresh launch immediately uses `/rename <topic>`.
A tmux session name is not an adoption key. The daemon's own launch paths are
unchanged; no fuzzy matching, tmux-name matching, live killing, or blocking.
"""

    assert [defect for defect in _defects_in(text=unsafe) if defect.startswith("m-")] != []


def test_detector_n_flags_unattended_picker_without_unblock_authority() -> None:
    missing = """
# Supervisor Protocol

Shared role-level instructions for every generated supervisor handoff.

## AskUserQuestion presentation rules

Every maintainer-facing action is an AskUserQuestion call. Put --- as the final
line before the picker.
"""
    authorized = """
# Supervisor Protocol

Shared role-level instructions for every generated supervisor handoff.

## AskUserQuestion presentation rules

Every maintainer-facing action is an AskUserQuestion call. Put --- as the final
line before the picker.

If the SUPERVISOR can perform the unblock, PERFORM IT.
"""
    interactive = """
# Interactive Plan Track

## AskUserQuestion presentation rules

Every maintainer-facing action is an AskUserQuestion call. Put --- as the final
line before the picker.
"""
    unattended_without_picker = """
# Supervisor Protocol

Shared role-level instructions for every generated supervisor handoff.
"""

    assert [defect for defect in _defects_in(text=missing) if defect.startswith("n-")] == [
        "n-unattended-charter-missing-perform-the-unblock: "
        "unattended charter presents a picker without perform-the-unblock authority"
    ]
    assert [defect for defect in _defects_in(text=authorized) if defect.startswith("n-")] == []
    assert [defect for defect in _defects_in(text=interactive) if defect.startswith("n-")] == []
    assert [
        defect for defect in _defects_in(text=unattended_without_picker) if defect.startswith("n-")
    ] == []


def test_charters_in_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """charters_in returns IOFailure when the root glob raises OSError."""
    import pathlib

    module = _charters_module()
    root = pathlib.Path("/nonexistent")

    def raise_os_error(*args: object, **kwargs: object) -> None:  # noqa: ARG001
        raise OSError("Permission denied")

    monkeypatch.setattr(pathlib.Path, "glob", raise_os_error)

    outcome = module.charters_in(root=root)
    assert isinstance(outcome, IOFailure)
    from returns.unsafe import unsafe_perform_io

    failure = unsafe_perform_io(outcome.failure())
    assert isinstance(failure, CharterReadFailure)
    assert failure.path == str(root)
    assert failure.detail == "Permission denied"


def test_defects_in_parity_with_detectors_registry() -> None:
    """Direct enumeration of detectors must match registry-based iteration.

    This test verifies that calling each detector directly produces the same
    results as iterating over DETECTORS. If the registry ever drifts from the
    direct calls in defects_in(), this will fail.
    """
    module = _charters_module()

    # Build a probe that trips at least two different detector classes
    # Based on detector_a: bare tmux target
    # Based on detector_g: bash pipestatus under zsh
    probe = _fenced(
        body=(
            "tmux send-keys -t my-session -- 'echo hi'\n"
            'just check | tail -5; echo "EXIT=${PIPESTATUS[0]}"'
        )
    )

    # The direct enumeration must match the registry iteration
    expected = [
        f"{name}: {line}" for name, detector in module.DETECTORS for line in detector(text=probe)
    ]
    assert module.defects_in(text=probe) == expected

    # Verify at least two detectors triggered
    result = module.defects_in(text=probe)
    assert len(result) >= 2
    assert any(line.startswith("a-bare-tmux-target:") for line in result)
    assert any(line.startswith("g-bash-pipestatus-under-zsh:") for line in result)
