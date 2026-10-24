# `fabro_client` — per-host values for the inventory's `host_vars`

The pinned Fabro **CLIENT** builds a dev host stages for a Dispatcher running
natively on it. Each build is placed at a declared stable path from a
digest-verified control-node source by `ansible/dev-host.yml`, and never by
hand.

Governed by `SPECIFICATION/non-functional-requirements.md` §"Dev host Fabro
client builds" and the `SPECIFICATION/scenarios.md` scenario "the dev-host play
stages each pinned Fabro client build and refuses an unsafe entry". Work-item
`livespec-dev-tooling-lirki2`, requested by plan `fabro-currency` (`bd-ib-6tcjfx`)
for its `bd-ib-zb2hso` at the fleet coordinator's direction.

**Why it exists.** A Dispatcher reaches a factory through whichever `fabro`
client its repository's committed `dispatcher.factories.<name>.bin` names, or
through the host PATH client when it commits none. Measured 2026-10-23: the
`petri` carrier client every fleet repository commits —
`~/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro` — had been
staged BY HAND. Nothing recorded which build it was, no drift report saw it, and
a routing table for fifteen repositories rested on a binary nobody could
reproduce. The two families cannot be collapsed either: `legacy` is the 0.254
fork engine, `petri` is the Petri-era engine, and since the Kubernetes canary of
2026-10-23 the Petri factory holds a run with a `kubernetes` sandbox the 0.254
client cannot decode at all — so a 0.254 reader of it is BLIND, not merely old.

**Server binaries are a different role.** `fabro_server` owns the binary a Fabro
SERVER unit starts, through its own `binary_source` / `binary_sha256` axes, and
it RETAINS the outgoing build beside the new one. This role owns client builds
only. The two never write one file, and the refusal below is what guarantees it.

## The variables

| variable | default | what it is |
| --- | --- | --- |
| `fabro_client_builds` | `[]` | **THE DECLARATION.** A list of entries, each with the three keys below. Declared ONLY in `ansible/inventory/group_vars/dev_hosts.yml` |
| `fabro_client_path_client` | absent | Optional PATH-client declaration beside `fabro_client_builds`; its `link` and `target` fields are described below |
| `fabro_client_owner` | `ubuntu` | the login that owns every staged build and every ancestor directory this role creates; the build's group is that account's PRIMARY group, derived from the account and never declared |
| `fabro_client_server_binary_path_default` | derived | the `binary_path` a `fabro_server` instance that names none runs, resolved from this host's own `fabro_server_host_home`. Read by the exclusion below; not a value an operator sets |

### The keys of one entry

| key | what it is |
| --- | --- |
| `path` | the ABSOLUTE path on the dev host where the build is placed. Written only by this play. This is the value a committed `bin` must equal |
| `source` | an ABSOLUTE control-node path holding the build an operator has staged. Read, never written |
| `sha256` | that build's digest, 64 hexadecimal digits, compared case-insensitively |

### Which committed `bin` values point at each declared path

The fleet's routing rests on this correspondence, so it is written down rather
than left to be inferred from fifteen repositories:

| declared `path` | the `bin` that names it |
| --- | --- |
| `…/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro` | every fleet repository's `dispatcher.factories.petri.bin`, including this repository's own |
| `…/fabro-currency/carrier-legacy-v0.254-8869e88/fabro` | each repository that declares a `legacy` factory, per `bd-ib-zb2hso` step 1. None commits one yet |

For THIS repository the correspondence is enforced:
`check-dev-host-fabro-client-bins-declared` fails this repository's `just check`
aggregate when a committed `bin` names no declared `path`, and reports itself
VACUOUS rather than as a pass when no `bin` is committed at all. **For every
other fleet repository the same rule is documentation, which is this paragraph:**
a repository that commits a `bin` naming a path absent from the table above is
reaching a build this play does not stage, and the check in its own tree cannot
see that — it reads this inventory, which that repository does not have.

### A dev host whose login differs sets `fabro_client_owner`

The default is the login the one host in `dev_hosts` uses, the same account
`fabro_server_host_user`, `dev_host_retention_user` and `codex_config_user` name
there, so that host needs no entry. A dev host whose login differs sets it in
its own `host_vars`:

```yaml
# <some-other-dev-host> — the Dispatcher runs as this login, so the builds it
# execs are owned by it.
fabro_client_owner: cwoolley
```

Why it has to be the Dispatcher's own login: a root-owned build under that
account's home is one the account cannot replace through any ordinary path, and
the first symptom is a converge that looks clean while a hand repair is refused.

## What one converge does

For each declared entry, after EVERY entry has been validated:

- every missing ancestor directory of `path` is created, mode 0755, owned by
  `fabro_client_owner` and that account's primary group. An ancestor that
  already exists is left exactly as found — mode and owner included — because a
  declared path legitimately sits inside a tree another role or the operator
  owns;
- when the file at `path` already hashes to `sha256`, its contents are left
  untouched and its mode and owner are still ensured — which is how a build this
  role has adopted rather than placed gets its mode tightened without being
  rewritten. The petri carrier is the one such build today: it was hand-staged at
  mode 0775, so the first converge tightens it to 0755, and whether that converge
  also rewrites it depends on whether the hand-staged copy already hashes to the
  declared digest. The drift report says which;
- otherwise the build is placed ATOMICALLY: written to `<path>.incoming` in the
  same directory with the final mode and owner, verified against `sha256`, and
  only then renamed into place. A Dispatcher already exec'ing the old build
  keeps a whole file, because `rename(2)` does not touch the inode a running
  process holds;
- a `<path>.incoming` an interrupted converge left behind may be overwritten or
  removed, and is removed first when it is not a regular file.

A second converge with unchanged inventory on an undrifted host changes nothing.

**Nothing else on the host is ever removed.** A build at a path the inventory no
longer declares STAYS in place: a Dispatcher in another fleet repository may
still name it in a committed `bin`, and this role keeps no record of earlier
inventories, so it does not report such a file either. Only a declared entry's
own `<path>.incoming` is ever deleted.

## What one converge refuses, and when

Every refusal below is decided BEFORE anything on the host is written, so an
inventory with one bad entry leaves every declared path holding exactly the
build the previous converge installed. A refusal names each refused entry and
its reason.

An entry is refused when it

- omits `path`, `source` or `sha256`;
- declares a `path` or `source` that is not absolute;
- declares a `sha256` that is not 64 hexadecimal digits;
- declares a `path` that DENOTES THE SAME FILE on the host as another entry's
  `path`;
- declares a `path` at which the host already holds something that is not a
  regular file — a symbolic link included;
- declares a `path` an ancestor of which exists on the host and, after symbolic
  links are resolved, is not a directory;
- declares a `path` that DENOTES THE SAME FILE on the host as the `binary_path`,
  explicit or defaulted, of any `fabro_server_instances` mapping declared for
  that host;
- declares a `path` whose `<path>.incoming` DENOTES THE SAME FILE as any entry's
  `path` or as any such `binary_path`;
- declares a `source` that denotes the same file as its own `path` or any
  entry's `path`, on a dev host that is also the control node;
- declares a `source` that is absent on the control node, or that hashes there
  to anything but `sha256`.

Two names **denote the same file** when they are equal after every symbolic link
in both, final component included, is resolved, or when both exist and are on
the same device with the same inode. This is not a string comparison, and that
matters here: on `vps` the PATH client `~/.local/bin/fabro` is a symbolic link
to `~/.fabro/bin/fabro`, which is the `fabro_server` role's default
`binary_path`, so two names that look nothing alike reach one file.

**A declared `path` is never a server instance's `binary_path`, and is best kept
out of a server instance's binary directory altogether.** The refusal catches the
same file; it cannot catch a NEIGHBOUR. `fabro_server` stages into that directory
and retains `<binary_path>.<digest>.bak` copies there, and a client build sitting
among them is one an operator reading that directory would reasonably take for a
server build. The declared paths therefore live under
`~/.local/state/fabro-currency/`, which is where the pinned client carriers
already were.

## The PATH client

`fabro_client_path_client` is optional and is declared only beside
`fabro_client_builds` in `ansible/inventory/group_vars/dev_hosts.yml`:

```yaml
fabro_client_path_client:
  link: /home/ubuntu/.local/bin/fabro
  target: /home/ubuntu/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro
```

`link` is the absolute pathname the host PATH resolves. `target` is the absolute
pathname of one declared `fabro_client_builds` entry. After every declared build
is in place, the role makes `link` a symbolic link whose literal `readlink`
output is exactly `target`, with the role owner and that user's primary group.
Missing ancestors are created like build ancestors. A matching undrifted link is
left in place, so a second converge reports no change; a changed or absent link
is replaced by an atomic rename of `<link>.incoming`.

The declaration refuses before writing when either field is missing or
non-absolute, `target` names no declared build, `link` exists as anything other
than a symbolic link, its resolved target is a directory, an ancestor is not a
directory, either `link` or `<link>.incoming` collides with a declared build,
build staging name or server binary, or `<link>.incoming` exists as a regular
file. The final component of `link` is not resolved for that collision check:
an old PATH link may legitimately point at a server binary, and this role must
replace that link without writing through it.

Moving the PATH client between client families is a change to `target` followed
by the dev-host play. It is not a `fabro_server` change: the server role owns its
binary, while this role replaces only the PATH symbolic link that may previously
have named it.

## Rollback is a change to the inventory, not a retained copy

`fabro_server` keeps the outgoing server binary beside the new one, because a
server that will not start is a factory that is down and the rollback has to be
reachable in one move on the host. A client build is different: the outgoing
build is NOT retained here, and a rollback is changing the entry's `source` and
`sha256` back and converging.

Three reasons, and the first is the load-bearing one:

- a retained copy is a build on the host that version control does not describe,
  which is exactly the state this section exists to end. The committed entry is
  the record of which build a host runs, and a `.bak` beside it would be a
  second answer;
- the control node holds every staged source already, so the previous build has
  not gone anywhere — the roll-back target is a path an operator can read out of
  this file's own git history;
- a client is exec'd per dispatch rather than held open by a unit, so a bad
  build is noticed on the next dispatch and costs one converge to undo. There is
  no restart window to get through.

## Operator procedure

Stage the build on the control node first — this role never BUILDS one — then
declare it and converge:

```bash
sha256sum /home/ubuntu/.local/state/fabro-web-prod/<build>/fabro
# edit ansible/inventory/group_vars/dev_hosts.yml: path, source, sha256
just ansible-drift ansible/dev-host.yml --tags fabro_client
just ansible-apply ansible/dev-host.yml --tags fabro_client
```

A `source` may not be its own `path` on a host that is also the control node, so
a build whose `path` is already populated by hand needs a SEPARATE control-node
copy staged as its `source` before the first converge.

To read what the host now holds:

```bash
for f in /home/ubuntu/.local/state/fabro-currency/*/fabro; do
  printf '%s ' "$f"; "$f" --version; sha256sum "$f" | cut -d' ' -f1
done
```

Silence is not success: the drift report names every entry it would place and
every refusal it would make. A `--check` run cannot verify a staged copy it did
not make, so it reports the rename as a would-be change and skips the staged
digest read.

## Rollback of the role itself

```bash
# remove the entries from ansible/inventory/group_vars/dev_hosts.yml, and the
# `bin` that names each declared path from every repository that commits one
```

Nothing on the host is removed by that: the builds stay where they are, because
another repository's committed `bin` may still name them. Remove them by hand
only once nothing names them — and that is the one hand change this section
sanctions, because the role deliberately keeps no record of what it used to
declare.
