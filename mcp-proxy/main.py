"""Bearer-auth reverse proxy for the neo4j-agent-memory MCP SSE server.

Routes:
  GET  /sse           — opens upstream SSE stream (long-lived)
  POST /messages/     — forwards client→server JSON-RPC messages
  GET  /health        — unauthenticated liveness probe

Auth: every /sse and /messages request requires `Authorization: Bearer <token>`
where <token> is one of the comma-separated values in MCP_AUTH_TOKENS.
"""
from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp-proxy")

UPSTREAM = os.environ.get("MCP_UPSTREAM", "http://127.0.0.1:9090")
TOKENS = {t.strip() for t in os.environ.get("MCP_AUTH_TOKENS", "").split(",") if t.strip()}
if not TOKENS:
    raise RuntimeError("MCP_AUTH_TOKENS must be set (comma-separated bearer tokens)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No read timeout: SSE streams are long-lived.
    client = httpx.AsyncClient(
        base_url=UPSTREAM,
        timeout=httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0),
    )
    app.state.client = client
    log.info("mcp-proxy ready: upstream=%s tokens=%d", UPSTREAM, len(TOKENS))
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="mcp-proxy", lifespan=lifespan)


def _check_auth(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    # constant-time comparison against each valid token
    if not any(secrets.compare_digest(token, t) for t in TOKENS):
        log.warning("rejected request from %s: bad token", request.client.host if request.client else "?")
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "upstream": UPSTREAM}


@app.get("/sse")
async def sse_proxy(request: Request) -> StreamingResponse:
    _check_auth(request)
    client: httpx.AsyncClient = app.state.client
    log.info("sse open from %s", request.client.host if request.client else "?")

    async def stream() -> AsyncIterator[bytes]:
        try:
            async with client.stream(
                "GET",
                "/sse",
                headers={"accept": "text/event-stream"},
            ) as upstream:
                upstream.raise_for_status()
                async for chunk in upstream.aiter_raw():
                    yield chunk
        except httpx.HTTPError as exc:
            log.error("upstream sse error: %s", exc)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache, no-transform",
            "x-accel-buffering": "no",   # disable nginx/traefik buffering
            "connection": "keep-alive",
        },
    )


@app.post("/messages/")
async def messages_proxy(request: Request) -> Response:
    _check_auth(request)
    client: httpx.AsyncClient = app.state.client
    body = await request.body()
    upstream = await client.post(
        "/messages/",
        params=dict(request.query_params),
        content=body,
        headers={"content-type": request.headers.get("content-type", "application/json")},
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
