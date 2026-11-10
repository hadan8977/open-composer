# Read-only Cockpit operations

This is the English operational reference extracted from the September2026 deployment record. Historical verification, old unit names and old provider-console screenshots are retained in the guidance-consolidation before snapshot; they do not prove today's service state.

The current documented architecture is a loopback-only Cockpit at `127.0.0.1:8770`, exposed through Cloudflare Tunnel with Cloudflare Access in front of every route, including API and SSE. No public write/command surface, separate API bypass or new authentication platform is intended.

## Existing service contract

- `quant.service`:project `.venv` runs `python -m open_composer.cockpit --host 127.0.0.1 --port 8770 --log-level warning`; `Restart=on-failure`,5second delay, `MemoryMax=300M`, `MemoryHigh=250M`, `OOMScoreAdjust=-200`, `ProtectSystem=strict`, no `ReadWritePaths`, `NoNewPrivileges=yes`, `ProtectKernelTunables=yes`.
- `cloudflared-quant.service`:existing remote-managed tunnel; `Restart=always`,5second delay, `MemoryMax=200M`, `ProtectSystem=strict`, `ProtectHome=read-only`, `NoNewPrivileges=yes`. Its configured token file is a credential:do not print or copy it into artifacts. Origin routing and Access policies are managed in the provider console.
- `quant-reload.path` watches the Cockpit code/data/template/static CSS/JS directories and triggers `quant-reload.service`, which waits3seconds then restarts `quant.service`. The local2026-10-15 read-only check confirmed the active Cockpit limits at300MiB max and250MiB high. Confirm actual deployed units before maintenance. This documentation cleanup does not restart or change them.

## Read-only checks

```bash
systemctl status quant cloudflared-quant quant-reload.path --no-pager
journalctl -u quant -u cloudflared-quant -n 80 --no-pager
systemctl show quant.service -p ActiveEnterTimestamp
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://quant.hadan.blog/
```

An unauthenticated request should be denied or redirected to Cloudflare Access, not return Cockpit content. Check root/API/agent paths when assessing exposure. A redirect alone does not prove an authorized user's complete workflow. Investigate unexpected public200responses and handle actual exposure under existing incident authority; do not alter unrelated tunnels.

## Route maintenance

For a permitted route change, establish the owner-restricted Access policy before publishing the hostname. Keep API and SSE behind the same policy. Then route the approved hostname to loopback8770 and verify unauthorized access is blocked. Use current official provider guidance for console details rather than copying dated UI labels.

The historical setup used the existing `dsh-vps` tunnel and `quant.hadan.blog`, with owner-email authentication. It did not require WARP, a second client-side network or a separate service-token API bypass. Unrelated legacy routes and provider credentials are not permission to change them.
