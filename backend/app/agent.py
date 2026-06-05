"""Software Engineering AI Agent — PydanticAI implementation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

from app.config import settings


# Ensure ANTHROPIC_API_KEY env var is set before PydanticAI creates the provider.
# pydantic-settings may load an empty value from the shell env, overriding .env.
if not os.environ.get("ANTHROPIC_API_KEY"):
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    else:
        from dotenv import dotenv_values
        _key = dotenv_values("../.env").get("ANTHROPIC_API_KEY", "")
        if _key:
            os.environ["ANTHROPIC_API_KEY"] = _key

from pydantic_ai import Agent, RunContext

from app.context_graph_client import execute_cypher, get_schema
from app.memory import store_message, get_context, resolve_session_id


SYSTEM_PROMPT = """You are an AI engineering intelligence assistant with access to a comprehensive
knowledge graph of software development data. You help engineering teams analyze
their repositories, issues, pull requests, deployments, services, and incidents.

Your capabilities include:
- Searching code repositories, issues, and pull requests
- Analyzing service dependencies and health status
- Tracing deployment impact and incident root causes
- Identifying patterns in engineering workflows
- Finding similar past incidents and decisions

Always provide specific, actionable insights based on the data in the knowledge graph.
When discussing incidents, prioritize clarity about impact and resolution steps.


IMPORTANT: You MUST use the available tools to query the knowledge graph before answering any question about the data. Never guess or make up information — always use tools to look up actual data from the graph. If a user asks a question, identify which tool(s) can help answer it and call them.

CRITICAL: Call tools DIRECTLY without any introductory text. Do NOT say "I'll search for..." or "Let me look up..." before calling a tool — just call the tool immediately. Only generate text AFTER you have received the tool results and are ready to provide your final answer.

When writing Cypher queries with run_cypher:
- Never combine ORDER BY with DISTINCT or aggregation in the same RETURN clause — use a WITH clause first
- Always LIMIT results (default LIMIT 25) to avoid overwhelming responses
- Use toLower() for case-insensitive matching
- If a query fails, try a simpler approach rather than repeating the same pattern"""



@dataclass
class AgentDeps:
    """Dependencies injected into the agent."""
    session_id: str


agent = Agent(
    "anthropic:claude-sonnet-4-20250514",
    system_prompt=SYSTEM_PROMPT,
    deps_type=AgentDeps,
    retries=2,
)

# ---------------------------------------------------------------------------
# Agent tools — domain-specific for Software Engineering
# ---------------------------------------------------------------------------

@agent.tool
async def search_developer(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search for developers by name or role"""
    cypher = """MATCH (p:Person)
    WHERE toLower(p.name) CONTAINS toLower($query)
       OR toLower(coalesce(p.role, '')) CONTAINS toLower($query)
    OPTIONAL MATCH (p)-[r]-(related)
    RETURN p, type(r) AS rel_type, related
    LIMIT 20
"""
    params = {
        "query": query,
    }
    result = await execute_cypher(cypher, params, tool_name="search_developer")
    return json.dumps(result, default=str)

@agent.tool
async def get_service_health(ctx: RunContext[AgentDeps], name: str) -> str:
    """Get the health status and dependencies of a service"""
    cypher = """MATCH (s:Service {name: $name})
    OPTIONAL MATCH (s)-[:DEPENDS_ON]->(dep:Service)
    OPTIONAL MATCH (d:Deployment)-[:DEPLOYED_TO]->(s)
    OPTIONAL MATCH (i:Incident)-[:AFFECTED]->(s)
    WHERE i.status <> 'resolved'
    RETURN s, collect(DISTINCT dep) AS dependencies,
           collect(DISTINCT d) AS recent_deployments,
           collect(DISTINCT i) AS active_incidents
"""
    params = {
        "name": name,
    }
    result = await execute_cypher(cypher, params, tool_name="get_service_health")
    return json.dumps(result, default=str)

@agent.tool
async def find_similar_incidents(ctx: RunContext[AgentDeps], incident_id: str) -> str:
    """Find past incidents similar to a current one"""
    cypher = """MATCH (i:Incident {incident_id: $incident_id})
    CALL db.index.vector.queryNodes('incident_embeddings', 5, i.embedding)
    YIELD node, score
    WHERE node.incident_id <> $incident_id
    RETURN node AS similar_incident, score
    ORDER BY score DESC
"""
    params = {
        "incident_id": incident_id,
    }
    result = await execute_cypher(cypher, params, tool_name="find_similar_incidents")
    return json.dumps(result, default=str)

@agent.tool
async def get_deployment_history(ctx: RunContext[AgentDeps], service: str, limit: int = 10) -> str:
    """Get deployment history for a service"""
    cypher = """MATCH (d:Deployment)-[:DEPLOYED_TO]->(s:Service {name: $service})
    OPTIONAL MATCH (d)-[:TRIGGERED_BY]->(pr:PullRequest)
    OPTIONAL MATCH (d)-[:CAUSED_INCIDENT]->(i:Incident)
    RETURN d, pr, i
    ORDER BY d.date DESC
    LIMIT $limit
"""
    params = {
        "service": service,
        "limit": limit,
    }
    result = await execute_cypher(cypher, params, tool_name="get_deployment_history")
    return json.dumps(result, default=str)

@agent.tool
async def get_pr_impact(ctx: RunContext[AgentDeps], pr_id: str) -> str:
    """Trace the impact of a pull request through deployments and incidents"""
    cypher = """MATCH (pr:PullRequest {pr_id: $pr_id})
    OPTIONAL MATCH (pr)<-[:TRIGGERED_BY]-(d:Deployment)-[:DEPLOYED_TO]->(s:Service)
    OPTIONAL MATCH (d)-[:CAUSED_INCIDENT]->(i:Incident)
    RETURN pr, collect(DISTINCT d) AS deployments,
           collect(DISTINCT s) AS services,
           collect(DISTINCT i) AS incidents
"""
    params = {
        "pr_id": pr_id,
    }
    result = await execute_cypher(cypher, params, tool_name="get_pr_impact")
    return json.dumps(result, default=str)

@agent.tool
async def list_repositories(ctx: RunContext[AgentDeps], limit: str) -> str:
    """List Repository records with optional limit"""
    cypher = """MATCH (n:Repository)
    RETURN n
    ORDER BY n.name
    LIMIT toInteger($limit)
"""
    params = {
        "limit": limit,
    }
    result = await execute_cypher(cypher, params, tool_name="list_repositories")
    return json.dumps(result, default=str)

@agent.tool
async def get_repository_by_name(ctx: RunContext[AgentDeps], name: str) -> str:
    """Get a specific Repository by name with all connections"""
    cypher = """MATCH (n:Repository {name: $name})
    OPTIONAL MATCH (n)-[r]-(related)
    RETURN n, type(r) AS relationship, labels(related) AS related_labels, related.name AS related_name
    LIMIT 50
"""
    params = {
        "name": name,
    }
    result = await execute_cypher(cypher, params, tool_name="get_repository_by_name")
    return json.dumps(result, default=str)



@agent.tool
async def run_cypher(ctx: RunContext[AgentDeps], query: str, parameters: str = "{}") -> str:
    """Execute a read-only Cypher query against the knowledge graph."""
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError:
        return json.dumps([{"error": "Invalid JSON parameters"}])
    params.setdefault("domain", settings.domain_id)
    try:
        result = await execute_cypher(query, params, tool_name="run_cypher")
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps([{"error": f"Cypher query failed: {e}"}])


@agent.tool
async def get_graph_schema(ctx: RunContext[AgentDeps]) -> str:
    """Get the knowledge graph schema (node labels and relationship types)."""
    result = await get_schema()
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------


async def handle_message(message: str, session_id: str | None = None) -> dict:
    """Handle an incoming chat message."""
    session_id = resolve_session_id(session_id)

    # Store user message (triggers entity extraction + preference detection)
    await store_message(session_id, "user", message)

    # Get rich context (messages + entities + preferences + traces)
    context = await get_context(session_id, query=message)
    history = context.get("messages", [])

    # Convert history to PydanticAI message format
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    message_history = []
    for msg in history:
        if msg["role"] == "user":
            message_history.append(
                ModelRequest(parts=[UserPromptPart(content=msg["content"])])
            )
        elif msg["role"] == "assistant":
            message_history.append(
                ModelResponse(parts=[TextPart(content=msg["content"])])
            )

    deps = AgentDeps(session_id=session_id)
    result = await agent.run(
        message, deps=deps, message_history=message_history
    )

    response_text = result.output or ""
    if not response_text.strip():
        response_text = "I searched the knowledge graph but couldn't find relevant results for your query. Could you try rephrasing your question?"
    assistant_result = await store_message(session_id, "assistant", response_text)

    return {
        "response": response_text,
        "session_id": session_id,
        "graph_data": None,
        "entities_extracted": (assistant_result or {}).get("entities", []),
        "preferences_detected": (assistant_result or {}).get("preferences", []),
    }


async def handle_message_stream(message: str, session_id: str | None = None) -> dict:
    """Handle a chat message with streaming text deltas via the collector event queue."""
    from app.context_graph_client import get_collector

    session_id = resolve_session_id(session_id)

    collector = get_collector()
    await store_message(session_id, "user", message)

    # Get rich context (messages + entities + preferences + traces)
    context = await get_context(session_id, query=message)
    history = context.get("messages", [])

    # Convert history to PydanticAI message format
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    message_history = []
    for msg in history:
        if msg["role"] == "user":
            message_history.append(
                ModelRequest(parts=[UserPromptPart(content=msg["content"])])
            )
        elif msg["role"] == "assistant":
            message_history.append(
                ModelResponse(parts=[TextPart(content=msg["content"])])
            )

    deps = AgentDeps(session_id=session_id)
    # Use agent.run() (not run_stream) so the full agent loop completes —
    # including all tool calls — before we emit the final text.
    # run_stream stops at the first text part, so it cuts off before tool
    # results are incorporated when Claude generates "I'll search..." + a tool
    # call in the same response.  Tool events (tool_start / tool_end) are still
    # pushed to the SSE queue by execute_cypher during the run.
    result = await agent.run(
        message, deps=deps, message_history=message_history
    )

    response_text = result.output or ""
    if not response_text.strip():
        response_text = "I searched the knowledge graph but couldn't find relevant results for your query. Could you try rephrasing your question?"

    collector.emit_text_delta(response_text)
    assistant_result = await store_message(session_id, "assistant", response_text)
    if assistant_result:
        collector.emit_entities_extracted(assistant_result.get("entities", []))
        collector.emit_preferences_detected(assistant_result.get("preferences", []))
    collector.emit_done(response_text, session_id)

    return {
        "response": response_text,
        "session_id": session_id,
        "graph_data": None,
    }
