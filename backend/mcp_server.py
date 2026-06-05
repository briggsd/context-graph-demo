"""MCP server entry point with sentence-transformers embedding (384 dims).

Defaults to SSE transport on port 9090 so it runs as a persistent service
alongside the backend and frontend. Override with MCP_TRANSPORT=stdio for
Claude Desktop / stdio clients.
"""
import asyncio
import os

from neo4j_agent_memory.mcp.server import run_server

asyncio.run(
    run_server(
        neo4j_uri=os.environ.get("NEO4J_URI", "neo4j://localhost:7687"),
        neo4j_user=os.environ.get("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", "password"),
        profile="extended",
        embedding="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dimensions=384,
        transport=os.environ.get("MCP_TRANSPORT", "sse"),
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        # Railway injects PORT; fall back to MCP_PORT then 9090
        port=int(os.environ.get("PORT", os.environ.get("MCP_PORT", "9090"))),
    )
)
