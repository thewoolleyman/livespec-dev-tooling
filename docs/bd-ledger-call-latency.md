# Ledger call latency per calling host

Record for `livespec-dev-tooling-z4cu3m`. It answers one question: why does one
`bd` call take about 10 s from some hosts, and which of network distance,
tunnel overhead or query count causes it, per calling host. Rule
DOLT-STAYS-ON-VPS holds throughout: the Dolt server and the beads tenant stay
on the VPS `vmi3006760`; no remedy here moves or replicates them.

Measured 2026-11-17 with bd 1.2.2 (`6c124203e`), item `bd show` through the
credential wrapper, with the script in "The measurement script" below.

## Finding

One `bd show` issues about 90 sequential client writes to Dolt over 2
connections. The cost on any host is therefore about 90 times its round trip
to the VPS. Process startup is 0.20 s. The tunnel's connect-plus-greeting time
equals the raw ping floor, and 11 to 13 s for about 90 writes is at most one
path round trip per write, so the tunnel is not now doubling round trips. It
did once: hetzner-xubuntu-info research note 024 (2026-11-14) measured
about 19 s per read because the `-N` tunnel left the VPS's OpenSSH 10.0
without `TCP_NODELAY`, doubling 38 of its then-counted 55 round trips; the
unit now runs without `-N` (its own comment cites note 024). That earlier
count of 55 is round trips as note 024 defined them, this document counts
client writes (90); the two are not the same measure. The dominant cause now
is **query count times network distance**.

## Per calling host

| Calling host | Raw ping to VPS (min / avg) | Ledger-path round trip | One `bd show` wall | Dolt round trips per `bd show` | Dominant cause |
|---|---|---|---|---|---|
| VPS `vmi3006760` | 0.047 / 0.205 ms (loopback) | 1 to 2 ms (connect plus greeting on 127.0.0.1:3307) | 0.95, 1.02, 0.72 s | 90 writes, 179 reads, 2 connections | query count (about 0.62 s over 90 queries; network distance is about 0.02 s and the tunnel does not exist on this host) |
| hetzner-xubuntu | 172 / 255 ms | 171 to 177 ms (`hxi-dolt-tunnel.service`, connect plus greeting) | 11.7 to 13.5 s (six runs) | 90 writes, 205 reads, 2 connections | query count times network distance |
| CI runner pod (measured at node poweredge-xubuntu) | 29.6 / 37.6 ms | not measured (no bd on the node) | derived 2.7 to 3.4 s (90 x RTT) | 90 (same binary) | query count times network distance |
| Factory sandbox pod (measured at node gmktec-xubuntu) | 28.2 / 41.8 ms | not measured (no bd on the node) | derived 2.5 to 3.8 s (90 x RTT) | 90 (same binary) | query count times network distance |

The pod rows are NODE-level, by design: a pod egresses through its node, so its
round trip to the VPS is the node's, and a hand probe pod is refused by
`fleet_host_guard`. The nodes carry neither `bd` nor the credential wrapper, so
only ping was taken and the per-call cost is derived as 90 times the round
trip. That derivation is stated, not measured.

## Where the 90 round trips come from

The source is `bd` itself. The real binary
(`/usr/local/lib/hxi-toolchain/bd-1.2.2/bd`) called directly and the guard
(`/usr/local/bin/bd`, a POSIX shell script) each make exactly 90 writes to the
Dolt port, so neither the guard nor the wrapper adds any. Decoding the write
payloads of one `bd show` shows 7 `START TRANSACTION` / `ROLLBACK` pairs around
a read-only operation, the same issue selected about 13 times, repeated
wisps / labels / dependencies lookups, startup queries (`SELECT
@@max_allowed_packet` twice, `SHOW DATABASES`, `schema_migrations`, `metadata`),
and prepare / execute / close packets for each prepared statement.

## Time spent in startup versus queries

Timed on hetzner-xubuntu (one `bd show`, 12.58 s total): 0.20 s before the
first Dolt write (process startup), 11.17 s between the first and last Dolt
write (queries), 1.21 s after the last write. On the VPS itself the same split
is, untraced, five runs each by `legacy-dispatcher-agent` on the VPS:
`bd --version` (process startup) median 0.22 s (0.20 to 0.31 s); `bd show`
through the wrapper median 0.84 s (0.74 to 1.14 s). So about 0.22 s (26%) is
process startup and about 0.62 s (74%) is Dolt query time plus the wrapper's
own startup, which is about 7 ms per query over 90 queries. A strace of the same
call on the VPS ran 11.9 s because tracing inflates it, so no phase timing is
taken from a traced run there; only its counts (90 writes, 179 reads, 2
connections) are used. The `1.0 s` carried in the item title is the same
measurement within its spread (0.72 to 1.14 s).

## Counts of bd calls

| Unit | bd calls | Ledger time added on hetzner-xubuntu (about 11.5 s per call) | On a node (about 3 s per call, derived) |
|---|---|---|---|
| One CI run of this repository | 0 (no workflow or CI script calls `bd`) | 0 | 0 |
| One factory run | DERIVED, one run: about 39 (upper bound 51). Run `01M7NCTPVMNXCJE458PBHQN34Y`, item `hxi-wsrrso`, green, run window 2026-11-17 18:38:09 to 19:51:19 UTC (dispatch record 18:38:19 to 19:59:04). Method: 0 `bd` calls reached the ledger from the sandbox side (67 stages and all 155 agent Bash calls in `fabro dump`; the 2 attempted `bd comments` were refused by the credential launcher before `bd` ran); 39 host-side calls by the dispatcher loop for that item (show 21, comments 11, update 7) read from the `bd-guard` Honeycomb spans (`bd.argv` containing the item id) over 18:30 to 20:10; 51 if operator and session calls that name the item are counted too (show 25, comments 17, update 8, create 1). Calls whose argv lacks the item id (for example preflight `list` and `config`) are not counted. | about 39 x 11.5 s = 7.5 min if run from hetzner-xubuntu; the dispatcher runs on the VPS, so its actual cost is about 39 x 0.84 s = 33 s | about 39 x 3 s = 2 min |
| One coordinator-seat turn | 0.66 direct `bd` CLI calls per user turn over 110 seat transcripts (3,840 calls in 5,838 turns; up to 3.7 per turn in the heaviest sessions). Excludes the `bd` calls inside plan and drive operations, which each make many. | about 7.6 s per turn, up to about 43 s | about 2 s per turn |

Fleet-wide, the `bd-guard` spans recorded 68,599 `bd` calls in 24 hours (2026-11-16/17), 16,591 of them from `/data/projects/livespec-orchestrator-beads-fabro`; the spans carry no run id, so this is a rate, not a per-run figure. The dispatcher makes 1,323 `bd` calls per dry run on the VPS (measured by
`legacy-dispatcher-agent`), about 22 minutes at 1.0 s each if run from a
distant host.

## The fix

The fix is a work item that reduces the number of sequential Dolt round trips
per `bd` call and keeps Dolt and the beads tenant on the VPS:
`livespec-dev-tooling-tbhqye` (host-captured DoD: a `bd show` on
hetzner-xubuntu completes in under 3 s with at most 5 sequential round trips).
Candidate routes are recorded on that item: the guard runs the real `bd` on the
VPS over one persistent SSH connection (needs a credential decision, owned by
the hetzner-xubuntu-info `hxi_dolt_tunnel` role), upstream `bd` batching, and a
multi-statement read. Related: `livespec-dev-tooling-g4qirz` (the guard cost
and options note in `docs/bd-guard.md`) and `livespec-dev-tooling-2disz5`
(per-call batching in the incident authority reader).

## The measurement script

Run on the calling host from a livespec-dev-tooling checkout; read-only (ping,
a TCP greeting probe on 127.0.0.1:3307, three `bd show`, strace counts).

```bash
#!/bin/bash
# Host-captured measurement for livespec-dev-tooling-z4cu3m. Run ON the calling host,
# from a livespec-dev-tooling checkout, e.g.:
#   bash measure-bd-latency.sh <vps-ip-or-empty> [item-id]
# Prints key=value lines. Read-only: ping, a TCP greeting probe, and `bd show`.
set -u
VPS="${1-66.94.121.15}"
ITEM="${2:-livespec-dev-tooling-z4cu3m}"
W=/usr/local/bin/with-livespec-env.sh
echo "host=$(hostname)"
echo "bd_version=$(bd --version 2>&1 | head -1)"
if [ -n "$VPS" ]; then
  ping -c 10 -q "$VPS" 2>/dev/null | tail -1 | sed 's/^/ping_vps: /'
fi
python3 - <<'PYEOF'
import socket, time
t = []
for _ in range(10):
    s = time.perf_counter()
    try:
        c = socket.create_connection(("127.0.0.1", 3307), timeout=5)
        c.recv(200)
        t.append((time.perf_counter() - s) * 1000)
        c.close()
    except OSError as e:
        print("ledger_path_probe_error:", e); break
if t:
    t.sort(); print("ledger_path_connect_greeting_ms: min %.0f median %.0f" % (t[0], t[len(t)//2]))
PYEOF
for i in 1 2 3; do
  s=$(date +%s.%N); $W -- bd show "$ITEM" >/dev/null 2>&1; e=$(date +%s.%N)
  echo "bd_show_wall_s_$i=$(echo "$e - $s" | bc -l | cut -c1-6)"
done
D=$(mktemp -d)
$W -- strace -f -yy -ttt -e trace=execve,write,sendto,read,recvfrom -o "$D/s" bd show "$ITEM" >/dev/null 2>&1
python3 - "$D/s" <<'PYEOF'
import re, sys
w = r = 0; first = last = None; start = None; end = None; conns = set()
for l in open(sys.argv[1]):
    m = re.match(r'\d+\s+([\d.]+)\s', l)
    if not m: continue
    ts = float(m.group(1))
    start = start or ts; end = ts
    if "3307" not in l: continue
    c = re.search(r'TCP:\[([\d.:]+)->[\d.]+:3307\]', l)
    if c: conns.add(c.group(1))
    if re.match(r'\d+\s+[\d.]+\s+(write|sendto)\(', l):
        w += 1; first = first or ts; last = ts
    elif re.match(r'\d+\s+[\d.]+\s+(read|recvfrom)\(', l):
        r += 1
print("strace_client_writes_to_dolt=%d reads=%d connections=%d" % (w, r, len(conns)))
if first:
    print("startup_before_first_dolt_write_s=%.2f dolt_phase_first_to_last_write_s=%.2f after_last_write_s=%.2f total_s=%.2f" % (first - start, last - first, end - last, end - start))
PYEOF
rm -rf "$D"
```
