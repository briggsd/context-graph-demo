# Deploying to Railway

Railway is significantly simpler than Coolify for this stack: no Traefik labels,
no proxy configuration, no raw compose mode hacks. Each service gets its own
deployment with automatic HTTPS and a `*.up.railway.app` domain.

Services communicate internally via `<service-name>.railway.internal:<port>`.

---

## Prerequisites

- Railway account + CLI: `npm i -g @railway/cli && railway login`
- GitHub repo: `https://github.com/briggsd/context-graph-demo`

---

## 1. Create the project

```bash
railway init   # creates a new Railway project, name it "context-graph-demo"
```

Or create via the Railway dashboard: **New Project → Empty Project**.

---

## 2. Add Neo4j (Docker image service)

Railway doesn't have a Neo4j managed addon, so deploy it as a Docker image.

In the Railway dashboard:
1. **+ New Service → Docker Image**
2. Image: `neo4j:5.26.0`
3. Name the service: `neo4j`
4. Set environment variables:
   ```
   NEO4J_AUTH          = neo4j/<your-password>
   NEO4J_PLUGINS       = ["apoc", "graph-data-science"]
   NEO4J_server_memory_heap_max__size = 2G
   ```
5. Add a **Volume** mounted at `/data` for persistence
6. Neo4j is **not** given a public domain — internal only

Neo4j will be reachable internally at:
- Bolt: `neo4j.railway.internal:7687`
- HTTP: `neo4j.railway.internal:7474`

---

## 3. Add each application service

For each service below, go to **+ New Service → GitHub Repo → briggsd/context-graph-demo**.

### backend

| Setting | Value |
|---------|-------|
| Root Directory | `backend` |
| Dockerfile Path | `../Dockerfile.backend` (auto-detected from `railway.toml`) |
| Public domain | Yes (auto-assigned) |

**Environment variables:**
```
NEO4J_URI           = bolt://neo4j.railway.internal:7687
NEO4J_USERNAME      = neo4j
NEO4J_PASSWORD      = <same as neo4j service>
ANTHROPIC_API_KEY   = sk-ant-...
MEMORY_EMBEDDING    = sentence-transformers/all-MiniLM-L6-v2
MEMORY_BACKEND      = bolt
CORS_ORIGINS        = https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
```

### mcp-server

| Setting | Value |
|---------|-------|
| Root Directory | `/` (repo root) |
| Dockerfile Path | `mcp-server/Dockerfile` |
| Public domain | **No** — internal only |

**Environment variables:**
```
NEO4J_URI           = bolt://neo4j.railway.internal:7687
NEO4J_USERNAME      = neo4j
NEO4J_PASSWORD      = <same as neo4j service>
MEMORY_EMBEDDING    = sentence-transformers/all-MiniLM-L6-v2
MCP_TRANSPORT       = sse
MCP_HOST            = 0.0.0.0
```

### mcpproxy

| Setting | Value |
|---------|-------|
| Root Directory | `mcp-proxy` |
| Public domain | Yes (auto-assigned) |

**Environment variables:**
```
MCP_UPSTREAM        = http://mcp-server.railway.internal:${{mcp-server.PORT}}
MCP_AUTH_TOKENS     = <openssl rand -hex 32>
```

> `${{mcp-server.PORT}}` is a Railway reference variable — it resolves to the
> port that the `mcp-server` service is actually listening on.

### frontend

| Setting | Value |
|---------|-------|
| Root Directory | `frontend` |
| Dockerfile Path | `../Dockerfile.frontend` |
| Public domain | Yes (auto-assigned) |

**⚠️ IMPORTANT — deploy backend first, then set this:**
```
NEXT_PUBLIC_API_URL = https://${{backend.RAILWAY_PUBLIC_DOMAIN}}/api
```

`NEXT_PUBLIC_API_URL` is baked into the Next.js bundle at build time.
Railway resolves `${{backend.RAILWAY_PUBLIC_DOMAIN}}` before the build starts,
so this reference variable works correctly as a build arg — as long as the
backend service is already deployed and has a domain.

---

## 4. Deploy order

1. `neo4j` — let it become healthy first
2. `backend` — needs neo4j
3. `mcp-server` — needs neo4j
4. `mcpproxy` — needs mcp-server
5. `frontend` — set `NEXT_PUBLIC_API_URL` first, then deploy

---

## 5. Seed demo data (one-time)

Railway has a terminal in each service's dashboard. In the `backend` service:

```bash
# Download fixtures from GitHub
curl -sL https://raw.githubusercontent.com/briggsd/context-graph-demo/main/data/fixtures.json \
  -o /data/fixtures.json
mkdir -p /data
uv run python scripts/generate_data.py
```

Or use the Railway CLI:
```bash
railway run --service backend -- bash -c '
  mkdir -p /data &&
  curl -sL https://raw.githubusercontent.com/briggsd/context-graph-demo/main/data/fixtures.json -o /data/fixtures.json &&
  uv run python scripts/generate_data.py
'
```

---

## 6. Verify

```bash
# MCP proxy SSE
TOKEN=<your MCP_AUTH_TOKENS>
curl -sN -H "authorization: Bearer $TOKEN" \
  https://<mcpproxy-domain>.up.railway.app/sse | head -3
# expect: event: endpoint ...

# Backend health
curl https://<backend-domain>.up.railway.app/health
# expect: {"status":"ok",...}

# Frontend
open https://<frontend-domain>.up.railway.app
```

---

## Connect pi extension

```bash
export MCP_URL=https://<mcpproxy-domain>.up.railway.app/sse
export MCP_AUTH_TOKEN=<your token>
cd /path/to/workspace
pi
```

---

## Why Railway is simpler than Coolify

| Concern | Coolify | Railway |
|---------|---------|---------|
| Routing/SSL | Manual Traefik labels | Automatic |
| Service discovery | Docker network + IPs | `service.railway.internal` |
| Env vars | DB inserts via PHP + `.env` fixes | Dashboard + reference vars |
| Config persistence | Wipes on redeploy, needs DB hacks | Permanent in dashboard |
| Debugging | SSH + SSM + docker exec | Log streaming in dashboard |
| Proxy crashes | `docker restart coolify-proxy` | Managed, no proxy to restart |

---

## Cost estimate

Railway pricing (as of 2026): ~$5/month per service on the Hobby plan.
For 5 services + a volume for Neo4j, expect ~$30-40/month.

For a short-lived POC, use **Ephemeral Volumes** for Neo4j (no extra cost,
data lost on redeploy) and the trial credits.
