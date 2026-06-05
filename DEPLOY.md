# Deploying to Coolify

This stack ships as five services in `docker-compose.coolify.yml`:

| Service     | Purpose                              | Public? |
|-------------|--------------------------------------|---------|
| `neo4j`     | Graph database + GDS + APOC          | No      |
| `backend`   | FastAPI app + agent                  | Yes     |
| `frontend`  | Next.js UI                           | Yes     |
| `mcp-server`| Neo4j-agent-memory MCP over SSE      | No      |
| `mcpproxy`  | Bearer-auth front for `mcp-server`   | Yes     |

The MCP server is intentionally **never exposed directly** — clients go
through `mcp-proxy`, which checks `Authorization: Bearer <token>` before
forwarding.

This compose file uses Coolify's "magic" `SERVICE_FQDN_*` env vars, so you
**do not have to use the Domains tab** — Coolify auto-generates and wires
domains for the three public services.

## 1. Connect the repo

1. **New Resource → Docker Compose → Public Repository** (or Private + GitHub App)
2. Repository: this repo
3. Branch: `main`
4. **Compose file path:** `docker-compose.coolify.yml`
5. Click **Save**. Coolify reads the compose and shows you the env vars it
   detected (including `SERVICE_FQDN_*` and `${...}` substitutions).

## 2. Set environment variables

In Coolify's **Environment Variables** tab, set these.

### Secrets (toggle "Is Secret" on)

| Variable | How to generate |
|---|---|
| `ANTHROPIC_API_KEY` | from console.anthropic.com |
| `NEO4J_PASSWORD` | `openssl rand -hex 24` |
| `MCP_AUTH_TOKENS` | `openssl rand -hex 32` (comma-separate for multiple clients) |

### Domains (plain — these are public values)

You have two options:

**Option A — let Coolify auto-assign domains** (easiest, gives ugly URLs):
Leave `SERVICE_FQDN_FRONTEND_3000`, `SERVICE_FQDN_BACKEND_8000`, and
`SERVICE_FQDN_MCP_PROXY_9091` blank. Coolify will fill them in with auto-
generated subdomains of the Coolify instance's wildcard domain on first
deploy.

**Option B — use your own domains** (recommended). Add these env vars:

```
SERVICE_FQDN_FRONTEND_3000=https://cg.example.com
SERVICE_FQDN_BACKEND_8000=https://cg-api.example.com
SERVICE_FQDN_MCPPROXY_9091=https://cg-mcp.example.com
```

> ⚠️ Note the env var is `SERVICE_FQDN_MCPPROXY_9091` (no underscore). Coolify
> derives the magic-env name from the compose service name, and the service
> is named `mcpproxy` — hyphens in service names confuse Coolify's parser, so
> we keep it as one word.

Then point those DNS A records at the Coolify host. **Include the
`https://` scheme** — it's part of the value, not just the hostname.

## 3. Deploy

Click **Deploy**. Coolify will:
- Build the three Dockerfiles (`backend`, `frontend`, `mcp-proxy`)
- Pull `neo4j:5.26.0`
- Auto-generate Traefik routes for the three public services
- Auto-issue Let's Encrypt certs for any custom domains you provided

On first deploy, watch the logs for the `frontend` build — `NEXT_PUBLIC_API_URL`
is baked in at that moment from `SERVICE_FQDN_BACKEND_8000`, so if you change
the backend domain later you must **rebuild** the frontend, not just restart.

## 4. (Optional) Seed the graph

After the first deploy succeeds, seed the demo data from the backend container:

```bash
# In Coolify: click the backend service → Terminal tab → run:
uv run python scripts/generate_data.py
```

Or skip seeding — the agent will populate the graph as users chat with it.

## 5. Connect a client

### Smoke test from your laptop

```bash
TOKEN=<one MCP_AUTH_TOKENS value>
curl -sN -H "authorization: Bearer $TOKEN" \
  https://cg-mcp.example.com/sse | head -3
```

Expect:

```
event: endpoint
data: /messages/?session_id=...
```

### Pi extension

```bash
export MCP_URL=https://cg-mcp.example.com/sse
export MCP_AUTH_TOKEN=<one of the tokens>
pi -p "what services are degraded?"
```

The `.pi/extensions/neo4j-memory` extension (one level up from this dir)
reads both env vars and connects to your deployed proxy.

## Troubleshooting

### Long-lived SSE connections drop after ~30 seconds

Coolify's global Traefik has a default idle timeout. Bump it:

**Settings → Proxy → Add custom config:**
```yaml
entryPoints:
  https:
    transport:
      respondingTimeouts:
        idleTimeout: 3600s
```

The compose file already sets `flushInterval=10ms` on the `mcpproxy`
service, so SSE events should stream immediately without buffering.

### `NEXT_PUBLIC_API_URL` is wrong after changing the backend domain

`NEXT_PUBLIC_*` vars are baked into the Next.js bundle at build time, not
runtime. Click **Redeploy** (not just Restart) on the frontend service.

### Frontend can't reach backend (CORS errors)

`CORS_ORIGINS` is set from `SERVICE_FQDN_FRONTEND_3000`. If you changed the
frontend domain after first deploy, redeploy the backend so it picks up the
new value.

### Token rotation

Edit `MCP_AUTH_TOKENS` in Coolify (comma-separated allowlist), then restart
just the `mcpproxy` service. Old tokens stop working immediately. No
backend or neo4j restart needed.

## Notes

- **No JWT support yet.** Static bearer tokens only. Swap `_check_auth` in
  `mcp-proxy/main.py` for a JWKS validator if you want OAuth.
- **No rate limiting.** Add `slowapi` to `mcp-proxy/main.py` if needed.
- **Neo4j memory.** The compose file sets a 2G heap. Bump it if your graph
  grows past ~100K nodes.
