# flake_retry_filer — host-side retry filing

The role runs the one flake-retry reader on the dev host. It invokes the
installed `livespec-dev-tooling` virtual environment through
`/usr/local/bin/with-livespec-env.sh`, which supplies the existing Beads
credential; it does not add a CI credential.

The defaults target the dev host's canonical checkout at
`/data/projects/livespec-dev-tooling` and its `ubuntu` service account. A host
that relocates that checkout or uses another account overrides these values:

```yaml
flake_retry_filer_repo_root: /data/projects/livespec-dev-tooling
flake_retry_filer_python: /data/projects/livespec-dev-tooling/.venv/bin/python
flake_retry_filer_user: ubuntu
flake_retry_filer_group: ubuntu
```

`livespec-flake-retry-filer.timer` runs the reader every 15 minutes.
`livespec-flake-retry-filer-staleness.timer` checks the last successful pass
every five minutes. When the reader has not completed within 900 seconds, its
service fails and its journal entry names `flake-retry-filer` and
`age_seconds`; inspect it with:

```bash
systemctl status livespec-flake-retry-filer-staleness.service
journalctl -u livespec-flake-retry-filer-staleness.service
```

Converge it with:

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags flake_retry_filer
```
