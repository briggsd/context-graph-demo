# Deploying to Coolify

Five services in `docker-compose.coolify.yml`:

| Service     | Public? | Purpose                            |
|-------------|---------|------------------------------------|
| `neo4j`     | No      | Graph DB + GDS + APOC              |
| `mcp-server`| No      | MCP SSE server (internal only)     |
| `backend`   | Yes     | FastAPI + agent                    |
| `frontend`  | Yes     | Next.js UI                         |
| `mcpproxy`  | Yes     | Bearer-auth front for `mcp-server` |

All routing uses Coolify's `SERVICE_FQDN_*` magic env pattern — no Domains-
tab or Labels-tab clicking required.

---

## 1. Create the resource

In Coolify:

1. **New Resource → Docker Compose → Public Repository**
2. Repository: `https://github.com/briggsd/context-graph-demo`
3. Branch: `main`
4. **Compose file path: `docker-compose.coolify.yml`** ← this field is the one people miss
5. Save

Coolify parses the compose and lists detected env vars in the Environment
Variables tab.

## 2. Set environment variables

In the **Environment Variables** tab, add the following.

### Secrets (toggle "Is Secret" on)

```
ANTHROPIC_API_KEY=sk-ant-...
NEO4J_PASSWORD=<openssl rand -hex 24>
MCP_AUTH_TOKENS=<openssl rand -hex 32>
```

`MCP_AUTH_TOKENS` is comma-separated if you want multiple clients with
independently revocable tokens.

### Domain assignment (pick A or B)

**Option A — Coolify auto-assigns subdomains of its wildcard.** Leave these
three variables blank (or don't add them — Coolify auto-detects from the
compose file):

```
SERVICE_FQDN_FRONTEND_3000
SERVICE_FQDN_BACKEND_8000
SERVICE_FQDN_MCPPROXY_9091
```

**Option B — use your own domains.** Set explicit values (note: include the
`https://` scheme):

```
SERVICE_FQDN_FRONTEND_3000=https://cg.example.com
SERVICE_FQDN_BACKEND_8000=https://cg-api.example.com
SERVICE_FQDN_MCPPROXY_9091=https://cg-mcp.example.com
```

Then add DNS A records for the three subdomains pointing at the Coolify host.

> ⚠️ **`SERVICE_FQDN_MCPPROXY_9091` quirk.** Coolify sometimes lists this as
> `SERVICE_FQDN_MCPPROXY` (without the port suffix). If you see that, manually
> add `SERVICE_FQDN_MCPPROXY_9091` as a new variable. The compose file
> declares `expose: ["9091"]` to make Coolify pick it up, but older Coolify
> versions miss it. Both names map to the same container, but the port-
> suffixed name routes to the right port reliably.

## 3. Deploy

Click **Deploy**. Watch the build logs — `frontend` and `backend` are slow
the first time (Python + npm installs). Expect ~5 minutes total on a small
VPS.

Coolify will:
- Build all three Dockerfiles (`backend`, `frontend`, `mcp-proxy`)
- Pull `neo4j:5.26.0`
- Wire Traefik routes for the three public services with auto Let's Encrypt

## 4. (Optional) Seed the graph

After the first deploy is green, load demo data:

1. Coolify → `backend` service → **Terminal** tab
2. Run: `uv run python scripts/generate_data.py`

55 entities, 125 relationships, 25 documents, 10 decision traces.

Skip this step if you'd rather start with an empty graph that the agent
populates from chat.

## 5. Smoke-test from your laptop

```bash
# Open the UI
open https://cg.example.com

# Test the MCP proxy
TOKEN=<one MCP_AUTH_TOKENS value>
curl -sN -H "authorization: Bearer $TOKEN" \
  https://cg-mcp.example.com/sse | head -3
```

Expected output:
```
event: endpoint
data: /messages/?session_id=...
```

If you get:
- **HTML or 404** → routing/port issue (see troubleshooting)
- **401 / 403** → routing works, token mismatch
- **`event: endpoint`** → you're done

## 6. Connect the pi extension

```bash
export MCP_URL=https://cg-mcp.example.com/sse
export MCP_AUTH_TOKEN=<one of MCP_AUTH_TOKENS>

cd /path/to/this/repo/..   # one dir up — where .pi/extensions/ lives
pi -p "what services are degraded?"
```

The `.pi/extensions/neo4j-memory` extension reads both env vars, connects
through the auth proxy, and registers all 16 MCP tools.

---

## Troubleshooting

### SSE connections drop after ~30s

Coolify's global Traefik default idle timeout. **Settings → Proxy → Add
custom config:**

```yaml
entryPoints:
  https:
    transport:
      respondingTimeouts:
        idleTimeout: 3600s
```

The compose file sets `flushInterval=10ms` on `mcpproxy`, and `mcp-proxy/main.py`
sets `X-Accel-Buffering: no` — so events stream immediately. The above only
addresses the long-lived connection drop.

### `NEXT_PUBLIC_API_URL` is wrong after changing backend domain

It's baked into the Next.js bundle at build time. **Redeploy** the frontend
(not just restart) so it picks up the new `SERVICE_FQDN_BACKEND_8000`.

### Frontend can't reach backend (CORS)

`backend.CORS_ORIGINS` is derived from `SERVICE_FQDN_FRONTEND_3000`. If you
changed the frontend domain, redeploy the backend so it re-reads the env.

### Rotating a token

Edit `MCP_AUTH_TOKENS` in Coolify, then restart only the `mcpproxy` service.
Old tokens stop working immediately.

### Coolify created `SERVICE_FQDN_MCPPROXY` without `_9091`

This is the documented quirk above. Manually add `SERVICE_FQDN_MCPPROXY_9091`
to the env vars (empty value → auto-domain, or set to your custom domain).
After Coolify accepts it, redeploy `mcpproxy`.

---

## Notes

- **No JWT yet.** Static bearer tokens. To swap to JWT/OAuth, replace
  `_check_auth` in `mcp-proxy/main.py` with a JWKS validator.
- **No rate limiting.** Add `slowapi` to the proxy if you need per-token rate limits.
- **Neo4j heap** is set to 2G. Bump `NEO4J_server_memory_heap_max__size` in
  compose if the graph grows past ~100K nodes.
