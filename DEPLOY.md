# Deploying to Coolify — Definitive Guide

This document captures everything learned from a real deployment. Read the
**Gotchas** section before you start — it will save hours.

---

## Stack

| Service     | Public? | Purpose                            |
|-------------|---------|-------------------------------------|
| `neo4j`     | No      | Graph DB + GDS + APOC               |
| `mcp-server`| No      | MCP SSE server (internal)           |
| `backend`   | Yes     | FastAPI + AI agent                  |
| `frontend`  | Yes     | Next.js UI (BasicAuth protected)    |
| `mcpproxy`  | Yes     | Bearer-token auth proxy for MCP     |

Routing is handled via **explicit Traefik labels** in `docker-compose.coolify.yml`.
Raw compose mode is enabled in Coolify's DB (see below) so Coolify deploys
the file verbatim instead of running its broken parser.

---

## Prerequisites

- Coolify v4+ instance
- A GitHub repo containing this directory
- DNS wildcard pointed at the Coolify host (or individual A records per subdomain)
- AWS SSM access to the Coolify EC2 host (for operational tasks below)

---

## First-time setup

### 1. Create the resource

1. **New Resource → Docker Compose → Public Repository**
2. Repository: `https://github.com/briggsd/context-graph-demo`
3. Branch: `main`
4. **Compose file path: `docker-compose.coolify.yml`** ← easy to miss
5. Save

### 2. Set environment variables

In the **Environment Variables** tab. Mark secrets with "Is Secret".

```
# Secrets
ANTHROPIC_API_KEY    = sk-ant-...
NEO4J_PASSWORD       = <openssl rand -hex 24>
MCP_AUTH_TOKENS      = <openssl rand -hex 32>

# Web UI BasicAuth (frontend only — see auth section)
# Generate: python3 -c "import hashlib,base64; print('user:{SHA}'+base64.b64encode(hashlib.sha1(b'yourpassword').digest()).decode())"
WEB_AUTH_USERS       = admin:{SHA}<hash>
```

> ⚠️ **Critical**: `SERVICE_FQDN_MCPPROXY` is NOT auto-generated correctly by
> Coolify (known parser bug). You must add it manually after first deploy — see
> the **Post-deploy steps** section below.

### 3. Enable raw compose mode

Coolify's Docker Compose parser has a bug that corrupts `SERVICE_FQDN_*`
environment variables, causing `docker compose build` to fail with:

```
non-string key in services.frontend.environment: 0
```

Workaround: enable raw compose mode via the DB so the file is deployed
verbatim. Run this **once** via AWS SSM after creating the resource:

```bash
# Get the app ID first
docker exec coolify-db psql -U coolify -t -A -c \
  "SELECT id, name FROM applications ORDER BY id DESC LIMIT 5;"

# Then enable raw mode (replace 31 with your actual app ID)
cat > /tmp/raw.php <<'PHP'
<?php
require "/var/www/html/vendor/autoload.php";
$app = require_once "/var/www/html/bootstrap/app.php";
$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();
$application = \App\Models\Application::find(31); // <-- your app ID
$settings = $application->settings;
$settings->is_raw_compose_deployment_enabled = true;
$settings->save();
echo "Raw compose mode: " . ($settings->is_raw_compose_deployment_enabled ? "ENABLED" : "disabled") . "\n";
PHP
docker cp /tmp/raw.php coolify:/tmp/raw.php
docker exec coolify php /tmp/raw.php
```

### 4. Add persistent env vars to Coolify's DB

Coolify regenerates `.env` from its DB on every deploy, so any manual `.env`
edits get wiped. These vars must live in the DB. Run once via SSM:

```bash
# Replace APP_ID and UUID with your values
cat > /tmp/add_vars.php <<'PHP'
<?php
require "/var/www/html/vendor/autoload.php";
$app = require_once "/var/www/html/bootstrap/app.php";
$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

$appId = 31;   // <-- your app ID
$uuid  = 'ofzm4a6lh1kq23pnl1kuu19f';  // <-- your resource UUID (from the FQDN pattern)

// Get UUID from: docker exec coolify-db psql -U coolify -t -A -c \
//   "SELECT uuid FROM applications WHERE id=31;"

$toUpsert = [
    'WEB_AUTH_USERS'         => 'admin:{SHA}RZ7o5bBpTyaT882U8QukSIEMrp0=',  // change this!
    'SERVICE_FQDN_MCPPROXY'  => "mcpproxy-{$uuid}.apps.circlebackhq.com",
    'SERVICE_URL_MCPPROXY'   => "https://mcpproxy-{$uuid}.apps.circlebackhq.com",
    'SERVICE_FQDN_MCPPROXY_9091' => "mcpproxy-{$uuid}.apps.circlebackhq.com:9091",
];

foreach ($toUpsert as $key => $value) {
    \App\Models\EnvironmentVariable::where([
        'resourceable_id' => $appId, 'resourceable_type' => 'App\Models\Application', 'key' => $key
    ])->delete();
    $env = new \App\Models\EnvironmentVariable();
    $env->key = $key; $env->value = $value;
    $env->resourceable_type = 'App\Models\Application';
    $env->resourceable_id = $appId;
    $env->is_preview = false; $env->is_runtime = true; $env->is_buildtime = true;
    $env->uuid = \Illuminate\Support\Str::uuid();
    $env->version = '4.0.0-beta.239';
    $env->save();
    echo "Saved: {$key}\n";
}
PHP
docker cp /tmp/add_vars.php coolify:/tmp/add_vars.php
docker exec coolify php /tmp/add_vars.php
```

### 5. Deploy

Click **Deploy**. First build takes ~10 minutes (Python + spaCy + npm).
Expect the backend image to be ~5GB — don't be alarmed.

### 6. Post-deploy steps

#### a) Fix mcpproxy routing (needed after EVERY first/fresh deploy)

The `SERVICE_FQDN_MCPPROXY` env var isn't picked up by Docker Compose at
startup because Coolify's parser doesn't write it to the `.env` file correctly.
Fix it via SSM after each deploy:

```bash
UUID="ofzm4a6lh1kq23pnl1kuu19f"   # <-- your UUID
ENVFILE="/data/coolify/applications/${UUID}/.env"
COMPOSE="/data/coolify/applications/${UUID}/docker-compose.yaml"

python3 - <<PYEOF
import re
path = "${ENVFILE}"
uuid = "${UUID}"
content = open(path).read()
content = re.sub(r'\n?SERVICE_FQDN_MCPPROXY=.*', '', content)
content = re.sub(r'\n?SERVICE_URL_MCPPROXY=.*', '', content)
content = content.rstrip('\n') + '\n'
content += f'SERVICE_FQDN_MCPPROXY=mcpproxy-{uuid}.apps.circlebackhq.com\n'
content += f'SERVICE_URL_MCPPROXY=https://mcpproxy-{uuid}.apps.circlebackhq.com\n'
open(path, 'w').write(content)
print("Fixed")
PYEOF

docker compose --project-name $UUID \
  --project-directory /data/coolify/applications/$UUID \
  -f $COMPOSE up -d --no-deps --force-recreate mcpproxy
```

#### b) Seed demo data (one-time)

The `data/fixtures.json` is in the repo but not in the backend Docker image
(build context is `./backend` only). Copy it in and seed:

```bash
UUID="ofzm4a6lh1kq23pnl1kuu19f"

# Download fixtures from GitHub onto the host, then copy into the container
curl -sL https://raw.githubusercontent.com/briggsd/context-graph-demo/main/data/fixtures.json \
  -o /tmp/fixtures.json

docker exec ${UUID}-backend-1 mkdir -p /data
docker cp /tmp/fixtures.json ${UUID}-backend-1:/data/fixtures.json
docker exec ${UUID}-backend-1 uv run python scripts/generate_data.py
```

---

## Auth

| Service   | Auth method       | Credentials / tokens          |
|-----------|-------------------|-------------------------------|
| Frontend  | HTTP BasicAuth    | `admin` / `context-graph-2026` (change via `WEB_AUTH_USERS`) |
| Backend   | None (CORS only)  | Not directly accessible from other origins |
| MCPProxy  | Bearer token      | Value of `MCP_AUTH_TOKENS` env var |

**Why the backend has no BasicAuth:** the frontend JS calls `/api/*` on the
backend cross-origin. Browsers don't send BasicAuth credentials to a
different origin, so adding auth to the backend breaks the UI. The backend
is protected by CORS (`CORS_ORIGINS=https://frontend-domain`) and is not
directly port-exposed.

**Changing the web UI password:**
```bash
python3 -c "import hashlib,base64; print('admin:{SHA}'+base64.b64encode(hashlib.sha1(b'newpassword').digest()).decode())"
# Set the output as WEB_AUTH_USERS in Coolify's Environment Variables tab
# then run the add_vars.php script above to persist it to the DB
# then force-recreate the backend container to pick up the new label
```

**Rotating MCP tokens:** edit `MCP_AUTH_TOKENS` in Coolify's env vars tab
(comma-separated for multiple clients), re-run `add_vars.php`, then restart
the `mcpproxy` container.

---

## Connecting clients

### Smoke test (MCP)
```bash
TOKEN=<your MCP_AUTH_TOKENS value>
curl -sN -H "authorization: Bearer $TOKEN" \
  https://mcpproxy-<uuid>.apps.circlebackhq.com/sse | head -3
# expect:
# event: endpoint
# data: /messages/?session_id=...
```

### pi extension
```bash
export MCP_URL=https://mcpproxy-<uuid>.apps.circlebackhq.com/sse
export MCP_AUTH_TOKEN=<your token>
cd /path/to/workspace   # parent of where .pi/extensions/neo4j-memory/ lives
pi
```

---

## Operational runbook

### Traefik 503 on all services

If all public services return 503 and Traefik logs show 0 lines:

```bash
docker restart coolify-proxy
```

**Root cause:** Coolify's Traefik runs a Docker-provider goroutine that can
crash silently. The `/ping` endpoint stays healthy (different goroutine) but
route discovery stops. A container restart reinitializes the provider.
This happens occasionally after bad deploys that push invalid Traefik labels.

### Disk space during build

The backend image is large (~5GB) due to PyTorch/spaCy/NVIDIA dependencies.
If a build fails with "no space left on device":

```bash
docker system prune -f              # remove stopped containers + dangling images
docker image prune -a -f --filter "until=2h"   # remove old images
df -h /                             # verify free space
```

Then trigger a redeploy.

### SERVICE_FQDN_MCPPROXY after redeploy

After every full redeploy (not just restart), re-run the mcpproxy fix in
step 6a above. Coolify's parser generates `SERVICE_FQDN_MCPPROXY` with the
wrong value (`<root-domain>:8000` instead of `mcpproxy-<uuid>.apps...`).

### Check running containers

```bash
docker ps --format "{{.Names}}: {{.Status}}" | grep <uuid>
```

All five should show "Up":
- `<uuid>-neo4j-1` (healthy)
- `<uuid>-backend-1`
- `<uuid>-mcp-server-1`
- `<uuid>-mcpproxy-1`
- `<uuid>-frontend-1`

---

## Known Coolify bugs / limitations

| Bug | Workaround |
|-----|------------|
| `SERVICE_FQDN_*` parser corrupts list-style env vars → `non-string key` build crash | Raw compose mode (step 3) |
| `SERVICE_FQDN_MCPPROXY` generates wrong value | Manual DB insert + `.env` fix after each deploy (step 6a) |
| Traefik Docker-provider goroutine crashes silently | `docker restart coolify-proxy` |
| `.env` is regenerated from DB on every deploy, wiping manual edits | Store persistent vars in DB via `add_vars.php` (step 4) |
| BasicAuth defined on container A not always accessible to router on container B | Define middleware and router on the same container |
| `NEXT_PUBLIC_*` vars are build-time baked — wrong value if `SERVICE_URL_BACKEND` is empty during build | `SERVICE_URL_BACKEND` (with `https://`) not `SERVICE_FQDN_BACKEND` (hostname only) |

---

## URLs (this deployment)

| Service  | URL |
|----------|-----|
| Frontend | https://frontend-ofzm4a6lh1kq23pnl1kuu19f.apps.circlebackhq.com |
| Backend API | https://backend-ofzm4a6lh1kq23pnl1kuu19f.apps.circlebackhq.com |
| MCP proxy | https://mcpproxy-ofzm4a6lh1kq23pnl1kuu19f.apps.circlebackhq.com |
| Neo4j Browser | Not exposed (internal only) |
