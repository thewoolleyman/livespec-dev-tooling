#!/usr/bin/env bash
# check-no-workflow-edits.sh — the fleet's ONE workflow-edit guard.
#
# WHAT THIS IS
# ============
# The seventh member of the livespec worktree-discipline pack: a single,
# byte-identical body installed into every governed repo's `dev-tooling/`
# by `livespec_dev_tooling.install_worktree_pack` and byte-verified by the
# `primary_checkout_commit_refuse_hook_installed` worktree-pack arm. It
# replaces the eight hand-rolled per-repo copies of the same rule
# (livespec-dev-tooling-fy02), three of which carried an agent-settable
# escape. This body carries NONE: there is no environment variable, flag,
# or mechanical allowance that changes what it does.
#
# THE RULE (maintainer, 2026-09-04): the factory MUST NOT land changes to
# `.github/workflows/` autonomously. An agent may INVOKE the human
# authorization override below but cannot FABRICATE it.
#
# WHAT THIS IS NOT
# ================
# This is an AUTHORSHIP control at the agent boundary — it runs locally
# (pre-push via the `check` aggregate) and in the Dispatcher's janitor gate.
# It is NOT a master-safety gate: master is protected by PR gate ≡ master
# gate (livespec spec v217), which this guard neither weakens nor
# strengthens. It deliberately does NOT run in CI (see venue below): CI has
# no local author to control, and the fleet's bot lanes (pin bumps, the
# canonical-slug reconciler, release-please) legitimately rewrite workflow
# files there.
#
# BEHAVIOUR
# =========
#   1. Venue.   `GITHUB_ACTIONS` set → note + exit 0. Not a CI venue.
#   2. Base.    `refs/remotes/origin/HEAD` via symbolic-ref; else
#               `origin/master`; else `origin/main`; else note + exit 0
#               (nothing to compare against).
#   3. Scope.   The union of `.github/workflows/` paths changed in
#               <base>...HEAD, staged, unstaged, and untracked. Empty →
#               exit 0, silently.
#   4. Override. A workflow edit is allowed ONLY under human authorization:
#        (a) a TRACKED declaration `.livespec-workflow-edit-exemption`
#            AUTHORED IN THIS CHANGE (present in <base>...HEAD or pending),
#            carrying exactly one `work_item=<ledger-id>` line and exactly
#            one non-empty `reason=` line — livespec-overseer's rules,
#            verbatim. A declaration inherited from the base is NOT an
#            authorization: one exemption binds to one reviewed change.
#        (b) when the repo has a ledger (`.beads/config.yaml` present), the
#            named work item MUST carry the label `approval:workflow-edit`,
#            read via `bd show <id> --json` (`LIVESPEC_BD_PATH` if set and
#            executable, else `bd` on PATH). A HUMAN sets that label from
#            their own terminal; the fleet footgun hook denies it to
#            agents. An unreachable ledger FAILS CLOSED.
#        (c) a repo with NO ledger accepts the valid declaration alone, and
#            says so.
#   5. No environment variable of any kind changes any of the above.
#
# EXIT CODES
# ==========
#   0  pass (no workflow edit, or a workflow edit under valid human
#      authorization, or not a venue for this guard)
#   1  a workflow edit without valid human authorization
#   2  the authorization could not be EVALUATED: the ledger is unreachable
#      (`bd` absent, failing, or emitting unparseable JSON) or the
#      declaration is malformed — fail closed, naming the cause
#
# USAGE
# =====
#   bash dev-tooling/check-no-workflow-edits.sh
#   (every consumer's `check-no-workflow-edits` recipe is exactly that line,
#   and the recipe is a member of the consumer's `check` targets array)

set -euo pipefail

declaration=".livespec-workflow-edit-exemption"
workflows_dir=".github/workflows"
approval_label="approval:workflow-edit"
ledger_config=".beads/config.yaml"
guard="check-no-workflow-edits"

note() {
    printf '%s: %s\n' "$guard" "$*" >&2
}

# --------------------------------------------------------------------------
# 1. Venue
# --------------------------------------------------------------------------
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    note "local/janitor authorship control at the agent boundary; not a CI venue (GITHUB_ACTIONS is set) — nothing to check here"
    exit 0
fi

# Every path below is repo-root-relative; run from the work-tree root so a
# recipe invoked from a subdirectory sees the same scope.
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# --------------------------------------------------------------------------
# 2. Base ref — the shared default-branch resolution rule, no override
# --------------------------------------------------------------------------
resolve_base_ref() {
    local origin_head candidate
    if origin_head="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)"; then
        printf '%s\n' "${origin_head#refs/remotes/}"
        return 0
    fi
    for candidate in origin/master origin/main; do
        if git rev-parse --verify --quiet "$candidate" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if ! base="$(resolve_base_ref)"; then
    note "no base to compare against (no refs/remotes/origin/HEAD, origin/master, or origin/main) — nothing to check"
    exit 0
fi

# --------------------------------------------------------------------------
# 3. Scope — committed, staged, unstaged, and untracked workflow paths
# --------------------------------------------------------------------------
workflow_paths="$(
    {
        git diff --name-only "${base}...HEAD" -- "$workflows_dir"
        git diff --name-only --cached -- "$workflows_dir"
        git diff --name-only -- "$workflows_dir"
        git ls-files --others --exclude-standard -- "$workflows_dir"
    } | sed '/^$/d' | sort -u
)"

if [[ -z "$workflow_paths" ]]; then
    exit 0
fi

# --------------------------------------------------------------------------
# 4a. The declaration — livespec-overseer's rules, verbatim
# --------------------------------------------------------------------------
# Returns 0 with the value on stdout when `key=` appears EXACTLY once.
declared_value() {
    local key="$1" lines
    lines="$(grep -E "^${key}=" "$declaration" || true)"
    if [[ "$(printf '%s\n' "$lines" | sed '/^$/d' | wc -l | tr -d ' ')" != "1" ]]; then
        return 1
    fi
    printf '%s\n' "${lines#*=}"
}

# Sets `declaration_status` to one of:
#   absent     — no declaration authored in this change (exit 1 territory)
#   malformed  — a declaration is here but cannot be evaluated (exit 2)
#   valid      — sets `work_item`
declaration_status=""
work_item=""
inspect_declaration() {
    if [[ ! -f "$declaration" ]]; then
        note "missing workflow-edit exemption declaration: $declaration"
        declaration_status="absent"
        return 0
    fi
    if ! git ls-files --error-unmatch "$declaration" >/dev/null 2>&1; then
        note "workflow-edit exemption declaration must be tracked (git add it): $declaration"
        declaration_status="absent"
        return 0
    fi
    # The declaration must be authored BY THIS CHANGE, not inherited from the
    # base. A declaration lands on the base alongside the workflow edit it
    # exempted, so a file-existence test would let that first legitimate use
    # disable the guard permanently. Requiring it in this branch's own diff
    # (or staged/unstaged, for the pre-commit moment) keeps one exemption
    # bound to one reviewed change.
    local declared_here declared_pending
    declared_here="$(git diff --name-only "${base}...HEAD" -- "$declaration")"
    declared_pending="$(git status --short -- "$declaration")"
    if [[ -z "$declared_here" && -z "$declared_pending" ]]; then
        note "workflow-edit exemption declaration is inherited from $base, not authored by this change"
        note "an exemption is per-change: add or update $declaration in this branch"
        declaration_status="absent"
        return 0
    fi

    local reason
    if ! work_item="$(declared_value "work_item")"; then
        note "malformed declaration: $declaration must contain exactly one work_item= line"
        declaration_status="malformed"
        return 0
    fi
    if ! reason="$(declared_value "reason")"; then
        note "malformed declaration: $declaration must contain exactly one reason= line"
        declaration_status="malformed"
        return 0
    fi
    if [[ ! "$work_item" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
        note "malformed declaration: work_item must be a single ledger id token, got '$work_item'"
        declaration_status="malformed"
        return 0
    fi
    if [[ -z "$reason" ]]; then
        note "malformed declaration: reason= must be non-empty"
        declaration_status="malformed"
        return 0
    fi
    declaration_status="valid"
}

print_offending_paths() {
    {
        echo "$guard: changes under $workflows_dir/ require HUMAN authorization:"
        printf '%s\n' "$workflow_paths" | sed 's/^/  /'
    } >&2
}

print_human_procedure() {
    {
        echo "$guard: the two-step human-authorization path:"
        echo "  1. add or update $declaration in THIS branch (tracked), with exactly one"
        echo "     work_item=<ledger-id> line and exactly one reason=<reviewable reason> line;"
        echo "  2. have a HUMAN set the approval label on that work item from their own terminal:"
        echo "       bd label add <ledger-id> $approval_label"
        echo "     (agents cannot set it; the fleet footgun hook denies them that command)."
        echo "  No environment variable or flag bypasses this guard."
    } >&2
}

inspect_declaration
case "$declaration_status" in
    absent)
        print_offending_paths
        print_human_procedure
        exit 1
        ;;
    malformed)
        print_offending_paths
        print_human_procedure
        note "fix the declaration and re-run"
        exit 2
        ;;
    valid) ;;
esac

# --------------------------------------------------------------------------
# 4c. No ledger — the declaration alone authorizes, and we say so
# --------------------------------------------------------------------------
if [[ ! -f "$ledger_config" ]]; then
    note "this repository has no ledger ($ledger_config absent): accepting the tracked declaration alone (work_item=$work_item) as the human authorization"
    exit 0
fi

# --------------------------------------------------------------------------
# 4b. Ledger — the named work item must carry the approval label
# --------------------------------------------------------------------------
wrapper_hint="run under the project's credential wrapper so BEADS_DOLT_PASSWORD is present"

fail_closed() {
    note "$*"
    note "the ledger-held authorization could not be evaluated — FAILING CLOSED; $wrapper_hint"
    exit 2
}

resolve_bd() {
    if [[ -n "${LIVESPEC_BD_PATH:-}" && -x "${LIVESPEC_BD_PATH}" ]]; then
        printf '%s\n' "$LIVESPEC_BD_PATH"
        return 0
    fi
    command -v bd 2>/dev/null
}

if ! bd_bin="$(resolve_bd)"; then
    fail_closed "no usable bd binary (LIVESPEC_BD_PATH unset or not executable, and no bd on PATH)"
fi
if ! command -v python3 >/dev/null 2>&1; then
    fail_closed "python3 is required to read the ledger record and is not on PATH"
fi

bd_stderr="$(mktemp)"
trap 'rm -f "$bd_stderr"' EXIT
if ! bd_json="$("$bd_bin" show "$work_item" --json 2>"$bd_stderr")"; then
    fail_closed "bd show $work_item --json failed via $bd_bin: $(tr '\n' ' ' <"$bd_stderr")"
fi

# The record may arrive as a bare object, a list of records, or an envelope
# with a `data` key, possibly behind a non-JSON preamble — the same shapes
# `checks/_plan_ledger.py` tolerates. Exit 0 when the label is present, 1
# when it is absent, 3 when the output cannot be read as a ledger record.
label_probe='
import json
import sys

wanted = sys.argv[1]
text = sys.stdin.read()
starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
if not starts:
    sys.exit(3)
try:
    parsed = json.loads(text[min(starts):])
except ValueError:
    sys.exit(3)
if isinstance(parsed, dict) and "data" in parsed:
    parsed = parsed["data"]
if isinstance(parsed, list):
    parsed = parsed[0] if parsed else None
if not isinstance(parsed, dict):
    sys.exit(3)
labels = parsed.get("labels") or []
if not isinstance(labels, list):
    sys.exit(3)
sys.exit(0 if wanted in labels else 1)
'

set +e
printf '%s' "$bd_json" | python3 -c "$label_probe" "$approval_label"
probe_status=$?
set -e

case "$probe_status" in
    0)
        note "workflow edit authorized: $work_item carries $approval_label (declaration: $declaration)"
        exit 0
        ;;
    1)
        print_offending_paths
        note "the declared work item $work_item does NOT carry the label $approval_label"
        note "a human must run, from their own terminal:  bd label add $work_item $approval_label"
        print_human_procedure
        exit 1
        ;;
    *)
        fail_closed "bd show $work_item --json via $bd_bin returned output that is not a ledger record"
        ;;
esac
