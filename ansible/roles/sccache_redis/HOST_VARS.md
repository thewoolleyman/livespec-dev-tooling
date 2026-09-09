# `sccache_redis` — per-host values for the inventory's `host_vars`

Measured from the live host on 2026-09-06 over `ssh cwoolley@hp-xubuntu` and
carried here from `fabro-hosts/services/sccache-redis/hosts/hp-xubuntu.env`:
30 GiB RAM with 24 GiB available and three concurrent sandboxes; docker network
`bridge` gateway `172.17.0.1/16`; port 6379 free per `ss -ltn`.

Every one of these equals this role's default, so **`hp-xubuntu` needs no
`host_vars` entry at all**. They are listed so the next host's values have
something to differ from — and so the sizing rationale is not lost.

```yaml
# hp-xubuntu
sccache_redis_bind_addr: 172.17.0.1
sccache_redis_port: 6379
sccache_redis_maxmemory: 4gb
sccache_redis_container_memory: 5g
```

`SCCACHE_REDIS_CANONICAL_HOST` (`hp-xubuntu.perch-rudd.ts.net`) and
`SCCACHE_REDIS_SYSTEM_HOSTNAME` (`hp-xubuntu`) are deliberately **not** host
vars: both existed only for `install.sh`'s hostname guard, which inventory
targeting replaces. The canonical host also appeared in the installer's final
success line, which has no counterpart in a play whose recap already names the
host it ran against.

**Why hp-xubuntu and not vps.** vps dispatches Python consumers only, and
sccache is a Rust compilation cache. A vps values file would be a prediction;
add one from vps's own measurement when a Rust consumer is routed there.
