# Cockpit v2 (front end B)

React 19 + Vite 8 + Tailwind 4, started from a Figma Make export and finished
by hand. It renders the same six screens as the native cockpit at `/`, but as a
single-page app reading the read-only JSON API (`/api/*.json`) and the agent
SSE stream (`/agents/<id>/stream`).

- Build: `make cockpit-v2` (or `pnpm install --frozen-lockfile && pnpm build`).
  The bundle lands in `open_composer/cockpit/static/v2/` and the cockpit
  mounts it at `/v2/` when `index.html` exists. The server never runs node.
- Dev: `pnpm dev` on 127.0.0.1:5173 proxies `/api` and `/agents` to the
  cockpit on 8770.
- Routing is the URL hash: `#/agents/<id>`, `#/paper/<strategy>`, `#/hypotheses/<card>`.
- No write requests exist. Every data shape in `src/api.ts` mirrors a
  dataclass in `open_composer/cockpit/data/`; nothing is invented on the client.
