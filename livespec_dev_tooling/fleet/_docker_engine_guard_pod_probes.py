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
    "API_PROBE",
    "API_SCRIPT",
    "CRICTL_TIMEOUT_SECONDS",
    "DNS_PROBE",
    "DNS_SCRIPT",
    "HTTPS_PROBE",
    "HTTPS_SCRIPT",
    "POD_LIST_ARGV",
    "POD_NAMESPACE",
    "POD_PROBE_TIMEOUT_SECONDS",
    "RESOLVE_TIMEOUT_SECONDS",
    "UBUNTU_ARCHIVE_HOST",
    "UBUNTU_ARCHIVE_PATH",
    "api_probe",
    "api_probe_argv",
    "dns_probe",
    "dns_probe_argv",
    "https_probe",
    "https_probe_argv",
    "inspect_pod_argv",
    "nsenter_argv",
    "pod_namespace_pid",
    "resolve_argv",
    "resolve_on_host",
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


# A TLS handshake and nothing beyond it. Verification is deliberately
# OFF: no credential is involved here, and the identity of the API
# server is what the Node Ready read proves through the node-status
# kubeconfig. What this script proves is the PACKET PATH -- that the pod
# namespace reached a service ClusterIP, that kube-proxy's rules carried
# it to a real endpoint, and that the endpoint answered far enough to
# negotiate a session. `version()` is the assertion because a wrapped
# socket that never completed its handshake has none.
API_SCRIPT: Final[str] = (
    "import socket, ssl, sys\n"
    "address, port = sys.argv[1], int(sys.argv[2])\n"
    "context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)\n"
    "context.check_hostname = False\n"
    "context.verify_mode = ssl.CERT_NONE\n"
    "with socket.create_connection((address, port), timeout=5) as raw:\n"
    "    with context.wrap_socket(raw) as secured:\n"
    "        assert secured.version() is not None, 'no TLS session was established'\n"
)

API_PROBE: Final[str] = "api"


def api_probe_argv(*, pid: str, address: str, port: int) -> tuple[str, ...]:
    """The handshake, run inside the pod namespace against a service address."""
    return nsenter_argv(pid=pid, argv=(sys.executable, "-c", API_SCRIPT, address, str(port)))


def api_probe(*, runner: GuardCommandRunner, pid: str, address: str, port: int) -> ProbeResult:
    """Whether the Kubernetes API service address answers this pod's namespace."""
    answer = runner(
        argv=api_probe_argv(pid=pid, address=address, port=port),
        timeout_seconds=POD_PROBE_TIMEOUT_SECONDS,
    )
    failure = (
        f"the TLS handshake to {address}:{port} from the pod namespace "
        f"exited {answer.returncode}"
    )
    return ProbeResult(
        name=API_PROBE,
        passed=answer.returncode == 0,
        error="" if answer.returncode == 0 else failure,
    )


# The egress endpoint, fixed by design R8: an Ubuntu archive mirror,
# which carries no per-hour quota. The GitHub API it replaced
# rate-limits an unauthenticated caller at sixty requests an hour, so a
# window sampling every fifteen seconds would begin failing part way
# through on a host whose network was perfectly fine. The canary's own
# egress check uses the same endpoint for the same reason.
UBUNTU_ARCHIVE_HOST: Final[str] = "archive.ubuntu.com"
UBUNTU_ARCHIVE_PATH: Final[str] = "/ubuntu/"

HTTPS_PROBE: Final[str] = "https"

# `ahostsv4` rather than `hosts`: the probe needs an IPv4 address to
# hand to a namespace whose forwarding path is IPv4, and `hosts` would
# answer an AAAA record on a host with IPv6 resolution.
RESOLVE_TIMEOUT_SECONDS: Final[int] = 10

# An HTTPS HEAD whose SNI is sent EXPLICITLY. The connection is opened
# to an address, because the pod namespace cannot resolve a name -- and
# an address carries no name, so both the TLS server name and the HTTP
# `Host` header have to be supplied by hand or the mirror answers a
# redirect or a 400 that has nothing to do with this host's network.
# `Connection: close` so the reply ends without a second round trip.
HTTPS_SCRIPT: Final[str] = (
    "import socket, ssl, sys\n"
    "address, host, path = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "context = ssl.create_default_context()\n"
    "request = 'HEAD ' + path + ' HTTP/1.1\\r\\n'\n"
    "request += 'Host: ' + host + '\\r\\nConnection: close\\r\\n\\r\\n'\n"
    "with socket.create_connection((address, 443), timeout=10) as raw:\n"
    "    with context.wrap_socket(raw, server_hostname=host) as secured:\n"
    "        secured.sendall(request.encode())\n"
    "        status = secured.recv(64).split(b' ')[1:2]\n"
    "        assert status, 'the mirror sent no status line'\n"
    "        assert status[0][:1] in (b'2', b'3'), 'the mirror answered ' + repr(status[0])\n"
)


def resolve_argv(*, host: str) -> tuple[str, ...]:
    """The HOST-side resolution of `host`, run outside any pod namespace."""
    return ("getent", "ahostsv4", host)


def resolve_on_host(*, runner: GuardCommandRunner, host: str) -> str:
    """`host`'s first IPv4 address as the HOST resolves it, or nothing.

    Resolved here and not inside the namespace, for the reason the
    module docstring records. Only the FIRST row's address is taken:
    `getent` repeats each address once per socket type, so a caller
    reading every row would get the same address three times.
    """
    answer = runner(argv=resolve_argv(host=host), timeout_seconds=RESOLVE_TIMEOUT_SECONDS)
    addresses = tuple(field for raw in answer.stdout.splitlines() for field in raw.split()[:1])
    return addresses[0] if addresses else ""


def https_probe_argv(*, pid: str, address: str, host: str, path: str) -> tuple[str, ...]:
    """The HEAD, run inside the pod namespace against a host-resolved address."""
    return nsenter_argv(pid=pid, argv=(sys.executable, "-c", HTTPS_SCRIPT, address, host, path))


def https_probe(
    *,
    runner: GuardCommandRunner,
    pid: str,
    host: str = UBUNTU_ARCHIVE_HOST,
    path: str = UBUNTU_ARCHIVE_PATH,
) -> ProbeResult:
    """Whether this pod's namespace still reaches the internet over HTTPS.

    A name that does not resolve on the host is reported as its own
    failure rather than as a failed request: the two have different
    causes and only one of them is about the pod network.
    """
    address = resolve_on_host(runner=runner, host=host)
    if not address:
        return ProbeResult(
            name=HTTPS_PROBE, passed=False, error=f"{host} did not resolve on the host"
        )
    answer = runner(
        argv=https_probe_argv(pid=pid, address=address, host=host, path=path),
        timeout_seconds=POD_PROBE_TIMEOUT_SECONDS,
    )
    failure = f"the HEAD of https://{host}{path} from the pod namespace exited {answer.returncode}"
    return ProbeResult(
        name=HTTPS_PROBE,
        passed=answer.returncode == 0,
        error="" if answer.returncode == 0 else failure,
    )
