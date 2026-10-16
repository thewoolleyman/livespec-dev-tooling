"""The probes that run INSIDE a pod's network namespace, and the pod they enter.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "DNS", "API" and
"HTTPS". Governing design: `docs/docker-engine-guard-design.md`
Mechanism 3 item 3 as corrected by R8.

WHY A POD'S NAMESPACE AT ALL. The network a Docker install can break on
this host is the POD network: Docker adds a bridge, a masquerade and
FORWARD rules, and k3s's pods reach their DNS, their API server and the
internet through the same forwarding path those rules sit in. A probe
run in the host's namespace would take a different path and pass while
every pod on the machine had lost the network.

WHY EACH PROBE IS A SCRIPT AND NOT A LIBRARY CALL. `nsenter --net`
changes the network namespace of a NEW process, so the request has to be
made by a child; the host's filesystem and interpreter are unchanged
inside it, which is why the host's own Python runs the request. Each
script is deliberately small, stdlib-only, and uses NO resolver: the pod
namespace has no `/etc/resolv.conf`, so a `getaddrinfo` there would fail
on a perfectly healthy host (design R8). Every name the probes need is
resolved on the HOST and passed in as an address.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CRICTL_TIMEOUT_SECONDS",
    "DNS_PROBE",
    "DNS_SCRIPT",
    "POD_LIST_ARGV",
    "POD_NAMESPACE",
    "POD_PROBE_TIMEOUT_SECONDS",
    "dns_probe",
    "dns_probe_argv",
    "inspect_pod_argv",
    "nsenter_argv",
    "pod_namespace_pid",
]

# k3s's own `crictl`, which talks to the embedded containerd rather than
# to any Docker the guard is installing: the pod inventory has to come
# from the runtime that actually holds these pods.
_CRICTL: Final[tuple[str, ...]] = ("k3s", "crictl")

POD_LIST_ARGV: Final[tuple[str, ...]] = (*_CRICTL, "pods", "--state", "Ready", "-o", "json")

# How `inspectp` spells a pod with a network namespace of its OWN. The
# other value is `NODE`, which is a host-network pod -- it shares the
# host's namespaces, so entering it would prove nothing about the pod
# network.
POD_NAMESPACE: Final[str] = "POD"

CRICTL_TIMEOUT_SECONDS: Final[int] = 20

# A request/reply across the pod network, with its own timeout inside
# the script as well: the outer bound catches an `nsenter` that cannot
# enter at all, the inner one a reply that never comes.
POD_PROBE_TIMEOUT_SECONDS: Final[int] = 20

DNS_PROBE: Final[str] = "dns"

# A whole DNS exchange, built and parsed by hand. It never touches a
# resolver: the query is assembled from the name's own labels, sent over
# a UDP socket to the service address it is given, and the reply is read
# from its header -- the transaction id, the response code and the
# answer count. That is what makes it work in a namespace with no
# `/etc/resolv.conf`, and it is also what makes a WRONG answer visible:
# a reply to another query, or an empty answer section, is a failure
# rather than something a resolver would have retried away.
DNS_SCRIPT: Final[str] = (
    "import random, socket, struct, sys\n"
    "server, name = sys.argv[1], sys.argv[2]\n"
    "identifier = random.getrandbits(16)\n"
    "labels = [part.encode() for part in name.split('.')]\n"
    "question = b''.join(bytes([len(part)]) + part for part in labels) + b'\\x00'\n"
    "header = struct.pack('!6H', identifier, 0x0100, 1, 0, 0, 0)\n"
    "query = header + question + struct.pack('!2H', 1, 1)\n"
    "reader = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
    "reader.settimeout(5)\n"
    "reader.sendto(query, (server, 53))\n"
    "reply = reader.recv(512)\n"
    "answered, flags, _, answers = struct.unpack('!4H', reply[:8])\n"
    "assert answered == identifier, 'the reply answered another query'\n"
    "assert flags & 0x000F == 0, 'the reply carried a DNS error code'\n"
    "assert answers > 0, 'the reply carried no answer'\n"
)


def inspect_pod_argv(*, sandbox: str) -> tuple[str, ...]:
    """The inspection of one pod sandbox: its namespace options and its PID."""
    return (*_CRICTL, "inspectp", "-o", "json", sandbox)


def _sandbox_pid(*, text: str) -> str:
    """One `inspectp` answer's sandbox PID, or nothing when it is host-network."""
    inspected = json.loads(text)
    options = inspected["status"]["linux"]["namespaces"]["options"]
    return str(inspected["info"]["pid"]) if options["network"] == POD_NAMESPACE else ""


def pod_namespace_pid(*, runner: GuardCommandRunner) -> str:
    """The sandbox PID of a ready pod on this node that is NOT host-network.

    The first qualifying pod wins, and the choice is made AFRESH on
    every sample rather than remembered: this host runs a CI pool whose
    ARC listener deletes and creates pods continuously, so a pid held
    across samples would be a pid that has gone (design Mechanism 3,
    "the pod is re-selected if it disappears").

    An empty answer means no such pod exists right now, which the
    caller reports as a failed probe rather than treating as a pass:
    a node with no pod to enter is a node whose pod network cannot be
    proven.
    """
    listed = runner(argv=POD_LIST_ARGV, timeout_seconds=CRICTL_TIMEOUT_SECONDS)
    for sandbox in json.loads(listed.stdout)["items"]:
        inspected = runner(
            argv=inspect_pod_argv(sandbox=str(sandbox["id"])),
            timeout_seconds=CRICTL_TIMEOUT_SECONDS,
        )
        pid = _sandbox_pid(text=inspected.stdout)
        if pid:
            return pid
    return ""


def nsenter_argv(*, pid: str, argv: Sequence[str]) -> tuple[str, ...]:
    """`argv`, run in the network namespace of the process `pid`, and nothing else.

    `--net` ALONE: the mount, PID and user namespaces are deliberately
    left as the host's, so the host's interpreter and its standard
    library are what the probe runs, and the only thing that changes is
    the network path the request takes.
    """
    return ("nsenter", "--target", pid, "--net", "--", *argv)


def dns_probe_argv(*, pid: str, server: str, name: str) -> tuple[str, ...]:
    """The DNS exchange, run inside the pod namespace against `server`."""
    return nsenter_argv(pid=pid, argv=(sys.executable, "-c", DNS_SCRIPT, server, name))


def dns_probe(*, runner: GuardCommandRunner, pid: str, server: str, name: str) -> ProbeResult:
    """Whether the kube-dns service answers this pod's namespace."""
    answer = runner(
        argv=dns_probe_argv(pid=pid, server=server, name=name),
        timeout_seconds=POD_PROBE_TIMEOUT_SECONDS,
    )
    failure = f"the DNS query to {server} from the pod namespace exited {answer.returncode}"
    return ProbeResult(
        name=DNS_PROBE,
        passed=answer.returncode == 0,
        error="" if answer.returncode == 0 else failure,
    )
