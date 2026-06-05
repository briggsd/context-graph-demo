# Deploying to Coolify

This stack ships as five services in `docker-compose.coolify.yml`:

| Service     | Purpose                              | Public?        |
|-------------|--------------------------------------|----------------|
| `neo4j`     | Graph database + GDS + APOC          | No (internal)  |
| `backend`   | FastAPI app + agent                  | Yes            |
| `frontend`  | Next.js UI                           | Yes            |
| `mcp-server`| Neo4j-agent-memory MCP over SSE      | No (internal)  |
| `mcp-proxy` | Bearer-auth front for `mcp-server`   | Yes            |

The MCP server is intentionally **never exposed directly** — clients go through
`mcp-proxy`, which checks `Authorization: Bearer <token>` before forwarding.

## 1. Prerequisites

- A Coolify instance (v4+)
- A GitHub repo containing this directory
- DNS records for the three public services pointing at the Coolify host

## 2. Create the resource in Coolify

1. **New Resource → Docker Compose → Public Repository (or Private + GitHub App)**
2. Repository: this repo
3. Branch: `main`
4. Compose file path: `docker-compose.coolify.yml`

## 3. Environment variables

In Coolify's "Environment Variables" tab, set these as **secrets**:

```
ANTHROPIC_API_KEY=sk-ant-...
NEO4J_PASSWORD=<openssl rand -hex 24>
MCP_AUTH_TOKENS=<openssl rand -hex 32>,<another-if-multi-tenant>
```

And these as plain build-time variables (used by Next.js at `docker build`):

```
FRONTEND_DOMAIN=cg.example.com
BACKEND_DOMAIN=cg-api.example.com
```

> ⚠️ Coolify only injects build args into a service if they're declared. The
> compose file already does this for `frontend.build.args.NEXT_PUBLIC_API_URL`.

## 4. Assign domains

In each service's "Domains" tab:

| Service     | Domain                           | Container port |
|-------------|----------------------------------|----------------|
| `frontend`  | `cg.example.com`                 | 3000           |
| `backend`   | `cg-api.example.com`             | 8000           |
| `mcp-proxy` | `cg-mcp.example.com`             | 9091           |

Leave `neo4j` and `mcp-server` without domains — they stay on the internal
compose network only.

## 5. SSE-safe Traefik labels (for `mcp-proxy`)

In Coolify's "Container Labels" for `mcp-proxy`, add:

```
traefik.http.middlewares.mcp-sse.headers.customResponseHeaders.X-Accel-Buffering=no
traefik.http.routers.mcp-proxy.middlewares=mcp-sse
traefik.http.services.mcp-proxy.loadbalancer.responseForwarding.flushInterval=10ms
```

And bump Coolify's global proxy read timeout to `3600s` so long-lived SSE
connections don't get killed.

## 6. Deploy

Click "Deploy". Coolify will:
- Build `Dockerfile.backend`, `Dockerfile.frontend`, and `mcp-proxy/Dockerfile`
- Pull `neo4j:5.26.0`
- Wire up Traefik with auto Let's Encrypt for the three public domains

## 7. Seed the graph (one-time)

After the first deploy, exec into the backend to load fixtures:

```bash
docker compose -f docker-compose.coolify.yml exec backend \
  uv run python scripts/generate_data.py
```

Or skip seeding entirely if you want an empty graph that the agent populates
as users chat.

## 8. Connect a client

### Pi extension

```bash
export MCP_URL=https://cg-mcp.example.com/sse
export MCP_AUTH_TOKEN=<one of MCP_AUTH_TOKENS>
pi   # the .pi/extensions/neo4j-memory extension auto-discovers and connects
```

### Smoke test from anywhere

```bash
curl -sN -H "authorization: Bearer $MCP_AUTH_TOKEN" \
  https://cg-mcp.example.com/sse | head -3
```

Expect:

```
event: endpoint
data: /messages/?session_id=...
```

## 9. Rotating a token

Edit `MCP_AUTH_TOKENS` in Coolify (comma-separated allowlist), restart
`mcp-proxy`. Old tokens stop working immediately. No backend restart needed.

## Notes & gotchas

- **`NEXT_PUBLIC_API_URL` is baked at build time.** Changing `BACKEND_DOMAIN`
  later requires a frontend rebuild, not just a restart.
- **Neo4j memory.** The compose file sets `NEO4J_server_memory_heap_max__size=2G`.
  Bump it if the graph grows past ~100K nodes.
- **MCP proxy has no rate limiting.** Add `slowapi` to `mcp-proxy/main.py` if
  you need per-token rate limits.
- **No JWT support yet.** Static bearer tokens only. To swap to JWT/OAuth,
  replace `_check_auth` in `mcp-proxy/main.py` with a JWKS validator.
