# -*- coding: utf-8 -*-
"""
Tests for Citizen MCP Server: tool discovery, authentication, data isolation, and statutory rules.
"""

import os
import sys
import pytest
import asyncio

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp_citizen.server import citizen_mcp
from mcp_citizen import tools as citizen_tools
from evals.runner import mint_eval_token, patch_eval_jwks, seed_eval_data_if_needed
from mcp_common.db import get_db_connection


@pytest.fixture(autouse=True)
def setup_environment():
    patch_eval_jwks()
    seed_eval_data_if_needed()


def test_citizen_tool_discovery():
    """Verify Citizen MCP tool registry contains exactly the 9 authorized tools and 0 officer tools."""
    tools = [t.name for t in citizen_mcp._tool_manager.list_tools()]
    expected_tools = [
        "get_my_profile",
        "get_my_application",
        "check_application_status",
        "get_application_timeline",
        "check_scheme_eligibility",
        "get_required_documents",
        "get_scheme_information",
        "withdraw_pending_application",
        "get_my_connected_applications"
    ]
    assert len(tools) == 9
    for exp in expected_tools:
        assert exp in tools

    # Strict check: No officer tools allowed in citizen registry
    assert "approve_application" not in tools
    assert "reject_application" not in tools
    assert "search_applications" not in tools
    assert "get_sla_breach_report" not in tools


def test_citizen_authentication_and_profile():
    """Valid citizen token retrieves their own profile with masked bank details."""
    async def _run():
        token = mint_eval_token("citizen:9217729489", role="citizen", scope="citizen")
        res = await citizen_tools.get_my_profile(auth_token=token)
        assert res.get("status") == "success"
        profile = res.get("profile")
        assert profile["applicant_name"] == "Sewali Gogoi"
        assert "CNRB" in profile["ifsc"]
        assert profile["bank_account_masked"].startswith("******") or "*" in profile["bank_account_masked"]
    asyncio.run(_run())


def test_citizen_record_isolation():
    """A citizen token can NEVER access another citizen's records."""
    async def _run():
        token_a = mint_eval_token("citizen:9217729489", role="citizen", scope="citizen")
        token_b = mint_eval_token("citizen:7747934527", role="citizen", scope="citizen")

        res_a = await citizen_tools.get_my_application(auth_token=token_a)
        res_b = await citizen_tools.get_my_application(auth_token=token_b)

        assert res_a["application"]["applicant_name"] == "Sewali Gogoi"
        assert res_b["application"]["applicant_name"] == "Girish Hussain"
        assert res_a["application"]["application_no"] != res_b["application"]["application_no"]
    asyncio.run(_run())


def test_scheme_eligibility_rules():
    """Verify age >= 60 requirement and 6 sanctioned blocks."""
    async def _run():
        # Underage (age 54) -> Ineligible
        res1 = await citizen_tools.check_scheme_eligibility("14/08/1972", "Namti")
        assert res1["eligible"] is False
        assert res1["calculated_age"] == 54

        # Senior (age 66) in valid block -> Eligible
        res2 = await citizen_tools.check_scheme_eligibility("01/01/1960", "Dhemaji Pathar")
        assert res2["eligible"] is True

        # Senior in non-sanctioned block -> Ineligible
        res3 = await citizen_tools.check_scheme_eligibility("01/01/1955", "Guwahati Urban")
        assert res3["eligible"] is False
    asyncio.run(_run())


def test_application_withdrawal_confirmation_and_db_state():
    """Application withdrawal requires confirmation and updates PostgreSQL status and audit trail."""
    async def _run():
        mob = "7255776618"
        token = mint_eval_token(f"citizen:{mob}", role="citizen", scope="citizen")

        # Step 1: Without confirmation -> prompts confirmation
        res1 = await citizen_tools.withdraw_pending_application(confirm=False, auth_token=token)
        assert res1.get("requires_confirmation") is True

        # Step 2: With explicit confirmation -> performs withdrawal
        res2 = await citizen_tools.withdraw_pending_application(confirm=True, auth_token=token)
        assert res2.get("success") is True
        assert res2.get("status") == "WITHDRAWN"

        # Verify DB state directly
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM applications WHERE mobile = %s", (mob,))
        assert cur.fetchone()[0] == "WITHDRAWN"

        cur.execute("SELECT action, actor FROM audit_log WHERE actor = %s ORDER BY at DESC LIMIT 1", (f"applicant:{mob}",))
        audit_row = cur.fetchone()
        assert audit_row is not None
        assert audit_row[0] == "WITHDRAW"
        cur.close()
        conn.close()
    asyncio.run(_run())
