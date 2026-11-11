"""The service-operations tools of the MCP 2026-07-28 developer demo, for mcp_server.py --demo.

mcp_server.py adds these only with --demo, so that the regression suite's server still lists only
get_weather. All data is fixed and simulated: no external API, no LLM, and no real system.

The scenario: an on-call engineer's MCP client finds the degraded service, reads its open incident,
gets a recommended action, and applies it. The tools return structured results (pydantic models),
which the SDK server sends as structuredContent, with a JSON text block.

Two 2026-07-28 features come from the SDK server, not from Envoy:
- Cache hints (SEP-2549): CACHE_HINTS puts ttlMs and cacheScope on the tools/list and
  server/discover results. The SDK client may then serve tools/list from its own cache.
- Multi round-trip requests (SEP-2322): apply_remediation needs the operator's approval. At
  2026-07-28 the SDK server answers the first tools/call with resultType "input_required",
  carrying an elicitation request and a sealed requestState. The client answers it, and calls
  again with inputResponses and the requestState; only that call runs the tool.
"""
from typing import Annotated, Literal

from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

# The server's version and instructions, in its server/discover result.
SERVER_VERSION = "1.0.0"
INSTRUCTIONS = ("Simulated service-operations tools for the Envoy MCP filter demo: find a degraded "
                "service, read its incident, get a recommended action, and apply it. All data is "
                "fixed; no tool changes a real system.")
# Freshness hints that the SDK server puts on these cacheable results.
CACHE_HINTS = {
    "tools/list": CacheHint(ttl_ms=60_000, scope="public"),
    "server/discover": CacheHint(ttl_ms=300_000, scope="public"),
}
# When the simulated health data was taken.
SNAPSHOT_TIME = "2026-09-15T14:05:00Z"

SERVICES = {
    "checkout": {"team": "payments", "tier": "critical", "version": "v2.15.0"},
    "payments-api": {"team": "payments", "tier": "critical", "version": "v5.3.1"},
    "inventory": {"team": "fulfillment", "tier": "standard", "version": "v1.22.4"},
    "search": {"team": "discovery", "tier": "standard", "version": "v3.8.0"},
}
HEALTH = {
    "checkout": {"status": "degraded", "error_rate_percent": 7.8, "p99_latency_ms": 2140,
                 "requests_per_minute": 4200, "slo_error_rate_percent": 1.0},
    "payments-api": {"status": "healthy", "error_rate_percent": 0.2, "p99_latency_ms": 180,
                     "requests_per_minute": 3900, "slo_error_rate_percent": 0.5},
    "inventory": {"status": "healthy", "error_rate_percent": 0.4, "p99_latency_ms": 95,
                  "requests_per_minute": 2600, "slo_error_rate_percent": 1.0},
    "search": {"status": "healthy", "error_rate_percent": 0.1, "p99_latency_ms": 240,
               "requests_per_minute": 7100, "slo_error_rate_percent": 1.0},
}
INCIDENTS = {
    "checkout": {
        "incident_id": "INC-2041",
        "severity": "SEV-2",
        "status": "investigating",
        "title": "Elevated HTTP 503s on POST /checkout after the v2.15.0 rollout",
        "started_at": "2026-09-15T13:47:00Z",
        "impact": "7.8% of checkout requests fail with HTTP 503; affected users cannot place "
                  "orders",
        "suspected_cause": "v2.15.0 lowered the payments-api client's connection pool from 64 to "
                           "8, so requests time out waiting for a connection",
        "related_change": "deploy-8812: checkout v2.14.3 -> v2.15.0 at 13:42Z",
    },
}
RECOMMENDATIONS = {
    ("checkout", "INC-2041"): {
        "action": "rollback",
        "summary": "Roll back checkout from v2.15.0 to v2.14.3",
        "steps": [
            "Pause the v2.15.0 rollout (deploy-8812)",
            "Roll back checkout to v2.14.3",
            "Watch the 5xx rate fall below the 1.0% SLO",
            "Restore the payments-api pool size to 64 before re-releasing v2.15.x",
        ],
        "risk": "low",
        "expected_recovery_minutes": 10,
        "runbook": "runbooks/checkout/rollback.md",
    },
}


class ServiceSummary(BaseModel):
    name: str
    team: str
    tier: Literal["critical", "standard"]
    version: str


class ServiceList(BaseModel):
    services: list[ServiceSummary]


class ServiceHealth(BaseModel):
    service: str
    status: Literal["healthy", "degraded", "down"]
    error_rate_percent: float
    p99_latency_ms: int
    requests_per_minute: int
    slo_error_rate_percent: float
    checked_at: str


class Incident(BaseModel):
    service: str
    incident_id: str
    severity: str
    status: str
    title: str
    started_at: str
    impact: str
    suspected_cause: str
    related_change: str


class Recommendation(BaseModel):
    service: str
    incident_id: str
    action: str
    summary: str
    steps: list[str]
    risk: str
    expected_recovery_minutes: int
    runbook: str


class Approval(BaseModel):
    """What apply_remediation asks the operator. An elicitation schema has primitive fields only."""
    approve: bool = Field(description="Approve the remediation")
    operator: str = Field(description="Who approves it")


class RemediationResult(BaseModel):
    service: str
    incident_id: str
    action: str
    approved_by: str
    status: Literal["simulated"]
    detail: str


def known_service(service):
    if service not in SERVICES:
        raise ToolError(f"Unknown service {service!r}. Known services: {', '.join(SERVICES)}")
    return service


def open_recommendation(service, incident_id):
    known_service(service)
    recommendation = RECOMMENDATIONS.get((service, incident_id))
    if recommendation is None:
        raise ToolError(f"{incident_id!r} is not an open incident of {service!r}")
    return recommendation


def list_services() -> ServiceList:
    """List the services of the simulated production fleet."""
    return ServiceList(
        services=[ServiceSummary(name=name, **info) for name, info in SERVICES.items()])


def get_service_health(service: str) -> ServiceHealth:
    """Get the current health of a service: status, error rate and p99 latency."""
    return ServiceHealth(
        service=known_service(service), checked_at=SNAPSHOT_TIME, **HEALTH[service])


def get_incident(service: str) -> Incident:
    """Get the open incident of a service."""
    if known_service(service) not in INCIDENTS:
        raise ToolError(f"{service!r} has no open incident")
    return Incident(service=service, **INCIDENTS[service])


def recommend_action(service: str, incident_id: str) -> Recommendation:
    """Recommend a remediation for an open incident of a service."""
    return Recommendation(service=service, incident_id=incident_id,
                          **open_recommendation(service, incident_id))


def request_approval(service: str, incident_id: str) -> Elicit[Approval]:
    """apply_remediation's resolver: asks the client for the operator's approval."""
    summary = open_recommendation(service, incident_id)["summary"]
    return Elicit(f"Approve this simulated remediation of {incident_id}? {summary}.", Approval)


def apply_remediation(
        service: str, incident_id: str,
        approval: Annotated[Approval, Resolve(request_approval)]) -> RemediationResult:
    """Apply the recommended remediation of an incident, once the operator approves it.

    Simulated: no real system changes.
    """
    recommendation = open_recommendation(service, incident_id)
    if not approval.approve:
        raise ToolError(f"{approval.operator} did not approve the remediation of {incident_id}")
    return RemediationResult(
        service=service,
        incident_id=incident_id,
        action=recommendation["action"],
        approved_by=approval.operator,
        status="simulated",
        detail=f"Simulated: {recommendation['summary']}. No real system was changed.")


TOOLS = (list_services, get_service_health, get_incident, recommend_action, apply_remediation)


def register(server):
    """Adds the demo's tools to an MCPServer."""
    for tool in TOOLS:
        server.tool()(tool)
