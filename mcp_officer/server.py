# -*- coding: utf-8 -*-
"""
Block Officer MCP Server for Sewa Setu.
Exposes Streamable HTTP endpoint for external AI clients and departmental officer assistants.
Strictly restricted to authorized departmental tools.
"""

import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp_common.auth import OfficerTokenVerifier
from mcp_officer import tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sewasetu.mcp.officer")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
OFFICER_AUDIENCE = os.environ.get("OFFICER_MCP_AUDIENCE", f"{PUBLIC_BASE_URL}/mcp/officer")
PORT = int(os.environ.get("OFFICER_MCP_PORT", 8002))
HOST = os.environ.get("OFFICER_MCP_HOST", "0.0.0.0")

officer_verifier = OfficerTokenVerifier(expected_audience=OFFICER_AUDIENCE)

auth_settings = AuthSettings(
    issuer_url=PUBLIC_BASE_URL,
    resource_server_url=OFFICER_AUDIENCE,
    required_scopes=["officer"],
    validate_token_resource=False
)

officer_mcp = FastMCP(
    name="SewaSetu Block Officer Assistant",
    instructions="""
    You are the official Sewa Setu Block Officer Assistant for the Department of Social Welfare.
    You assist Block Welfare Officers and administrators with reviewing pension applications,
    monitoring SLA compliance, inspecting audit trails, and executing approvals or rejections.
    Only authorized departmental officers may use these tools.
    Every approval or rejection requires explicit officer confirmation and records an immutable audit trail.
    Citizen tokens are strictly rejected from calling these tools.
    """,
    token_verifier=officer_verifier,
    auth=auth_settings,
    streamable_http_path="/mcp",
    host=HOST,
    port=PORT
)

# Register ONLY Officer-authorized tools
officer_mcp.add_tool(
    tools.search_applications,
    name="search_applications",
    description="Search applications across the database by application number, 10-digit mobile, or applicant name."
)

officer_mcp.add_tool(
    tools.get_application_details,
    name="get_application_details",
    description="Get complete application details including applicant record, document path, and audit history."
)

officer_mcp.add_tool(
    tools.list_pending_applications,
    name="list_pending_applications",
    description="List pending applications ordered from oldest to newest to prioritize statutory SLA compliance."
)

officer_mcp.add_tool(
    tools.filter_applications,
    name="filter_applications",
    description="Filter applications by status and/or block with pagination."
)

officer_mcp.add_tool(
    tools.get_application_audit_history,
    name="get_application_audit_history",
    description="Retrieve the complete audit history showing every action, officer, and statutory note."
)

officer_mcp.add_tool(
    tools.approve_application,
    name="approve_application",
    description="Approve a pending pension application. Requires confirmation (confirm=True). Records audit trail."
)

officer_mcp.add_tool(
    tools.reject_application,
    name="reject_application",
    description="Reject a pending pension application with required statutory reason. Requires confirmation (confirm=True)."
)

officer_mcp.add_tool(
    tools.get_block_application_statistics,
    name="get_block_application_statistics",
    description="Get aggregated welfare statistics: total volume, status distribution, overdue cases, and block counts."
)

officer_mcp.add_tool(
    tools.get_sla_breach_report,
    name="get_sla_breach_report",
    description="Retrieve pending applications that have breached or are about to breach the statutory 15-day SLA."
)


def create_asgi_app():
    """Return the Streamable HTTP Starlette ASGI application with root / alias."""
    app = officer_mcp.streamable_http_app()
    from starlette.routing import Route
    mcp_route = [r for r in app.routes if getattr(r, "path", "") == "/mcp"]
    if mcp_route:
        app.routes.insert(0, Route("/", endpoint=mcp_route[0].endpoint, methods=["GET", "POST", "OPTIONS", "DELETE"]))
    return app


app = create_asgi_app()

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Block Officer MCP Server on {HOST}:{PORT}/mcp")
    uvicorn.run(app, host=HOST, port=PORT)
