#!/usr/bin/env bash
# Run one command under a tenant's committed credential wrapper (role reconcile_runs).
#
# usage: livespec-tenant-wrap.sh -- <command> [<arg>...]
#        livespec-tenant-wrap.sh --resolve
#
# The tenant is the repository $TW_REPO names, else the working directory, which
# for a reconcile-runs service is its WorkingDirectory. The wrapper is that
# repository's committed `.livespec.jsonc` `credential_wrapper` argv, read when
# the command runs. A host copy of the argv would go stale the moment the tenant
# changes its wrapper. After the livespec-ai organization transfer, the stale
# family wrapper mints the personal GitHub App, which livespec-ai repositories
# refuse (livespec-orchestrator-beads-fabro bd-ib-ft426g).
#
# The family wrapper is $TW_FAMILY_WRAPPER, else /usr/local/bin/with-livespec-env.sh.
#   - No credential_wrapper:          <family> -- <command...>
#   - A wrapper whose first element has the family wrapper's basename runs as
#     committed, including any hop after its "--":
#                                     <argv...> <command...>
#   - Any other tenant's wrapper runs nested in the family wrapper, with the
#     family BEADS_DOLT_PASSWORD removed so the tenant's wrapper injects its own:
#                                     <family> -- env -u BEADS_DOLT_PASSWORD <argv...> <command...>
# A relative first element resolves against the repository, as the dispatcher
# resolves it.
#
# A .livespec.jsonc that cannot be read, or whose credential_wrapper is not a
# non-empty array of non-empty strings, exits 78 and runs nothing. It never
# falls back to the family wrapper, because that fallback is the wrong-App
# failure this script exists to prevent. A wrapper that is not an executable
# file also exits 78.
#
# --resolve runs nothing. It checks the same inputs, prints `mode=` and `chain=`
# (the shell-quoted argv the command would follow), and exits 0, or 78 when the
# command would be refused. The role runs it before it changes the host.
set -euo pipefail

family="${TW_FAMILY_WRAPPER:-/usr/local/bin/with-livespec-env.sh}"
repo="${TW_REPO:-${PWD}}"
config="${repo}/.livespec.jsonc"

refuse() {
  printf 'livespec-tenant-wrap: %s\n' "$1" >&2
  exit 78
}

resolve_only=0
case "${1:-}" in
  --resolve) resolve_only=1 ;;
  --) shift ;;
  *) printf 'usage: livespec-tenant-wrap.sh -- <command> [<arg>...] | --resolve\n' >&2; exit 64 ;;
esac
if ((!resolve_only)) && (($# == 0)); then
  printf 'livespec-tenant-wrap: no command after --\n' >&2
  exit 64
fi

# The first element the parser emits is a status: ok, absent, or error:<reason>.
# The argv follows it, NUL-separated, so an argument may hold any character.
argv=()
if [[ -e "${config}" ]]; then
  mapfile -d '' -t argv < <(python3 - "${config}" <<'PY'
import json
import sys


def strip_comments(text):
    out, i, in_string = [], 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\":
                out.append(text[i + 1 : i + 2])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    return "".join(out)


def strip_trailing_commas(text):
    out, i, in_string = [], 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\":
                out.append(text[i + 1 : i + 2])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif char == "," and text[i + 1 :].lstrip()[:1] in ("]", "}"):
            pass
        else:
            out.append(char)
        i += 1
    return "".join(out)


def emit(*fields):
    sys.stdout.write("".join(field + "\0" for field in fields))


try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        document = json.loads(strip_trailing_commas(strip_comments(handle.read())))
except (OSError, UnicodeDecodeError, ValueError) as error:
    emit(f"error:{sys.argv[1]} is not readable JSONC ({error})")
    sys.exit(0)
if not isinstance(document, dict) or "credential_wrapper" not in document:
    emit("absent")
    sys.exit(0)
wrapper = document["credential_wrapper"]
if not (isinstance(wrapper, list) and wrapper and all(isinstance(a, str) and a for a in wrapper)):
    emit(f"error:credential_wrapper in {sys.argv[1]} is not a non-empty array of non-empty strings")
    sys.exit(0)
emit("ok", *wrapper)
PY
  )
  ((${#argv[@]})) || refuse "credential-wrapper-unreadable: could not parse ${config}"
  status="${argv[0]}"
  argv=("${argv[@]:1}")
  case "${status}" in
    ok | absent) ;;
    error:*) refuse "credential-wrapper-unreadable: ${status#error:}" ;;
    *) refuse "credential-wrapper-unreadable: unexpected parser status for ${config}" ;;
  esac
fi

[[ -f "${family}" && -x "${family}" ]] || refuse "family wrapper ${family} is not an executable file"

if ((${#argv[@]} == 0)); then
  mode=default
  chain=("${family}" --)
else
  [[ "${argv[0]}" == /* ]] || argv[0]="${repo}/${argv[0]#./}"
  [[ -f "${argv[0]}" && -x "${argv[0]}" ]] \
    || refuse "credential_wrapper ${argv[0]} from ${config} is not an executable file"
  if [[ "${argv[0]##*/}" == "${family##*/}" ]]; then
    mode=family
    chain=("${argv[@]}")
  else
    mode=tenant
    chain=("${family}" -- env -u BEADS_DOLT_PASSWORD "${argv[@]}")
  fi
fi

if ((resolve_only)); then
  printf 'mode=%s\n' "${mode}"
  printf 'chain=%s\n' "$(printf '%q ' "${chain[@]}")"
  exit 0
fi
exec "${chain[@]}" "$@"
