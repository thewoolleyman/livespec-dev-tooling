"""The bounded, progress-reporting commands used by delegated gate waits."""

from __future__ import annotations

import math

from livespec_dev_tooling.gate_credential import with_gates_kubeconfig

__all__: list[str] = [
    "WATCH_NO_TERMINAL_DETAIL",
    "admission_read_argv",
    "terminal_watch_argv",
]

WATCH_NO_TERMINAL_DETAIL = "Job watch ended before a terminal condition was observed"
_REQUEST_TIMEOUT_SECONDS = 240
_WATCH_WINDOW_SECONDS = 240
_PROCESS_TIMEOUT_SECONDS = 270
_RUN_WITH_PROGRESS_SCRIPT = (
    r"""
set -eu
progress_stamp=${LIVESPEC_GATE_RUN_PROGRESS_STAMP:-}
heartbeat() {
    sleeper_pid=
    stop_heartbeat() {
        if test -n "$sleeper_pid"; then
            kill "$sleeper_pid" 2>/dev/null || true
            wait "$sleeper_pid" 2>/dev/null || true
        fi
        exit 0
    }
    trap stop_heartbeat TERM
    while :; do
        if test -n "$progress_stamp"; then
            : >"$progress_stamp"
        fi
        sleep 30 &
        sleeper_pid=$!
        wait "$sleeper_pid" || true
        sleeper_pid=
    done
}
heartbeat >/dev/null 2>&1 &
heartbeat_pid=$!
cleanup() {
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
}
trap cleanup EXIT
timeout 270s "$@" --output json --request-timeout=240s &
command_pid=$!
if wait "$command_pid"; then
    exit 0
else
    command_status=$?
fi
if test "$command_status" -eq 124; then
    printf '%s\n' "kubectl admission-state read timed out" >&2
fi
exit "$command_status"
"""
).strip()
_WATCH_TERMINAL_SCRIPT = (
    r"""
set -eu
job_name=$1
namespace=$2
timeout=$3
temporary=$(mktemp -d)
fifo="$temporary/watch"
stderr="$temporary/stderr"
progress_stamp=${LIVESPEC_GATE_RUN_PROGRESS_STAMP:-}
heartbeat() {
    sleeper_pid=
    stop_heartbeat() {
        if test -n "$sleeper_pid"; then
            kill "$sleeper_pid" 2>/dev/null || true
            wait "$sleeper_pid" 2>/dev/null || true
        fi
        exit 0
    }
    trap stop_heartbeat TERM
    while :; do
        if test -n "$progress_stamp"; then
            : >"$progress_stamp"
        fi
        sleep 30 &
        sleeper_pid=$!
        wait "$sleeper_pid" || true
        sleeper_pid=
    done
}
heartbeat >/dev/null 2>&1 &
heartbeat_pid=$!
cleanup() {
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    rm -rf "$temporary"
}
trap cleanup EXIT
mkfifo "$fifo"
timeout 270s kubectl --namespace "$namespace" get job "$job_name" --watch --output json \
    --request-timeout="$timeout" >"$fifo" 2>"$stderr" &
watch_pid=$!
if python3 -c '
import codecs
import json
import sys

decoder = json.JSONDecoder()
utf8 = codecs.getincrementaldecoder("utf-8")()
buffer = ""
while chunk := sys.stdin.buffer.read1(8192):
    buffer += utf8.decode(chunk)
    while True:
        document_text = buffer.lstrip()
        if not document_text:
            buffer = ""
            break
        try:
            document, end = decoder.raw_decode(document_text)
        except json.JSONDecodeError:
            buffer = document_text
            break
        buffer = document_text[end:]
        conditions = document.get("status", {}).get("conditions", ())
        if any(
            condition.get("status") == "True"
            and condition.get("type") in {"Complete", "Failed"}
            for condition in conditions
        ):
            print(json.dumps(document))
            raise SystemExit(0)
raise SystemExit(1)
' <"$fifo"; then
    parser_status=0
else
    parser_status=$?
fi
if test "$parser_status" -eq 0; then
    kill "$watch_pid" 2>/dev/null || true
    wait "$watch_pid" 2>/dev/null || true
    exit 0
fi
if wait "$watch_pid"; then
    watcher_status=0
else
    watcher_status=$?
fi
if test "$watcher_status" -ne 0; then
    if test "$watcher_status" -eq 124; then
        printf '%s\n' "kubectl terminal-state watch timed out" >&2
    fi
    cat "$stderr" >&2
    exit "$watcher_status"
fi
printf '%s\n' "Job watch ended before a terminal condition was observed" >&2
exit 1
"""
).strip()


def admission_read_argv(*, namespace: str, job_name: str) -> list[str]:
    """Build one bounded Job read, renewing gate-run progress while it blocks."""
    return [
        *with_gates_kubeconfig(argv=["sh", "-ceu", _RUN_WITH_PROGRESS_SCRIPT]),
        "await-gate-admission-read",
        "kubectl",
        "--namespace",
        namespace,
        "get",
        "job",
        job_name,
    ]


def terminal_watch_argv(*, namespace: str, job_name: str, remaining_seconds: float) -> list[str]:
    """Build one terminal-condition watch bounded to the remaining wait budget."""
    timeout_seconds = min(
        _WATCH_WINDOW_SECONDS,
        max(1, math.ceil(remaining_seconds)),
    )
    return [
        *with_gates_kubeconfig(argv=["sh", "-ceu", _WATCH_TERMINAL_SCRIPT]),
        "await-gate-terminal-watch",
        job_name,
        namespace,
        f"{timeout_seconds}s",
    ]
