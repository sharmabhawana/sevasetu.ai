# -*- coding: utf-8 -*-
"""
Security and isolation tests:
- Zero cross-exposure between Citizen and Officer MCP servers.
- Role-based access control (RBAC).
- Invalid, expired, and tampered JWT verification.
- Scope and audience validation.
"""

import os
import sys
import time
import pytest
import jwt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp_citizen.server import citizen_mcp
from mcp_officer.server import officer_mcp
from mcp_officer import tools as officer_tools
from mcp_citizen import tools as citizen_tools
from mcp_common.auth import verify_oauth_jwt
from evals.runner import mint_eval_token, patch_eval_jwks, _EVAL_KEY, _EVAL_KID
from cryptography.hazmat.primitives import serialization


@pytest.fixture(autouse=True)
def setup_environment():
    patch_eval_jwks()


def test_zero_cross_exposure():
    """Citizen server must never expose any officer tools, and vice-versa."""
    citizen_tools_list = [t.name for t in citizen_mcp._tool_manager.list_tools()]
    officer_tools_list = [t.name for t in officer_mcp._tool_manager.list_tools()]

    # Ensure completely disjoint sets
    intersection = set(citizen_tools_list).intersection(set(officer_tools_list))
    assert len(intersection) == 0, f"Cross-exposure detected: {intersection}"

    assert "approve_application" in officer_tools_list
    assert "approve_application" not in citizen_tools_list
    assert "reject_application" in officer_tools_list
    assert "reject_application" not in citizen_tools_list
    assert "get_my_profile" in citizen_tools_list
    assert "get_my_profile" not in officer_tools_list


def test_citizen_token_rejected_on_officer_tools():
    """A token with role 'citizen' attempting to invoke officer tools must be rejected."""
    async def _run():
        citizen_token = mint_eval_token("citizen:9217729489", role="citizen", scope="citizen")

        # Attempt to call approve_application
        res_approve = await officer_tools.approve_application("SSP26448454", confirm=True, auth_token=citizen_token)
        assert res_approve.get("status") == "unauthorized" or "Unauthorized" in str(res_approve)

        # Attempt to call search_applications
        res_search = await officer_tools.search_applications("9217729489", auth_token=citizen_token)
        assert res_search.get("status") == "unauthorized" or "Unauthorized" in str(res_search)
    import asyncio
    asyncio.run(_run())


def test_officer_token_rejected_on_citizen_tools():
    """An officer token cannot be used to masquerade as a citizen on citizen endpoints."""
    async def _run():
        officer_token = mint_eval_token("officer:admin", role="officer", scope="officer")

        res = await citizen_tools.get_my_profile(auth_token=officer_token)
        assert res.get("status") == "unauthenticated" or "Authentication required" in str(res)
    import asyncio
    asyncio.run(_run())


def test_expired_jwt_rejected():
    """Expired JWTs must be rejected."""
    now = int(time.time()) - 3600  # 1 hour ago
    claims = {
        "iss": "http://localhost:8000",
        "sub": "citizen:9217729489",
        "aud": "http://localhost:8000",
        "scope": "citizen",
        "role": "citizen",
        "client_id": "test-client",
        "iat": now - 7200,
        "exp": now,  # expired
    }
    pem = _EVAL_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()
    )
    expired_token = jwt.encode(claims, pem, algorithm="RS256", headers={"kid": _EVAL_KID})

    verified = verify_oauth_jwt(expired_token, expected_role="citizen", expected_scope="citizen")
    assert verified is None


def test_wrong_scope_and_role_rejected():
    """Tokens with invalid scope or role must be rejected."""
    token = mint_eval_token("citizen:9217729489", role="citizen", scope="invalid_scope")
    verified = verify_oauth_jwt(token, expected_role="citizen", expected_scope="citizen")
    assert verified is None

    token_role = mint_eval_token("citizen:9217729489", role="guest", scope="citizen")
    verified_role = verify_oauth_jwt(token_role, expected_role="citizen", expected_scope="citizen")
    assert verified_role is None


def test_wrong_audience_rejected():
    """Tokens minted for another resource server must be rejected."""
    token = mint_eval_token(
        "citizen:9217729489",
        role="citizen",
        scope="citizen",
        audience="https://other-service.gov.in"
    )
    verified = verify_oauth_jwt(
        token,
        expected_role="citizen",
        expected_scope="citizen",
        expected_audience="http://localhost:8000/mcp/citizen"
    )
    assert verified is None
