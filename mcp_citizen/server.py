# -*- coding: utf-8 -*-
"""
Citizen MCP Server for Sewa Setu.
Exposes Streamable HTTP endpoint for external AI clients and citizen assistants.
Strictly restricted to citizen-authorized tools.
"""

import os
import sys
import logging
from typing import Optional

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp.server.fastmcp import FastMCP
from mcp_common.auth import CitizenTokenVerifier
from mcp_citizen import tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sewasetu.mcp.citizen")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
CITIZEN_AUDIENCE = os.environ.get("CITIZEN_MCP_AUDIENCE", f"{PUBLIC_BASE_URL}/mcp/citizen")
PORT = int(os.environ.get("CITIZEN_MCP_PORT", 8001))
HOST = os.environ.get("CITIZEN_MCP_HOST", "0.0.0.0")

from mcp.server.auth.settings import AuthSettings

citizen_verifier = CitizenTokenVerifier(expected_audience=CITIZEN_AUDIENCE)

auth_settings = AuthSettings(
    issuer_url=PUBLIC_BASE_URL,
    resource_server_url=CITIZEN_AUDIENCE,
    required_scopes=["citizen"],
    validate_token_resource=False  # Handled within verifier for audience flexibility
)

citizen_mcp = FastMCP(
    name="SewaSetu Citizen Assistant",
    instructions="""
    You are the official Sewa Setu Citizen Welfare Assistant for the Government of Purvanchal.
    You assist senior citizens and applicants with the Old Age Pension Scheme.
    Be respectful, patient, clear, and reassuring. Avoid technical jargon.
    You can check eligibility, explain required documents, check application status,
    provide chronological timelines, and assist with application withdrawal upon explicit confirmation.
    You can ONLY access the records of the authenticated citizen.
    Never ask for passwords or OTPs.
    """,
    token_verifier=citizen_verifier,
    auth=auth_settings,
    streamable_http_path="/mcp",
    host=HOST,
    port=PORT
)

# Register ONLY Citizen-authorized tools
citizen_mcp.add_tool(
    tools.get_my_profile,
    name="get_my_profile",
    description="Retrieve your registered applicant profile (name, masked mobile, village, block, and masked bank info)."
)

citizen_mcp.add_tool(
    tools.get_my_application,
    name="get_my_application",
    description="Retrieve full details of your pension application (application number, status, submission date, village, block)."
)

citizen_mcp.add_tool(
    tools.check_application_status,
    name="check_application_status",
    description="Check the current status of your pension application in clear, simple language."
)

citizen_mcp.add_tool(
    tools.get_application_timeline,
    name="get_application_timeline",
    description="Retrieve chronological timeline history of events and actions on your application."
)

citizen_mcp.add_tool(
    tools.check_scheme_eligibility,
    name="check_scheme_eligibility",
    description="Check if an individual meets the scheme age (60+) and block criteria before applying."
)

citizen_mcp.add_tool(
    tools.get_required_documents,
    name="get_required_documents",
    description="Get the official checklist of required documents (age proof, bank details) for applying."
)

citizen_mcp.add_tool(
    tools.get_scheme_information,
    name="get_scheme_information",
    description="Get details about the Old Age Pension Scheme, monthly benefits (₹1,000/mo), and statutory rules."
)

citizen_mcp.add_tool(
    tools.withdraw_pending_application,
    name="withdraw_pending_application",
    description="Withdraw a pending application. Only pending applications can be withdrawn. Requires explicit confirmation (confirm=True)."
)

citizen_mcp.add_tool(
    tools.get_my_connected_applications,
    name="get_my_connected_applications",
    description="List third-party applications and AI assistants authorized to access your pension records."
)


def create_asgi_app():
    """Return the Streamable HTTP Starlette ASGI application with root / alias."""
    app = citizen_mcp.streamable_http_app()
    from starlette.routing import Route
    mcp_route = [r for r in app.routes if getattr(r, "path", "") == "/mcp"]
    if mcp_route:
        app.routes.insert(0, Route("/", endpoint=mcp_route[0].endpoint, methods=["GET", "POST", "OPTIONS", "DELETE"]))
    return app


app = create_asgi_app()

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Citizen MCP Server on {HOST}:{PORT}/mcp")
    uvicorn.run(app, host=HOST, port=PORT)
