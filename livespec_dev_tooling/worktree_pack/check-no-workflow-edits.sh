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
# THE RULE (maintainer, 2026-09-04; tiered 2026-11-02): the factory MUST NOT
# land changes to `.github/workflows/` autonomously. Every workflow edit needs
# prior authorization recorded on the ledger, in one of TWO TIERS:
#
#   ADDITIVE tier — the workflow diff is logically additive: it runs the same
#     work or more. A modification to `runs-on` routing, an `env` value, or a
#     `concurrency.group` value is permitted when the key remains present;
#     edits that can make existing work run less are not. The declaration
#     attests `change=additive` and
#     `ci_runtime=no-significant-increase`. Admitted under the label
#     `approval:workflow-edit-additive`, which the maintainer MAY delegate to a
#     coordinator agent to set (or under the maintainer label below).
#   MAINTAINER tier — everything else: any deleted or modified workflow line,
#     any edit that removes or reduces test coverage or a quality gate, any
#     edit that significantly increases CI runtime, or any declaration that
#     does not attest the additive tier. Admitted ONLY under
#     `approval:workflow-edit`, which ONLY the maintainer sets, directly. An
#     agent never sets it.
#
# A declaration that CLAIMS `change=additive` over a diff that can make
# existing work run less is refused outright, naming the offending lines —
# whatever label the item carries. An agent may INVOKE an authorization but
# cannot FABRICATE it.
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
#            verbatim — plus, for the ADDITIVE tier, at most one
#            `change=additive` line and at most one `ci_runtime=` line
#            (`no-significant-increase` attests the tier). A declaration
#            inherited from the base is NOT an authorization: one exemption
#            binds to one reviewed change.
#        (t) the tier: `change=additive` is checked against the union of the
#            committed (<merge-base>..HEAD), staged and unstaged workflow
#            diffs. A deleted workflow file or mode change refuses the claim.
#            A deleted nonblank, noncomment line is permitted only when the
#            post-image retains its `runs-on`, `concurrency.group`, or `env`
#            key path; added lines that can make work run less refuse it.
#            An attested logically additive edit is the ADDITIVE tier;
#            anything else is the MAINTAINER tier.
#        (b) when the repo has a ledger (`.beads/config.yaml` present), the
#            named work item MUST carry a label that admits the tier, read
#            via `bd show <id> --json` (`LIVESPEC_BD_PATH` if set and
#            executable, else `bd` on PATH): ADDITIVE accepts
#            `approval:workflow-edit-additive` or `approval:workflow-edit`;
#            MAINTAINER accepts `approval:workflow-edit` only. No hook stops
#            an agent from setting a label, so the labels are ADVISORY
#            authorization markers: an agent MAY set the additive label only
#            under the maintainer's prior authorization (directly, or as a
#            coordinator holding delegated authority), and never sets the
#            maintainer label. An unreachable ledger FAILS CLOSED.
#        (c) a repo with NO ledger accepts the valid declaration alone, and
#            says so (a false additive claim is still refused).
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
additive_label="approval:workflow-edit-additive"
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
# 2b. Pending base — what the pending (staged and on-disk) change is measured
#     against
# --------------------------------------------------------------------------
# Committed work is measured from the merge base of <base> and HEAD
# (`<base>...HEAD`). Pending work is measured from the merge base the NEXT
# commit will have. That is the same point, except while a merge is in progress
# (MERGE_HEAD present). The commit being prepared then has HEAD and every
# MERGE_HEAD as parents, so its merge base with <base> is the merge base of
# <base> and that hypothetical commit: `git merge-base <base> HEAD <merge heads>`.
# When the merge brings in <base> itself (a branch refresh), that point is
# <base>. Content the merge INHERITS from <base> is then identical to its
# baseline and is never counted as this change's workflow edit, while anything
# the branch itself changed still differs from it. Measuring pending work
# against HEAD instead counted every workflow file <base> had changed since the
# fork point as an edit by the branch. That refused every factory refresh-repair
# merge of a master that had moved workflow files (bd-ib-yuwftp run
# 01M6FTF5A9Y8, 2026-11-03), and it let a declaration merged in from <base> pass
# as "authored in this change".
merge_base="$(git merge-base "$base" HEAD 2>/dev/null || true)"
pending_base="$merge_base"
merge_head_file="$(git rev-parse --git-path MERGE_HEAD)"
if [[ -n "$merge_base" && -f "$merge_head_file" ]]; then
    mapfile -t merge_heads < <(sed '/^$/d' "$merge_head_file")
    if ! pending_base="$(git merge-base "$base" HEAD "${merge_heads[@]}" 2>/dev/null)"; then
        pending_base=""
    fi
fi

# The pending views: `--cached <pending_base>` is the index, `<pending_base>` the
# work tree. With no common history to measure from, they fall back to the
# index against HEAD and the work tree against the index, as before.
if [[ -n "$pending_base" ]]; then
    staged_view=(--cached "$pending_base")
    unstaged_view=("$pending_base")
else
    staged_view=(--cached)
    unstaged_view=()
fi

# --------------------------------------------------------------------------
# 3. Scope — committed, staged, unstaged, and untracked workflow paths
# --------------------------------------------------------------------------
workflow_paths="$(
    {
        git diff --name-only "${base}...HEAD" -- "$workflows_dir"
        git diff --name-only "${staged_view[@]}" -- "$workflows_dir"
        git diff --name-only "${unstaged_view[@]}" -- "$workflows_dir"
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

# Returns 0 with the value on stdout when `key=` appears AT MOST once (empty
# when absent); 1 when it appears more than once.
optional_value() {
    local key="$1" lines
    lines="$(grep -E "^${key}=" "$declaration" || true)"
    if [[ "$(printf '%s\n' "$lines" | sed '/^$/d' | wc -l | tr -d ' ')" -gt 1 ]]; then
        return 1
    fi
    printf '%s\n' "${lines#*=}"
}

# Sets `declaration_status` to one of:
#   absent     — no declaration authored in this change (exit 1 territory)
#   malformed  — a declaration is here but cannot be evaluated (exit 2)
#   valid      — sets `work_item`, `change_claim`, `ci_runtime_claim`
declaration_status=""
work_item=""
change_claim=""
ci_runtime_claim=""
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
    # Pending authorship is measured against the pending base. A declaration
    # that an in-progress merge brings in from <base> is therefore inherited,
    # not authored here.
    local declared_here declared_pending
    declared_here="$(git diff --name-only "${base}...HEAD" -- "$declaration")"
    declared_pending="$(
        {
            git diff --name-only "${staged_view[@]}" -- "$declaration"
            git diff --name-only "${unstaged_view[@]}" -- "$declaration"
        } | sed '/^$/d'
    )"
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
    if ! change_claim="$(optional_value "change")"; then
        note "malformed declaration: $declaration may contain at most one change= line"
        declaration_status="malformed"
        return 0
    fi
    if [[ -n "$change_claim" && "$change_claim" != "additive" ]]; then
        note "malformed declaration: change= must be 'additive' (or absent for the maintainer tier), got '$change_claim'"
        declaration_status="malformed"
        return 0
    fi
    if ! ci_runtime_claim="$(optional_value "ci_runtime")"; then
        note "malformed declaration: $declaration may contain at most one ci_runtime= line"
        declaration_status="malformed"
        return 0
    fi
    declaration_status="valid"
}

print_offending_paths() {
    {
        echo "$guard: changes under $workflows_dir/ require prior authorization on the ledger:"
        printf '%s\n' "$workflow_paths" | sed 's/^/  /'
    } >&2
}

print_human_procedure() {
    {
        echo "$guard: the two-step authorization path:"
        echo "  1. add or update $declaration in THIS branch (tracked), with exactly one"
        echo "     work_item=<ledger-id> line and exactly one reason=<reviewable reason> line;"
        echo "     a logically additive edit (the same work or more) may also attest the additive tier with"
        echo "       change=additive"
        echo "       ci_runtime=no-significant-increase"
        echo "  2. the work item must carry a label that admits the tier:"
        echo "     ADDITIVE tier (attested, logically additive diff):"
        echo "       bd label add <ledger-id> $additive_label"
        echo "       (set only under the maintainer's prior authorization — directly, or by a"
        echo "        coordinator agent holding delegated maintainer authority)"
        echo "     MAINTAINER tier (an edit that can run existing work less often, any reduction"
        echo "     of test coverage or quality gates, any significant CI-runtime increase, or no attestation):"
        echo "       bd label add <ledger-id> $approval_label"
        echo "       (set ONLY by the maintainer, directly; an agent never sets it)"
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
# 4t. The tier — an additive claim is verified against the diff itself
# --------------------------------------------------------------------------
# The additive tier is logical, not textual: it permits a modification only
# when the post-image still carries the same `runs-on`, `concurrency.group`,
# or `env` key path. A deleted blank or comment-only line is inert. Everything
# else deleted can reduce the existing workflow and is refused. Added `if`,
# `continue-on-error`, path filters, and `cancel-in-progress: true` also can
# make work run less, so they are refused. Untracked workflow files have no
# base-side deletions but are still checked for those added-line forms.
#
# Every view is inspected separately: committed work (what is pushed), staged
# work, and the working tree. The pending views are measured against the
# pending base (step 2b), so a line inherited through an in-progress merge is
# never read as this change's deletion.
non_additive_lines_for_view() {
    local base_ref="$1" post_ref="$2"
    shift 2
    local path base_file post_file diff_file
    while IFS= read -r path; do
        [[ -z "$path" ]] && continue
        base_file="$(mktemp)"
        post_file="$(mktemp)"
        diff_file="$(mktemp)"
        if ! git show "${base_ref}:${path}" >"$base_file" 2>/dev/null; then
            : >"$base_file"
        fi
        if [[ "$post_ref" == "WORKTREE" ]]; then
            if [[ -f "$path" ]]; then
                cat "$path" >"$post_file"
            else
                : >"$post_file"
            fi
        elif [[ "$post_ref" == ":" ]]; then
            if ! git show ":${path}" >"$post_file" 2>/dev/null; then
                : >"$post_file"
            fi
        elif ! git show "${post_ref}:${path}" >"$post_file" 2>/dev/null; then
            : >"$post_file"
        fi
        git diff --no-ext-diff --no-renames --no-color -U0 "$@" -- "$path" >"$diff_file"
        awk -v workflow="$path" -v base_file="$base_file" -v post_file="$post_file" '
            function record_path(line, line_number, paths,    indent, rest, key, parent) {
                if (line ~ /^[[:space:]]*($|#)/) return
                match(line, /^[[:space:]]*/)
                indent = RLENGTH
                rest = substr(line, indent + 1)
                sub(/^-[[:space:]]+/, "", rest)
                if (rest !~ /^[^:#][^:]*:/) return
                key = rest
                sub(/:.*/, "", key)
                sub(/[[:space:]]+$/, "", key)
                while (stack_depth > 0 && stack_indent[stack_depth] >= indent) {
                    delete stack_indent[stack_depth]
                    delete stack_path[stack_depth]
                    stack_depth--
                }
                parent = stack_depth > 0 ? stack_path[stack_depth] : ""
                paths[line_number] = parent == "" ? key : parent "." key
                stack_depth++
                stack_indent[stack_depth] = indent
                stack_path[stack_depth] = paths[line_number]
            }
            FILENAME == base_file {
                record_path($0, FNR, base_paths)
                next
            }
            FILENAME == post_file {
                if (FNR == 1) stack_depth = 0
                record_path($0, FNR, post_lines)
                if (FNR in post_lines) post_paths[post_lines[FNR]] = 1
                next
            }
            /^(old|new|deleted file) mode / {
                print workflow ": " $0
                next
            }
            /^@@/ {
                old_line = $0
                sub(/^@@ -/, "", old_line)
                sub(/,.*/, "", old_line)
                old_line += 0
                in_hunk = 1
                next
            }
            !in_hunk { next }
            /^---/ { next }
            /^-/ {
                deleted = substr($0, 2)
                if (deleted !~ /^[[:space:]]*($|#)/) {
                    key_path = base_paths[old_line]
                    permitted = 0
                    if (key_path != "" && post_paths[key_path]) {
                        if (key_path ~ /(^|[.])runs-on$/ || key_path ~ /(^|[.])concurrency[.]group$/ || key_path ~ /(^|[.])env([.]|$)/) {
                            permitted = 1
                        }
                    }
                    if (!permitted) print workflow ": -" deleted
                }
                old_line++
                next
            }
            /^\+\+\+/ { next }
            /^\+/ {
                added = substr($0, 2)
                if (added ~ /^[[:space:]]*(if|continue-on-error|paths|paths-ignore|branches-ignore):/ ||
                    added ~ /^[[:space:]]*cancel-in-progress:[[:space:]]*true([[:space:]]*(#.*)?)?$/) {
                    added_display = added
                    sub(/^[[:space:]]+/, "", added_display)
                    print workflow ": +" added_display
                }
            }
        ' "$base_file" "$post_file" "$diff_file"
        rm -f "$base_file" "$post_file" "$diff_file"
    done < <(git diff --no-ext-diff --no-renames --name-only "$@" -- "$workflows_dir")
}

non_additive_untracked_lines() {
    local path
    while IFS= read -r path; do
        [[ -z "$path" ]] && continue
        awk -v workflow="$path" '
            {
                added = $0
                if (added ~ /^[[:space:]]*(if|continue-on-error|paths|paths-ignore|branches-ignore):/ ||
                    added ~ /^[[:space:]]*cancel-in-progress:[[:space:]]*true([[:space:]]*(#.*)?)?$/) {
                    added_display = added
                    sub(/^[[:space:]]+/, "", added_display)
                    print workflow ": +" added_display
                }
            }
        ' "$path"
    done < <(git ls-files --others --exclude-standard -- "$workflows_dir")
}

non_additive_lines() {
    if [[ -n "$merge_base" && -n "$pending_base" ]]; then
        {
            non_additive_lines_for_view "$merge_base" HEAD "$merge_base" HEAD
            non_additive_lines_for_view "$pending_base" : --cached "$pending_base"
            non_additive_lines_for_view "$pending_base" WORKTREE "$pending_base"
            non_additive_untracked_lines
        } | awk '!seen[$0]++'
    else
        {
            non_additive_lines_for_view HEAD : --cached
            non_additive_lines_for_view : WORKTREE
            non_additive_untracked_lines
        } | awk '!seen[$0]++'
    fi
}

tier="maintainer"
if [[ "$change_claim" == "additive" ]]; then
    offending_lines="$(non_additive_lines)"
    if [[ -n "$offending_lines" ]]; then
        print_offending_paths
        {
            echo "$guard: $declaration claims change=additive, but the workflow diff can run existing work less:"
            printf '%s\n' "$offending_lines" | sed 's/^/  /'
            echo "$guard: a false additive attestation is refused whatever label the item carries;"
            echo "  remove change=additive (the MAINTAINER tier, label $approval_label) or make the edit logically additive"
        } >&2
        exit 1
    fi
    if [[ "$ci_runtime_claim" == "no-significant-increase" ]]; then
        tier="additive"
    else
        note "change=additive without the attestation ci_runtime=no-significant-increase is the maintainer tier"
    fi
fi

if [[ "$tier" == "additive" ]]; then
    accepted_labels=("$additive_label" "$approval_label")
else
    accepted_labels=("$approval_label")
fi

# --------------------------------------------------------------------------
# 4c. No ledger — the declaration alone authorizes, and we say so
# --------------------------------------------------------------------------
if [[ ! -f "$ledger_config" ]]; then
    note "this repository has no ledger ($ledger_config absent): accepting the tracked declaration alone (work_item=$work_item, $tier tier) as the authorization"
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
# `checks/_plan_ledger.py` tolerates. Exit 0 printing the first accepted
# label present, 1 when none is present, 3 when the output cannot be read as
# a ledger record.
label_probe='
import json
import sys

wanted = sys.argv[1:]
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
for label in wanted:
    if label in labels:
        print(label)
        sys.exit(0)
sys.exit(1)
'

set +e
matched_label="$(printf '%s' "$bd_json" | python3 -c "$label_probe" "${accepted_labels[@]}")"
probe_status=$?
set -e

case "$probe_status" in
    0)
        note "workflow edit authorized ($tier tier): $work_item carries $matched_label (declaration: $declaration)"
        exit 0
        ;;
    1)
        print_offending_paths
        if [[ "$tier" == "additive" ]]; then
            note "additive tier: the declared work item $work_item carries neither $additive_label nor $approval_label"
            note "under the maintainer's prior (possibly delegated) authorization:  bd label add $work_item $additive_label"
        else
            note "maintainer tier: the declared work item $work_item does NOT carry the label $approval_label"
            note "the maintainer must run, from their own terminal:  bd label add $work_item $approval_label"
        fi
        print_human_procedure
        exit 1
        ;;
    *)
        fail_closed "bd show $work_item --json via $bd_bin returned output that is not a ledger record"
        ;;
esac
