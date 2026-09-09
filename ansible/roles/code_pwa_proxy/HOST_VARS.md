# Host-specific variables for the `code_pwa_proxy` role

Everything else this role takes is a defensible default. The tailnet hostname
below is not: it is the MagicDNS name of one specific machine, it appears in
the URL the maintainer opens on the Fold, and the post-install probe fetches
it. Merge this into the inventory's `host_vars` for `vps`.

```yaml
# vps
code_pwa_proxy_serve_hostname: vps.perch-rudd.ts.net
```

The HTTPS port (`code_pwa_proxy_serve_https_port`, 8443) is left in
`defaults/main.yml` deliberately: it is a choice this role makes, not a
property of the host, and a second host running this role would want the
same one.
